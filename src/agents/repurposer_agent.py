from __future__ import annotations

from src.clients.llm import generate_structured
from src.config import settings
from src.logging_config import get_logger
from src.schemas import SocialVariants
from src.state import PipelineState

_SYSTEM_PROMPT = (
    "Repurpose the approved article into: a Twitter/X thread (5-8 tweets, "
    "hook first, one idea per tweet), a LinkedIn post (professional tone, "
    "3-5 short paragraphs), and a short email newsletter snippet (2-3 "
    "sentences plus a call to action). Match the brand voice given."
)


def repurposer_node(state: PipelineState) -> dict:
    log = get_logger(run_id=state["run_id"], node="repurposer")

    user_prompt = (
        f"Brand voice: {state['brand_voice']}\n\n"
        f"Article:\n{state['draft'].body_markdown}"
    )

    social, usage = generate_structured(_SYSTEM_PROMPT, user_prompt, SocialVariants, model=settings.llm_model)
    state["cost_tracker"].record("repurposer", settings.llm_model, **usage)

    log.info("repurpose_done", tweets=len(social.twitter_thread))
    return {"social": social}
