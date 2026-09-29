"""
Single choke point for every LLM call. Two things live here on
purpose, together: Instructor (for structured, validated output) and
the retry policy (because "the model returned malformed JSON" is a
transient failure mode worth retrying, not a hard error).
"""
from __future__ import annotations

from typing import Type, TypeVar

import instructor
from openai import OpenAI
from pydantic import BaseModel
from tenacity import RetryError

from src.config import settings
from src.utils.retry import UpstreamFailure, exhausted, with_retries

T = TypeVar("T", bound=BaseModel)

_raw_client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
client = instructor.from_openai(_raw_client, mode=instructor.Mode.JSON)


@with_retries(exceptions=(Exception,))
def _call(model: str, messages: list[dict], response_model: Type[T]) -> tuple[T, dict]:
    resp, completion = client.chat.completions.create_with_completion(
        model=model,
        messages=messages,
        response_model=response_model,
    )
    usage = {
        "input_tokens": completion.usage.prompt_tokens if completion.usage else 0,
        "output_tokens": completion.usage.completion_tokens if completion.usage else 0,
    }
    return resp, usage


def generate_structured(
    system_prompt: str,
    user_prompt: str,
    response_model: Type[T],
    model: str | None = None,
) -> tuple[T, dict]:
    """
    Returns (parsed_pydantic_object, token_usage_dict). Raises
    UpstreamFailure if the LLM keeps failing after every retry.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    try:
        return _call(model or settings.llm_model, messages, response_model)
    except RetryError as e:
        raise exhausted(e, "LLM") from e
    except Exception as e:  # noqa: BLE001 - last line of defense, re-raise typed
        raise UpstreamFailure(f"LLM call failed: {e}") from e
