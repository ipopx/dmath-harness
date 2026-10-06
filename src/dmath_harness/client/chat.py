"""Thin OpenAI-compatible chat client."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from openai import APIError, OpenAI

from dmath_harness.client.config import ChatConfig


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None

    def to_dict(self) -> dict[str, int | None]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass(frozen=True)
class ChatResult:
    text: str
    usage: Usage
    latency_ms: float
    raw_finish_reason: str | None = None


class ChatClient:
    """Stateless wrapper around chat.completions.create."""

    def __init__(self, config: ChatConfig) -> None:
        self.config = config
        self._client = OpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
            timeout=config.timeout_s,
        )

    def chat(self, messages: list[dict[str, Any]]) -> ChatResult:
        started = time.perf_counter()
        try:
            response = self._client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=self.config.temperature,
            )
        except APIError as exc:
            raise RuntimeError(
                f"Chat API error for model={self.config.model!r} "
                f"at {self.config.base_url}: {exc}"
            ) from exc

        latency_ms = (time.perf_counter() - started) * 1000.0
        choice = response.choices[0]
        text = (choice.message.content or "").strip()
        usage_obj = response.usage
        usage = Usage(
            prompt_tokens=getattr(usage_obj, "prompt_tokens", None) if usage_obj else None,
            completion_tokens=(
                getattr(usage_obj, "completion_tokens", None) if usage_obj else None
            ),
            total_tokens=getattr(usage_obj, "total_tokens", None) if usage_obj else None,
        )
        return ChatResult(
            text=text,
            usage=usage,
            latency_ms=latency_ms,
            raw_finish_reason=choice.finish_reason,
        )
