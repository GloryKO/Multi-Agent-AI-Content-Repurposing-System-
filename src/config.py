"""
Central configuration. All tunables live here so nothing is hardcoded
in the agent/client code. Loaded from environment variables / .env file.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- LLM ---
    # Works with OpenAI directly, or with OpenRouter by pointing base_url
    # at OpenRouter and using an OpenRouter key. Keeping this generic means
    # you can swap providers without touching agent code.
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_summarizer_model: str = "gpt-4o-mini"  # cheaper model is fine for summarization

    # --- External data sources ---
    firecrawl_api_key: str = ""
    serper_api_key: str = ""
    pexels_api_key: str = ""

    # --- Retry / resilience ---
    max_retries: int = 4
    retry_min_wait_seconds: float = 1.0
    retry_max_wait_seconds: float = 20.0

    # --- Pipeline behaviour ---
    # Only pay for a summarization LLM call when the scraped content
    # actually risks blowing the context budget of downstream calls.
    summarize_token_threshold: int = 6000
    chunk_size_tokens: int = 3000
    seo_score_threshold: float = 0.75
    max_critique_loops: int = 2

    # --- Caching (avoids burning free-tier API credits during dev) ---
    cache_dir: str = ".cache"
    cache_enabled: bool = True

    # --- Persistence ---
    # Every completed run's final package is saved here as JSON, so a
    # run survives past the process that generated it (the in-memory
    # RUNS dict in main.py does not).
    output_dir: str = "outputs"

    # --- Observability ---
    log_level: str = "INFO"
    json_logs: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
