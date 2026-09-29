"""
Every LLM call in this pipeline returns one of these Pydantic models
via Instructor, instead of raw text that then has to be parsed. This
is what makes the pipeline reliable enough to run unattended: a
malformed response is a validation error the graph can catch and
retry, not a silent parsing bug three steps later.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class SourceSummary(BaseModel):
    """Output of the summarizer node — a condensed version of scraped
    source content that preserves what downstream nodes actually need."""

    key_points: List[str] = Field(description="Core facts/arguments from the source, most important first")
    notable_stats_or_quotes: List[str] = Field(
        default_factory=list,
        description="Any concrete numbers, stats, or quotable lines worth preserving verbatim-in-spirit",
    )
    summary: str = Field(description="A dense 150-300 word summary of the source content")


class SerpInsight(BaseModel):
    top_ranking_titles: List[str]
    common_headings: List[str] = Field(description="Headings/subtopics that recur across top-ranking pages")
    people_also_ask: List[str] = Field(default_factory=list)
    content_gap_opportunities: List[str] = Field(
        default_factory=list,
        description="Angles or subtopics the top results under-cover, worth owning in our draft",
    )


class ContentBrief(BaseModel):
    """The spec the writer agent must satisfy. Everything downstream is
    scored against this, which is what makes the critique loop possible."""

    target_keyword: str
    working_title: str
    meta_description: str = Field(max_length=160)
    required_headings: List[str]
    target_word_count: int = Field(ge=400, le=3000)
    keyword_placements: List[str] = Field(
        description="Where the target keyword (or close variants) must naturally appear"
    )
    tone: str


class ArticleDraft(BaseModel):
    title: str
    meta_description: str = Field(max_length=160)
    headings: List[str]
    body_markdown: str
    word_count: int
    alt_text_suggestion: str = Field(description="Alt text for the accompanying image, based on article topic")


class SEOCritique(BaseModel):
    """Output of the critic node. Mirrors the confidence-gating pattern
    from production agent work: below-threshold output loops back for
    a rewrite instead of shipping as-is."""

    score: float = Field(ge=0.0, le=1.0, description="Overall SEO/brief-fit score")
    keyword_coverage_ok: bool
    heading_coverage_ok: bool
    length_ok: bool
    issues: List[str] = Field(default_factory=list, description="Specific, actionable problems to fix")
    passed: bool


class SocialVariants(BaseModel):
    twitter_thread: List[str] = Field(description="Each item is one tweet in the thread, in order")
    linkedin_post: str
    email_newsletter_snippet: str


class ImageResult(BaseModel):
    url: str
    photographer: str
    photographer_url: str
    alt_text: str
    source: str = "pexels"


class CostReport(BaseModel):
    total_usd: float
    total_tokens: int
    by_node: List[dict]


class FinalPackage(BaseModel):
    run_id: str
    article: ArticleDraft
    seo_critique: SEOCritique
    social: SocialVariants
    image: Optional[ImageResult]
    cost: CostReport
