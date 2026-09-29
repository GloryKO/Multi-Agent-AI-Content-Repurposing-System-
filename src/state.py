"""
Shared state that flows through every node in the graph. Kept as a
single TypedDict (LangGraph's convention) so the supervisor can make
routing decisions just by reading state, without agents needing to
know about each other directly.
"""
from __future__ import annotations

from typing import List, Optional, TypedDict

from src.schemas import (
    ArticleDraft,
    ContentBrief,
    FinalPackage,
    ImageResult,
    SEOCritique,
    SerpInsight,
    SocialVariants,
    SourceSummary,
)
from src.utils.cost_tracker import CostTracker


class PipelineState(TypedDict, total=False):
    # --- input ---
    run_id: str
    source_url: Optional[str]
    raw_text: Optional[str]  # used instead of source_url if user pastes text directly
    target_keyword: str
    brand_voice: str

    # --- working data, filled in as agents run ---
    scraped_content: Optional[str]
    content_summary: Optional[SourceSummary]
    serp_insight: Optional[SerpInsight]
    brief: Optional[ContentBrief]
    draft: Optional[ArticleDraft]
    critique: Optional[SEOCritique]
    pending_feedback: List[str]  # persists across the critique->writer loop, decoupled from `critique`
    revision_count: int
    social: Optional[SocialVariants]
    image: Optional[ImageResult]
    image_attempted: bool
    final_package: Optional[FinalPackage]

    # --- control / observability ---
    next: str  # supervisor's routing decision — name of the next node, or "END"
    errors: List[str]
    cost_tracker: CostTracker


def new_state(run_id: str, target_keyword: str, brand_voice: str,
              source_url: Optional[str] = None, raw_text: Optional[str] = None) -> PipelineState:
    return PipelineState(
        run_id=run_id,
        source_url=source_url,
        raw_text=raw_text,
        target_keyword=target_keyword,
        brand_voice=brand_voice,
        scraped_content=None,
        content_summary=None,
        serp_insight=None,
        brief=None,
        draft=None,
        critique=None,
        pending_feedback=[],
        revision_count=0,
        social=None,
        image=None,
        image_attempted=False,
        final_package=None,
        next="scrape",
        errors=[],
        cost_tracker=CostTracker(),
    )
