from __future__ import annotations

from src.clients import serper_client
from src.clients.llm import generate_structured
from src.config import settings
from src.logging_config import get_logger
from src.schemas import SerpInsight
from src.state import PipelineState
from src.utils.retry import UpstreamFailure

_SYSTEM_PROMPT = (
    "You analyze raw Google SERP data and extract what content strategy "
    "signals it reveals: what titles are winning, what headings/subtopics "
    "recur across top results, common 'People Also Ask' questions, and any "
    "subtopics the top results seem to under-cover that a new article "
    "could own."
)


def seo_research_node(state: PipelineState) -> dict:
    log = get_logger(run_id=state["run_id"], node="seo_research")
    keyword = state["target_keyword"]

    try:
        raw = serper_client.search(keyword)
    except UpstreamFailure as e:
        log.error("serper_failed", error=str(e))
        return {"errors": state.get("errors", []) + [str(e)]}

    organic = raw.get("organic", [])[:8]
    paa = [q.get("question", "") for q in raw.get("peopleAlsoAsk", [])]

    condensed = {
        "titles": [r.get("title") for r in organic],
        "snippets": [r.get("snippet") for r in organic],
        "people_also_ask": paa,
    }

    insight, usage = generate_structured(
        _SYSTEM_PROMPT, str(condensed), SerpInsight, model=settings.llm_model
    )
    state["cost_tracker"].record("seo_research", settings.llm_model, **usage)

    log.info("seo_research_done", ranking_titles=len(insight.top_ranking_titles))
    return {"serp_insight": insight}
