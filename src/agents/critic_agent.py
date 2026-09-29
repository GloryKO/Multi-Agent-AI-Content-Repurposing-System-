"""
Same confidence-gating pattern used for agent action-safety in
production work: don't let a below-threshold output ship. Here,
"ship" means "proceed to repurposing/assembly" rather than "take an
action," but the mechanism is identical — score against a spec, gate
on a threshold, loop back on failure, cap the loop so it can't run
forever.
"""
from __future__ import annotations

from src.clients.llm import generate_structured
from src.config import settings
from src.logging_config import get_logger
from src.schemas import SEOCritique
from src.state import PipelineState

_SYSTEM_PROMPT = (
    "You are a strict SEO editor. Score the draft against the brief on: "
    "keyword coverage, heading coverage, and length adherence. Give an "
    "overall score from 0 to 1. List specific, actionable issues if any. "
    "Set passed=true only if the draft is genuinely publish-ready."
)


def critic_node(state: PipelineState) -> dict:
    log = get_logger(run_id=state["run_id"], node="critic")

    user_prompt = (
        f"Brief:\n{state['brief'].model_dump_json(indent=2)}\n\n"
        f"Draft:\n{state['draft'].model_dump_json(indent=2)}"
    )

    critique, usage = generate_structured(_SYSTEM_PROMPT, user_prompt, SEOCritique, model=settings.llm_model)
    state["cost_tracker"].record("critic", settings.llm_model, **usage)

    # Reconcile the model's own "passed" flag with our numeric threshold —
    # don't just trust the LLM's self-assessment.
    passed = critique.passed and critique.score >= settings.seo_score_threshold
    critique.passed = passed

    revision_count = state.get("revision_count", 0)
    log.info("critique_done", score=critique.score, passed=passed, revision_count=revision_count)

    # The supervisor owns the actual loop/cap decision (single source of
    # truth for control flow); this node only reports and, if it's about
    # to hand back a failing critique, bumps the counter so the cap is
    # visible to whoever routes next.
    next_revision_count = revision_count if passed else revision_count + 1
    return {
        "critique": critique,
        "pending_feedback": critique.issues,
        "revision_count": next_revision_count,
    }
