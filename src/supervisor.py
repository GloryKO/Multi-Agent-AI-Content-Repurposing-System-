"""
Deterministic supervisor: reads pipeline state and decides which
specialist agent runs next. Every specialist node hands control back
here (`next: "supervisor"`) instead of calling each other directly, so
there's exactly one place that knows the shape of the whole pipeline.

Deliberately NOT an LLM call. An LLM-based router (structured-output
classifier choosing the next node, like the pattern this was modeled
after) makes sense when the next step genuinely depends on judgment —
e.g. routing a user's free-form question to one of several specialist
agents. Here the flow is a fixed DAG with one conditional loop (the
critique cycle), so a plain function is more reliable, free, instant,
and trivial to unit test. Swapping in an LLM router later, if the
pipeline grows branches that really need judgment, is a one-function
change — nothing else in the graph has to know the difference.
"""
from __future__ import annotations

from src.config import settings
from src.logging_config import get_logger
from src.state import PipelineState

TERMINAL = "END"


def supervisor_node(state: PipelineState) -> dict:
    log = get_logger(run_id=state.get("run_id", "unknown"), node="supervisor")

    if state.get("errors"):
        log.error("routing_to_end_due_to_errors", errors=state["errors"])
        return {"next": TERMINAL}

    if state.get("scraped_content") is None:
        decision = "scrape"
    elif state.get("content_summary") is None:
        decision = "summarize"
    elif state.get("serp_insight") is None:
        decision = "seo_research"
    elif state.get("brief") is None:
        decision = "brief"
    elif state.get("draft") is None:
        decision = "writer"
    elif state.get("critique") is None:
        decision = "critic"
    elif not state["critique"].passed and state.get("revision_count", 0) < settings.max_critique_loops:
        log.info("looping_back_to_writer", revision_count=state.get("revision_count", 0))
        # Clear the stale failing critique so the supervisor routes to
        # "critic" (not back into this same branch) once the writer
        # produces its next attempt — otherwise this branch would keep
        # matching forever on the old critique object.
        return {"next": "writer", "critique": None}
    elif state.get("social") is None:
        decision = "repurposer"
    elif not state.get("image_attempted"):
        decision = "image"
    elif state.get("final_package") is None:
        decision = "assembler"
    else:
        decision = TERMINAL

    log.info("routing_decision", next=decision, revision_count=state.get("revision_count", 0))
    return {"next": decision}
