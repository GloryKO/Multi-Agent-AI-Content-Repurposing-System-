from __future__ import annotations

from src.clients.llm import generate_structured
from src.config import settings
from src.logging_config import get_logger
from src.schemas import ArticleDraft
from src.state import PipelineState

_SYSTEM_PROMPT = (
    "You are an expert content writer. Write a complete article in Markdown "
    "that strictly follows the given brief: hit the required headings, stay "
    "close to the target word count, place the keyword naturally where "
    "specified, and match the requested tone. Output the full body as "
    "body_markdown, plus a title, meta description, and an alt-text "
    "suggestion for the accompanying image."
)


def writer_node(state: PipelineState) -> dict:
    log = get_logger(run_id=state["run_id"], node="writer", revision=state.get("revision_count", 0))
    brief = state["brief"]

    user_prompt = f"Brief:\n{brief.model_dump_json(indent=2)}\n\nSource material:\n{state['content_summary'].summary}"

    feedback = state.get("pending_feedback")
    if feedback:
        user_prompt += f"\n\nThe previous draft failed review. Fix these issues: {feedback}"

    draft, usage = generate_structured(_SYSTEM_PROMPT, user_prompt, ArticleDraft, model=settings.llm_model)
    state["cost_tracker"].record("writer", settings.llm_model, **usage)

    log.info("draft_done", word_count=draft.word_count)
    return {"draft": draft}
