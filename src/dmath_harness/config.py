"""Load OpenAI-compatible chat settings from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class ChatConfig:
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.0
    timeout_s: float = 120.0


def load_config(*, env_file: str | None = ".env") -> ChatConfig:
    """Load chat client config from environment (optionally via `.env`)."""
    if env_file:
        load_dotenv(env_file)

    base_url = os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:11434/v1").rstrip("/")
    api_key = os.getenv("OPENAI_API_KEY", "ollama")
    model = os.getenv("MODEL") or os.getenv("OPENAI_MODEL")
    if not model:
        raise ValueError(
            "MODEL (or OPENAI_MODEL) must be set. "
            "See .env.example for local Ollama and CSCS defaults."
        )

    temperature = float(os.getenv("TEMPERATURE", "0"))
    timeout_s = float(os.getenv("OPENAI_TIMEOUT_S", "120"))

    return ChatConfig(
        base_url=base_url,
        api_key=api_key,
        model=model,
        temperature=temperature,
        timeout_s=timeout_s,
    )
