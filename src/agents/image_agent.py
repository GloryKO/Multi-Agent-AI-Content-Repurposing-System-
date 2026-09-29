from __future__ import annotations

from src.clients import pexels_client
from src.logging_config import get_logger
from src.state import PipelineState
from src.utils.retry import UpstreamFailure


def image_node(state: PipelineState) -> dict:
    log = get_logger(run_id=state["run_id"], node="image")
    draft = state["draft"]

    query = draft.title

    try:
        image = pexels_client.find_image(query, alt_text=draft.alt_text_suggestion)
    except UpstreamFailure as e:

        log.warning("image_search_failed_continuing", error=str(e))
        return {"image": None, "image_attempted": True}

    log.info("image_done", found=image is not None)
    return {"image": image, "image_attempted": True}
