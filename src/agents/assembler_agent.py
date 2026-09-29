from __future__ import annotations

from src.logging_config import get_logger
from src.schemas import CostReport, FinalPackage
from src.state import PipelineState


def assembler_node(state: PipelineState) -> dict:
    log = get_logger(run_id=state["run_id"], node="assembler")

    cost = CostReport(**state["cost_tracker"].report())
    package = FinalPackage(
        run_id=state["run_id"],
        article=state["draft"],
        seo_critique=state["critique"],
        social=state["social"],
        image=state.get("image"),
        cost=cost,
    )

    log.info("run_complete", total_usd=cost.total_usd, total_tokens=cost.total_tokens)
    return {"final_package": package}
