from __future__ import annotations

from src.clients.llm import generate_structured
from src.config import settings
from src.logging_config import get_logger
from src.schemas import ContentBrief
from src.state import PipelineState

_SYSTEM_PROMPT = (
    "You are a senior content strategist. Given a source summary, SEO "
    "research on the target keyword, and a brand voice, produce a precise "
    "content brief a writer must follow: working title, meta description "
    "under 160 characters, required headings, target word count, where the "
    "keyword must naturally appear, and tone."
)


def brief_node(state: PipelineState) -> dict:
    log = get_logger(run_id=state["run_id"], node="brief")

    user_prompt = (
        f"Target keyword: {state['target_keyword']}\n"
        f"Brand voice: {state['brand_voice']}\n\n"
        f"Source summary: {state['content_summary'].summary}\n"
        f"Source key points: {state['content_summary'].key_points}\n\n"
        f"SERP insight - top ranking titles: {state['serp_insight'].top_ranking_titles}\n"
        f"Common headings across top results: {state['serp_insight'].common_headings}\n"
        f"People also ask: {state['serp_insight'].people_also_ask}\n"
        f"Content gap opportunities: {state['serp_insight'].content_gap_opportunities}\n"
    )

    brief, usage = generate_structured(_SYSTEM_PROMPT, user_prompt, ContentBrief, model=settings.llm_model)
    state["cost_tracker"].record("brief", settings.llm_model, **usage)

    log.info("brief_done", title=brief.working_title, target_words=brief.target_word_count)
    return {"brief": brief}
