from __future__ import annotations

from src.clients import firecrawl_client
from src.logging_config import get_logger
from src.state import PipelineState
from src.utils.retry import UpstreamFailure


def scrape_node(state: PipelineState) -> dict:
    log = get_logger(run_id=state["run_id"], node="scrape")

    if state.get("raw_text"):
        log.info("skip_scrape_raw_text_provided")
        return {"scraped_content": state["raw_text"]}

    url = state.get("source_url")
    if not url:
        return {"errors": state.get("errors", []) + ["No source_url or raw_text provided"]}

    log.info("scrape_start", url=url)
    try:
        content = firecrawl_client.scrape(url)
    except UpstreamFailure as e:
        log.error("scrape_failed", error=str(e))
        return {"errors": state.get("errors", []) + [str(e)]}

    log.info("scrape_done", chars=len(content))
    return {"scraped_content": content}
