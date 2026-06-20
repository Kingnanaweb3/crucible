"""Unified LLM access for Crucible.

Every agent runs on Groq, but each ROLE gets its own model so the system isn't
monolithic. Addressed by role (victim / orchestrator / judge / reporter) so the
rest of the codebase never hard-codes a model name. Retries on rate limits.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

import openai
from openai import OpenAI
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings

Role = Literal["victim", "orchestrator", "judge", "reporter"]

_ROLE_MODEL: dict[Role, str] = {
    "victim": "victim_model",
    "orchestrator": "orchestrator_model",
    "reporter": "reporter_model",
    "judge": "judge_model",
}

_RETRYABLE = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.InternalServerError,
)


@dataclass(frozen=True)
class LLMResponse:
    role: Role
    model: str
    content: str


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is not set.")
    return OpenAI(api_key=settings.groq_api_key, base_url=settings.groq_base_url)


def _model_for(role: Role) -> str:
    return getattr(settings, _ROLE_MODEL[role])


@retry(
    retry=retry_if_exception_type(_RETRYABLE),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(5),
    reraise=True,
)
def _create(model: str, messages: list[dict], temperature: float):
    return _client().chat.completions.create(
        model=model, messages=messages, temperature=temperature
    )


def chat(role: Role, messages: list[dict], temperature: float = 0.2) -> LLMResponse:
    model = _model_for(role)
    completion = _create(model, messages, temperature)
    content = (completion.choices[0].message.content or "").strip()
    return LLMResponse(role=role, model=model, content=content)


def ask(role: Role, prompt: str, system: str | None = None, **kwargs) -> str:
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return chat(role, messages, **kwargs).content
