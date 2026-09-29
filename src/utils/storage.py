"""
Deliberately kept out of the graph itself (not a node). Writing to
disk is an infrastructure concern, not part of the content pipeline's
logic — keeping it here means the graph stays pure and side-effect-free,
which is exactly why tests/test_graph_smoke.py can invoke the graph
directly, twice, with no filesystem or cleanup involved.

Everything for one run lives in one folder — outputs/{run_id}/ — the
same shape as a "publish this folder" export: article.md, the image,
social variants, and the raw structured data for debugging/reprocessing.
Fine for a portfolio-scale service; swap for S3/a database if this ever
needs to survive a container restart in a real multi-instance deployment.
"""
from __future__ import annotations

from pathlib import Path

from src.config import settings
from src.schemas import FinalPackage


def run_dir(run_id: str, *, create: bool = True) -> Path:
    d = Path(settings.output_dir) / run_id
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def save_package(package: FinalPackage) -> Path:
    """Saves the raw structured result as JSON — useful for debugging
    or reprocessing, separate from the human-facing markdown export."""
    path = run_dir(package.run_id) / "package.json"
    path.write_text(package.model_dump_json(indent=2))
    return path


def load_package(run_id: str) -> FinalPackage | None:
    path = run_dir(run_id, create=False) / "package.json"
    if not path.exists():
        return None
    return FinalPackage.model_validate_json(path.read_text())


def list_saved_runs() -> list[str]:
    out_dir = Path(settings.output_dir)
    if not out_dir.exists():
        return []
    return sorted(p.name for p in out_dir.iterdir() if p.is_dir())
