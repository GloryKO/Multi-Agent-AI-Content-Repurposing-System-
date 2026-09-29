"""
FastAPI app. Generation is slow (multiple LLM calls + external APIs),
so /generate kicks off a background job and returns immediately with a
run_id; the client polls /status/{run_id}. This is the same pattern as
a webhook-driven async job — no HTTP request sits open for two minutes
waiting on an LLM chain.

Run store is in-memory here on purpose (this is a portfolio-scale
service). For a real multi-worker deployment, swap RUNS for Redis and
run generation via Celery/RQ instead of BackgroundTasks — the pipeline
logic in src/graph.py doesn't change either way.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.graph import compiled_graph
from src.logging_config import configure_logging, get_logger
from src.state import PipelineState, new_state
from src.utils.markdown_export import export_markdown
from src.utils.retry import UpstreamFailure
from src.utils.storage import list_saved_runs, load_package, run_dir, save_package

configure_logging()
log = get_logger(component="api")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="Content Repurposing Pipeline", version="0.1.0")

# Loosened for demo purposes — tighten to your actual frontend origin in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

RUNS: dict[str, dict] = {}

PIPELINE_STEPS = [
    "scrape",
    "summarize",
    "seo_research",
    "brief",
    "writer",
    "critic",
    "repurposer",
    "image",
    "assembler",
]


class GenerateRequest(BaseModel):
    target_keyword: str
    brand_voice: str = "clear, confident, and helpful"
    source_url: Optional[str] = None
    raw_text: Optional[str] = None


class GenerateResponse(BaseModel):
    run_id: str
    status: str


def _progress_from_state(state: PipelineState) -> dict:
    critique = state.get("critique")
    return {
        "current_step": state.get("next"),
        "revision_count": state.get("revision_count", 0),
        "steps": {
            "scrape": state.get("scraped_content") is not None,
            "summarize": state.get("content_summary") is not None,
            "seo_research": state.get("serp_insight") is not None,
            "brief": state.get("brief") is not None,
            "writer": state.get("draft") is not None,
            "critic": critique is not None or (
                state.get("draft") is not None and state.get("revision_count", 0) > 0
            ),
            "repurposer": state.get("social") is not None,
            "image": state.get("image_attempted", False),
            "assembler": state.get("final_package") is not None,
        },
        "critique_passed": bool(critique and critique.passed),
    }


def _run_pipeline(run_id: str, initial_state: PipelineState) -> None:
    """Stream graph values so /status can show live progress mid-run."""
    try:
        final_state = initial_state
        for state in compiled_graph.stream(
            initial_state,
            config={"recursion_limit": 50},
            stream_mode="values",
        ):
            final_state = state
            RUNS[run_id] = {"status": "running", "state": state}

        package = final_state.get("final_package")
        if package:
            saved_path = save_package(package)
            exported = export_markdown(package)
            log.info("run_saved", run_id=run_id, json_path=str(saved_path), exported=exported)
            RUNS[run_id] = {"status": "done", "state": final_state}
        elif final_state.get("errors"):
            RUNS[run_id] = {
                "status": "failed",
                "error": "; ".join(final_state["errors"]),
                "state": final_state,
            }
        else:
            RUNS[run_id] = {"status": "done", "state": final_state}
    except UpstreamFailure as e:
        log.error("pipeline_failed", run_id=run_id, error=str(e))
        RUNS[run_id] = {"status": "failed", "error": str(e)}
    except Exception as e:  # noqa: BLE001 - top-level safety net for a background job
        log.error("pipeline_crashed", run_id=run_id, error=str(e))
        RUNS[run_id] = {"status": "failed", "error": f"Unexpected error: {e}"}


@app.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest, background_tasks: BackgroundTasks) -> GenerateResponse:
    if not req.source_url and not req.raw_text:
        raise HTTPException(400, "Provide either source_url or raw_text")

    run_id = str(uuid.uuid4())
    state = new_state(
        run_id=run_id,
        target_keyword=req.target_keyword,
        brand_voice=req.brand_voice,
        source_url=req.source_url,
        raw_text=req.raw_text,
    )
    RUNS[run_id] = {"status": "running", "state": state}
    background_tasks.add_task(_run_pipeline, run_id, state)
    return GenerateResponse(run_id=run_id, status="running")


@app.get("/status/{run_id}")
def status(run_id: str):
    run = RUNS.get(run_id)
    if run is None:
        raise HTTPException(404, "Unknown run_id")

    if run["status"] == "done":
        package = run["state"].get("final_package")
        return {
            "status": "done",
            "result": package.model_dump() if package else None,
            "output_folder": str(run_dir(run_id)) if package else None,
            "progress": _progress_from_state(run["state"]),
        }
    if run["status"] == "failed":
        return {
            "status": "failed",
            "error": run.get("error"),
            "progress": _progress_from_state(run["state"]) if run.get("state") else None,
        }

    return {
        "status": "running",
        "progress": _progress_from_state(run["state"]),
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/runs")
def list_runs():
    """Every run saved to disk, independent of the in-memory RUNS dict —
    survives an API process restart."""
    return {"run_ids": list_saved_runs()}


@app.get("/runs/{run_id}")
def get_saved_run(run_id: str):
    package = load_package(run_id)
    if package is None:
        raise HTTPException(404, "No saved run with that id")
    folder = run_dir(run_id, create=False)
    files = sorted(str(p.relative_to(folder)) for p in folder.rglob("*") if p.is_file())
    return {"result": package.model_dump(), "output_folder": str(folder), "files": files}


@app.get("/outputs/{run_id}/{file_path:path}")
def serve_output_file(run_id: str, file_path: str):
    """Serve exported files (images, markdown) for the demo UI."""
    folder = run_dir(run_id, create=False).resolve()
    target = (folder / file_path).resolve()
    if not str(target).startswith(str(folder)) or not target.is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(target)


@app.get("/")
def index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(404, "UI not found — expected static/index.html")
    return FileResponse(index_path)


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


if __name__ == "__main__":
    # Quick CLI smoke run, no server needed:
    #   python -m src.main "https://example.com/article" "your target keyword"
    import json
    import sys

    configure_logging()
    url = sys.argv[1] if len(sys.argv) > 1 else None
    keyword = sys.argv[2] if len(sys.argv) > 2 else "example keyword"
    raw_text = None
    if url is None and len(sys.argv) <= 1:
        raw_text = (
            "Artificial intelligence is changing how freelancers win clients. "
            "Agencies that ship content systems, not one-off blogs, retain more "
            "retainers. Keyword research, briefs, drafts, and social variants "
            "used to take a full day; multi-agent pipelines compress that into "
            "minutes while keeping human review on the score that matters."
        )

    initial = new_state(
        run_id=str(uuid.uuid4()),
        target_keyword=keyword,
        brand_voice="clear, confident, and helpful",
        source_url=url,
        raw_text=raw_text,
    )
    result = compiled_graph.invoke(initial, config={"recursion_limit": 50})
    final = result.get("final_package")
    if final:
        saved_path = save_package(final)
        exported = export_markdown(final)
        print(f"Saved raw data to {saved_path}")
        print(f"Exported publish-ready markdown to {exported.get('article')}\n")
        print(final.model_dump_json(indent=2))
    else:
        print(json.dumps({"errors": result.get("errors")}, indent=2))
