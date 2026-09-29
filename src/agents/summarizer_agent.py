"""
Handles the "Firecrawl can return a lot of text" problem.

Truncating at N characters was the other option on the table, but it
was rejected: truncation always keeps the start of the article and
throws away the end, which is exactly where conclusions, CTAs, and
often the most citation-worthy stats live. For a pipeline whose whole
job is producing SEO content, silently losing the back half of the
source is a real quality bug, not just an edge case.

Instead: only pay for a summarization LLM call when the content
actually risks blowing the downstream context budget (checked via
real token count, not a guess). When it's large, chunk it and
map-reduce summarize so every part of the source gets read, then
combine into one structured summary that keeps key facts and stats
instead of just "vibes."
"""
from __future__ import annotations

import tiktoken

from src.clients.llm import generate_structured
from src.config import settings
from src.logging_config import get_logger
from src.schemas import SourceSummary
from src.state import PipelineState
from src.utils.retry import UpstreamFailure

_encoder = None


def _get_encoder():
    """Lazy singleton. tiktoken downloads its encoding file on first use,
    so this stays out of module import time (matters for tests/CI running
    without network access to openaipublic's blob storage)."""
    global _encoder
    if _encoder is None:
        try:
            _encoder = tiktoken.get_encoding("cl100k_base")
        except Exception:  # noqa: BLE001 - network unavailable, fall back below
            _encoder = "unavailable"
    return _encoder

_CHUNK_SYSTEM_PROMPT = (
    "You summarize a chunk of a longer article. Preserve concrete facts, "
    "statistics, and any quotable lines. Do not add commentary or opinions."
)
_COMBINE_SYSTEM_PROMPT = (
    "You combine several partial summaries of one article into a single "
    "coherent summary. Preserve every distinct fact and statistic from the "
    "partial summaries. Do not repeat yourself."
)


def _token_count(text: str) -> int:
    encoder = _get_encoder()
    if encoder == "unavailable":
        return len(text) // 4  # rough English-text heuristic (~4 chars/token)
    return len(encoder.encode(text))


def _chunk(text: str, chunk_tokens: int) -> list[str]:
    encoder = _get_encoder()
    if encoder == "unavailable":
        chunk_chars = chunk_tokens * 4
        return [text[i : i + chunk_chars] for i in range(0, len(text), chunk_chars)]
    tokens = encoder.encode(text)
    return [encoder.decode(tokens[i : i + chunk_tokens]) for i in range(0, len(tokens), chunk_tokens)]


def summarize_node(state: PipelineState) -> dict:
    log = get_logger(run_id=state["run_id"], node="summarize")
    content = state.get("scraped_content") or ""
    tracker = state["cost_tracker"]

    token_count = _token_count(content)

    if token_count <= settings.summarize_token_threshold:
        log.info("summarize_skipped_short_enough", tokens=token_count)
        # Wrap as-is into the same schema downstream nodes expect, no LLM cost.
        summary = SourceSummary(key_points=[], notable_stats_or_quotes=[], summary=content)
        return {"content_summary": summary}

    log.info("summarize_map_reduce_start", tokens=token_count)
    chunks = _chunk(content, settings.chunk_size_tokens)

    partials: list[SourceSummary] = []
    try:
        for i, chunk in enumerate(chunks):
            result, usage = generate_structured(
                _CHUNK_SYSTEM_PROMPT,
                chunk,
                SourceSummary,
                model=settings.llm_summarizer_model,
            )
            tracker.record("summarize_chunk", settings.llm_summarizer_model, **usage)
            partials.append(result)
            log.info("summarize_chunk_done", chunk_index=i, of=len(chunks))

        combined_input = "\n\n".join(
            f"Partial summary {i+1}:\n{p.summary}\nKey points: {p.key_points}\nStats: {p.notable_stats_or_quotes}"
            for i, p in enumerate(partials)
        )
        final, usage = generate_structured(
            _COMBINE_SYSTEM_PROMPT, combined_input, SourceSummary, model=settings.llm_summarizer_model
        )
        tracker.record("summarize_combine", settings.llm_summarizer_model, **usage)
    except UpstreamFailure as e:
        log.error("summarize_failed", error=str(e))
        return {"errors": state.get("errors", []) + [str(e)]}

    log.info("summarize_done", final_words=len(final.summary.split()))
    return {"content_summary": final}
