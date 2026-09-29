"""
Smoke test: runs the full graph with every external dependency mocked,
so it verifies the *wiring* (supervisor routing, state threading,
critique loop, final assembly) without spending a cent on real APIs.
Run with: pytest
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

from src.schemas import (
    ArticleDraft,
    ContentBrief,
    ImageResult,
    SEOCritique,
    SerpInsight,
    SocialVariants,
    SourceSummary,
)
from src.state import new_state


def _usage():
    return {"input_tokens": 100, "output_tokens": 50}


def test_pipeline_happy_path():
    with (
        patch("src.agents.scraper_agent.firecrawl_client.scrape", return_value="# Some scraped article\n" * 20),
        patch(
            "src.agents.seo_research_agent.serper_client.search",
            return_value={"organic": [{"title": "T1", "snippet": "S1"}], "peopleAlsoAsk": []},
        ),
        patch(
            "src.agents.image_agent.pexels_client.find_image",
            return_value=ImageResult(
                url="https://images.pexels.com/x.jpg",
                photographer="Jane Doe",
                photographer_url="https://pexels.com/@jane",
                alt_text="a relevant photo",
            ),
        ),
        patch("src.agents.seo_research_agent.generate_structured") as mock_seo,
        patch("src.agents.brief_agent.generate_structured") as mock_brief,
        patch("src.agents.writer_agent.generate_structured") as mock_writer,
        patch("src.agents.critic_agent.generate_structured") as mock_critic,
        patch("src.agents.repurposer_agent.generate_structured") as mock_repurposer,
        patch("src.agents.summarizer_agent.generate_structured") as mock_summarizer,
    ):
        def side_effect(system_prompt, user_prompt, response_model, model=None):
            if response_model is SourceSummary:
                return SourceSummary(key_points=["a"], notable_stats_or_quotes=[], summary="short summary"), _usage()
            if response_model is SerpInsight:
                return SerpInsight(top_ranking_titles=["T1"], common_headings=["H1"]), _usage()
            if response_model is ContentBrief:
                return ContentBrief(
                    target_keyword="ai engineering",
                    working_title="Title",
                    meta_description="desc",
                    required_headings=["H1"],
                    target_word_count=500,
                    keyword_placements=["intro"],
                    tone="confident",
                ), _usage()
            if response_model is ArticleDraft:
                return ArticleDraft(
                    title="Title", meta_description="desc", headings=["H1"],
                    body_markdown="Body text " * 50, word_count=500,
                    alt_text_suggestion="alt",
                ), _usage()
            if response_model is SEOCritique:
                return SEOCritique(
                    score=0.9, keyword_coverage_ok=True, heading_coverage_ok=True,
                    length_ok=True, issues=[], passed=True,
                ), _usage()
            if response_model is SocialVariants:
                return SocialVariants(
                    twitter_thread=["tweet 1", "tweet 2"],
                    linkedin_post="post",
                    email_newsletter_snippet="snippet",
                ), _usage()
            raise AssertionError(f"Unexpected response_model: {response_model}")

        mock_seo.side_effect = side_effect
        mock_brief.side_effect = side_effect
        mock_writer.side_effect = side_effect
        mock_critic.side_effect = side_effect
        mock_repurposer.side_effect = side_effect
        mock_summarizer.side_effect = side_effect

        from src.graph import build_graph

        graph = build_graph()
        state = new_state(
            run_id=str(uuid.uuid4()),
            target_keyword="ai engineering",
            brand_voice="confident",
            source_url="https://example.com/article",
        )
        result = graph.invoke(state, config={"recursion_limit": 50})

        assert result["final_package"] is not None
        assert result["final_package"].article.title == "Title"
        assert result["errors"] == []


def test_critique_loop_caps_and_still_completes():
    """A draft that never passes review should retry up to
    settings.max_critique_loops times, then proceed anyway rather than
    looping forever — this is the behaviour the supervisor's cap logic
    exists to guarantee."""
    with (
        patch("src.agents.scraper_agent.firecrawl_client.scrape", return_value="# Article\n" * 20),
        patch(
            "src.agents.seo_research_agent.serper_client.search",
            return_value={"organic": [{"title": "T1", "snippet": "S1"}], "peopleAlsoAsk": []},
        ),
        patch("src.agents.image_agent.pexels_client.find_image", return_value=None),
        patch("src.agents.seo_research_agent.generate_structured") as mock_seo,
        patch("src.agents.brief_agent.generate_structured") as mock_brief,
        patch("src.agents.writer_agent.generate_structured") as mock_writer,
        patch("src.agents.critic_agent.generate_structured") as mock_critic,
        patch("src.agents.repurposer_agent.generate_structured") as mock_repurposer,
        patch("src.agents.summarizer_agent.generate_structured") as mock_summarizer,
    ):
        writer_calls = {"count": 0}

        def writer_side_effect(system_prompt, user_prompt, response_model, model=None):
            writer_calls["count"] += 1
            return ArticleDraft(
                title="Title", meta_description="desc", headings=["H1"],
                body_markdown="Body text " * 50, word_count=500,
                alt_text_suggestion="alt",
            ), _usage()

        def always_fails(system_prompt, user_prompt, response_model, model=None):
            # Always below threshold and passed=False, no matter what.
            return SEOCritique(
                score=0.2, keyword_coverage_ok=False, heading_coverage_ok=False,
                length_ok=False, issues=["missing keyword"], passed=False,
            ), _usage()

        mock_summarizer.side_effect = lambda *a, **k: (
            SourceSummary(key_points=["a"], notable_stats_or_quotes=[], summary="short summary"), _usage()
        )
        mock_seo.side_effect = lambda *a, **k: (
            SerpInsight(top_ranking_titles=["T1"], common_headings=["H1"]), _usage()
        )
        mock_brief.side_effect = lambda *a, **k: (
            ContentBrief(
                target_keyword="ai engineering", working_title="Title", meta_description="desc",
                required_headings=["H1"], target_word_count=500, keyword_placements=["intro"],
                tone="confident",
            ), _usage()
        )
        mock_writer.side_effect = writer_side_effect
        mock_critic.side_effect = always_fails
        mock_repurposer.side_effect = lambda *a, **k: (
            SocialVariants(twitter_thread=["t1"], linkedin_post="post", email_newsletter_snippet="snip"), _usage()
        )

        from src.graph import build_graph

        graph = build_graph()
        state = new_state(
            run_id=str(uuid.uuid4()), target_keyword="ai engineering",
            brand_voice="confident", source_url="https://example.com/article",
        )
        result = graph.invoke(state, config={"recursion_limit": 50})

        # Writer runs once for the initial draft, then once per allowed
        # retry (revision_count reaching max_critique_loops stops the
        # loop) — never more than that, even though critique always fails.
        from src.config import settings

        assert writer_calls["count"] == settings.max_critique_loops
        assert result["final_package"] is not None  # still completes, doesn't hang
        assert result["final_package"].seo_critique.passed is False


def test_markdown_export_writes_article_image_and_social_files(tmp_path):
    from src.schemas import ArticleDraft, CostReport, FinalPackage, ImageResult, SEOCritique, SocialVariants
    from src.utils.markdown_export import export_markdown
    import src.config as config_module

    # Point output_dir at a pytest tmp_path so this test never touches
    # the real outputs/ folder and cleans itself up automatically.
    original_output_dir = config_module.settings.output_dir
    config_module.settings.output_dir = str(tmp_path)

    package = FinalPackage(
        run_id="test-run-123",
        article=ArticleDraft(
            title="Why AI Agents Need Confidence Gating",
            meta_description="A short explainer.",
            headings=["Intro", "The Problem", "The Fix"],
            body_markdown="## Intro\n\nSome body text here.\n\n## The Fix\n\nMore text.",
            word_count=42,
            alt_text_suggestion="An AI agent evaluating its own confidence",
        ),
        seo_critique=SEOCritique(
            score=0.9, keyword_coverage_ok=True, heading_coverage_ok=True,
            length_ok=True, issues=[], passed=True,
        ),
        social=SocialVariants(
            twitter_thread=["Tweet one.", "Tweet two."],
            linkedin_post="A LinkedIn post.",
            email_newsletter_snippet="An email snippet.",
        ),
        image=ImageResult(
            url="https://images.pexels.com/photos/1/fake.jpeg",
            photographer="Jane Doe",
            photographer_url="https://pexels.com/@jane",
            alt_text="An AI agent evaluating its own confidence",
        ),
        cost=CostReport(total_usd=0.01, total_tokens=1000, by_node=[]),
    )

    try:
        with patch("src.utils.markdown_export._download", return_value=b"fake-image-bytes"):
            written = export_markdown(package)

        article_text = open(written["article"]).read()
        assert "Why AI Agents Need Confidence Gating" in article_text
        assert "![An AI agent evaluating its own confidence](./image.jpeg)" in article_text
        assert "Photo by [Jane Doe]" in article_text
        assert "Some body text here." in article_text

        assert open(written["image"], "rb").read() == b"fake-image-bytes"
        assert "Tweet one." in open(written["twitter_thread"]).read()
        assert "LinkedIn post" in open(written["linkedin_post"]).read()
        assert "email snippet" in open(written["email_snippet"]).read()
    finally:
        config_module.settings.output_dir = original_output_dir
