"""LLM interface for reasoning tasks.

Provides a unified interface for:
- Claude (Anthropic API)
- Gemini (Google API)
- DeepSeek / Qwen (OpenAI-compatible API or local)

Used by Stage 2 (argument extraction), Stage 3 (prediction/matching),
Stage 4 (discussion analysis), and the Review Agent.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class LLMBackend(ABC):
    """Abstract base for text-only LLM inference."""

    @abstractmethod
    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str:
        """Generate a completion given system and user prompts."""
        ...

    def chain(
        self,
        system_prompt: str,
        prompts: list[str],
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> list[str]:
        """Run a chain of prompts, each seeing the previous response.

        Returns list of responses (one per prompt).
        """
        responses: list[str] = []
        accumulated_context = ""

        for i, prompt in enumerate(prompts):
            if accumulated_context:
                full_prompt = (
                    f"Previous analysis:\n{accumulated_context}\n\n"
                    f"Now: {prompt}"
                )
            else:
                full_prompt = prompt

            response = self.complete(system_prompt, full_prompt, temperature, max_tokens)
            responses.append(response)
            accumulated_context += f"\n\n--- Step {i + 1} ---\n{response}"

        return responses


# ─── Anthropic Claude ───────────────────────────────────────────

class ClaudeLLM(LLMBackend):
    """Claude via Anthropic API."""

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str:
        client = self._get_client()
        response = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text


# ─── Google Gemini ──────────────────────────────────────────────

class GeminiLLM(LLMBackend):
    """Gemini via Google API."""

    def __init__(self, model: str = "gemini-2.5-pro"):
        self.model = model

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str:
        try:
            import google.genai as genai
            client = genai.Client()
            response = client.models.generate_content(
                model=self.model,
                contents=f"{system_prompt}\n\n{user_prompt}",
                config={"temperature": temperature, "max_output_tokens": max_tokens},
            )
            return response.text
        except ImportError:
            raise RuntimeError("Gemini requires: pip install google-genai")


# ─── OpenAI-Compatible (DeepSeek, Qwen, local vLLM) ────────────

class OpenAICompatibleLLM(LLMBackend):
    """OpenAI-compatible API (works with DeepSeek, Qwen, vLLM, etc.)."""

    def __init__(
        self,
        model: str = "deepseek-chat",
        base_url: str | None = None,
        api_key: str | None = None,
    ):
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self._client = None

    def _get_client(self):
        if self._client is None:
            import openai
            kwargs: dict[str, Any] = {}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            if self.api_key:
                kwargs["api_key"] = self.api_key
            self._client = openai.OpenAI(**kwargs)
        return self._client

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str:
        client = self._get_client()
        response = client.chat.completions.create(
            model=self.model,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or ""


# ─── Factory ────────────────────────────────────────────────────

def create_llm_backend(model_name: str, **kwargs) -> LLMBackend:
    """Create an LLM backend by model name from config."""
    if "claude" in model_name.lower():
        model_id = {
            "claude-sonnet-4": "claude-sonnet-4-20250514",
            "claude-opus-4.6": "claude-opus-4-6",
        }.get(model_name, model_name)
        return ClaudeLLM(model=model_id, **kwargs)

    elif "gemini" in model_name.lower():
        return GeminiLLM(model=model_name, **kwargs)

    elif "openrouter" in model_name.lower() or "qwen/" in model_name.lower():
        # OpenRouter: qwen/qwen3.6-plus:free etc.
        import os
        return OpenAICompatibleLLM(
            model=model_name,
            base_url=kwargs.get("base_url", "https://openrouter.ai/api/v1"),
            api_key=kwargs.get("api_key", os.getenv("OPENROUTER_API_KEY", "")),
        )

    elif "deepseek" in model_name.lower():
        return OpenAICompatibleLLM(
            model=model_name,
            base_url=kwargs.get("base_url", "https://api.deepseek.com"),
            **{k: v for k, v in kwargs.items() if k != "base_url"},
        )

    else:
        # Default to OpenAI-compatible (local vLLM, Ollama text, etc.)
        return OpenAICompatibleLLM(model=model_name, **kwargs)
