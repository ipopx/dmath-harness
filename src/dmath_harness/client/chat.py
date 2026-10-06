"""Thin OpenAI-compatible chat client."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
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
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON string from the model


@dataclass(frozen=True)
class ChatResult:
    text: str
    usage: Usage
    latency_ms: float
    raw_finish_reason: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    assistant_message: dict[str, Any] = field(default_factory=dict)


def _parse_tool_calls(message: Any) -> list[ToolCall]:
    raw = getattr(message, "tool_calls", None) or []
    parsed: list[ToolCall] = []
    for tc in raw:
        fn = getattr(tc, "function", None)
        if fn is None:
            continue
        parsed.append(
            ToolCall(
                id=str(getattr(tc, "id", "") or ""),
                name=str(getattr(fn, "name", "") or ""),
                arguments=str(getattr(fn, "arguments", "") or ""),
            )
        )
    return parsed


def _assistant_message_dict(message: Any, tool_calls: list[ToolCall]) -> dict[str, Any]:
    """OpenAI-shaped assistant message suitable for appending to conversation state."""
    content = getattr(message, "content", None)
    out: dict[str, Any] = {
        "role": "assistant",
        "content": content if content is not None else "",
    }
    if tool_calls:
        out["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": tc.arguments},
            }
            for tc in tool_calls
        ]
    return out


class ChatClient:
    """Stateless wrapper around chat.completions.create."""

    def __init__(self, config: ChatConfig) -> None:
        self.config = config
        self._client = OpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
            timeout=config.timeout_s,
        )

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResult:
        started = time.perf_counter()
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
        }
        if tools is not None:
            kwargs["tools"] = tools
        try:
            response = self._client.chat.completions.create(**kwargs)
        except APIError as exc:
            raise RuntimeError(
                f"Chat API error for model={self.config.model!r} "
                f"at {self.config.base_url}: {exc}"
            ) from exc

        latency_ms = (time.perf_counter() - started) * 1000.0
        choice = response.choices[0]
        message = choice.message
        text = (message.content or "").strip()
        tool_calls = _parse_tool_calls(message)
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
            tool_calls=tool_calls,
            assistant_message=_assistant_message_dict(message, tool_calls),
        )
