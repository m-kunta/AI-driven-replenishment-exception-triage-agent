"""Provider-agnostic LLM abstraction for the triage agent.

Supports: Claude (Anthropic), OpenAI, Gemini (Google), Ollama (local).
All providers expose a single complete(system, user) -> LLMResponse interface.

Usage:
    from src.agent.llm_provider import get_provider
    from src.utils.config_loader import load_config

    config = load_config()
    provider = get_provider(config.agent)
    response = provider.complete(system_prompt, user_prompt)

Author: Mohith Kunta <mohith.kunta@gmail.com>
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.utils.config_loader import AgentConfig


@dataclass
class LLMResponse:
    """Normalized response from any LLM provider."""
    text: str
    input_tokens: int
    output_tokens: int


class LLMProvider(ABC):
    """Abstract base class for LLM provider implementations."""

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Send a system+user prompt pair and return the response.

        Args:
            system_prompt: The system/persona prompt string.
            user_prompt: The user turn containing the exceptions to triage.

        Returns:
            LLMResponse with response text and token counts.
        """
        ...


class ClaudeProvider(LLMProvider):
    """Anthropic Claude provider via the anthropic SDK."""

    def __init__(self, api_key: str, model: str, max_tokens: int) -> None:
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "anthropic package is required for ClaudeProvider. "
                "Install it with: pip install anthropic"
            )
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        if not response.content:
            raise ValueError(
                f"ClaudeProvider received an empty content block "
                f"(stop_reason={response.stop_reason!r}). "
                "Check for content filtering or an invalid prompt."
            )
        return LLMResponse(
            text=response.content[0].text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )


class OpenAIProvider(LLMProvider):
    """OpenAI provider via the openai SDK."""

    def __init__(self, api_key: str, model: str, max_tokens: int) -> None:
        try:
            import openai
        except ImportError:
            raise ImportError(
                "openai package is required for OpenAIProvider. "
                "Install it with: pip install openai"
            )
        self._client = openai.OpenAI(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        choice = response.choices[0]
        content = choice.message.content
        if content is None:
            raise ValueError(
                f"OpenAIProvider received null content "
                f"(finish_reason={choice.finish_reason!r}). "
                "Check for content filtering or an invalid prompt."
            )
        return LLMResponse(
            text=content,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
        )


class GeminiProvider(LLMProvider):
    """Google Gemini provider via the google-generativeai SDK."""

    def __init__(self, api_key: str, model: str, max_tokens: int) -> None:
        import sys
        try:
            import google.generativeai  # noqa: F401 — ensure it's importable
        except ImportError:
            raise ImportError(
                "google-generativeai package is required for GeminiProvider. "
                "Install it with: pip install google-generativeai"
            )
        # Resolve through sys.modules so mocks applied via patch.dict are honoured
        genai = sys.modules["google.generativeai"]
        genai.configure(api_key=api_key)
        self._genai = genai
        # Store GenerationConfig at init time so complete() doesn't re-import
        self._GenerationConfig = genai.types.GenerationConfig
        self._model_name = model
        self._max_tokens = max_tokens

    def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        model = self._genai.GenerativeModel(
            model_name=self._model_name,
            system_instruction=system_prompt,
        )
        result = model.generate_content(
            user_prompt,
            generation_config=self._GenerationConfig(max_output_tokens=self._max_tokens),
        )
        input_tokens = getattr(result.usage_metadata, "prompt_token_count", 0)
        output_tokens = getattr(result.usage_metadata, "candidates_token_count", 0)
        return LLMResponse(
            text=result.text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


class OllamaProvider(LLMProvider):
    """Ollama local model provider via HTTP (uses httpx, already a project dependency)."""

    def __init__(self, base_url: str, model: str, max_tokens: int) -> None:
        import httpx
        self._client = httpx.Client(base_url=base_url, timeout=120.0)
        self._model = model
        self._max_tokens = max_tokens

    def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {"num_predict": self._max_tokens},
        }
        response = self._client.post("/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()
        return LLMResponse(
            text=data["message"]["content"],
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
        )


def get_provider(config: "AgentConfig") -> LLMProvider:
    """Factory: return the LLMProvider matching config.provider.

    Args:
        config: The AgentConfig section from the loaded AppConfig.

    Returns:
        An initialized LLMProvider ready to call complete().

    Raises:
        ValueError: If config.provider is not a supported value.
    """
    provider = config.provider.lower()
    if provider == "claude":
        return ClaudeProvider(
            api_key=config.anthropic_api_key,
            model=config.model,
            max_tokens=config.max_tokens,
        )
    if provider == "openai":
        return OpenAIProvider(
            api_key=config.openai_api_key,
            model=config.model,
            max_tokens=config.max_tokens,
        )
    if provider == "gemini":
        return GeminiProvider(
            api_key=config.gemini_api_key,
            model=config.model,
            max_tokens=config.max_tokens,
        )
    if provider == "ollama":
        return OllamaProvider(
            base_url=config.ollama_base_url,
            model=config.model,
            max_tokens=config.max_tokens,
        )
    raise ValueError(
        f"Unsupported provider: {config.provider!r}. "
        "Valid options are: claude, openai, gemini, ollama"
    )
