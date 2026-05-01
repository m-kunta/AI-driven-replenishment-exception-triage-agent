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
from typing import TYPE_CHECKING, List

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

    def list_models(self) -> List[str]:
        """Return available model IDs for this provider (best-effort).

        Implementations should query the provider API and return a sorted list
        of model IDs. Returns an empty list if the API is unreachable or the
        provider does not support model enumeration.
        """
        return []


def _check_placeholder(key: str, var_name: str) -> None:
    """Raise a clear error if the API key is still the .env.example placeholder."""
    if not key or key.startswith("your_") or key.endswith("_here"):
        raise ValueError(
            f"{var_name} looks like a placeholder value. "
            f"Set a real API key in your .env file before running the pipeline."
        )


class ClaudeProvider(LLMProvider):
    """Anthropic Claude provider via the anthropic SDK."""

    def __init__(self, api_key: str, model: str, max_tokens: int) -> None:
        _check_placeholder(api_key, "ANTHROPIC_API_KEY")
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
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
        except Exception as e:
            msg = str(e)
            if "model" in msg.lower() and ("not found" in msg.lower() or "404" in msg):
                raise ValueError(
                    f"Claude model {self._model!r} was not found. "
                    f"Set AGENT_MODEL in your .env to a valid model. "
                    f"Check available models at: https://docs.anthropic.com/en/docs/about-claude/models"
                ) from e
            if "401" in msg or "authentication" in msg.lower() or "invalid x-api-key" in msg.lower():
                raise ValueError(
                    "ANTHROPIC_API_KEY is invalid or expired. "
                    "Update it in your .env file."
                ) from e
            raise
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

    def _normalize_error(self, error: Exception, *, context: str) -> ValueError | Exception:
        msg = str(error)
        if "model" in msg.lower() and ("not found" in msg.lower() or "404" in msg):
            return ValueError(
                f"Claude model {self._model!r} was not found while {context}. "
                "Set AGENT_MODEL in your .env to a valid model. "
                "Check available models at: https://docs.anthropic.com/en/docs/about-claude/models"
            )
        if "401" in msg or "authentication" in msg.lower() or "invalid x-api-key" in msg.lower():
            return ValueError(
                "ANTHROPIC_API_KEY is invalid or expired. "
                "Update it in your .env file."
            )
        return error

    def list_models(self) -> List[str]:
        """Return available Claude model IDs from the Anthropic API."""
        try:
            models = self._client.models.list()
            return sorted(m.id for m in models.data)
        except Exception as e:
            raise self._normalize_error(e, context="listing available models") from e


class OpenAIProvider(LLMProvider):
    """OpenAI provider via the openai SDK."""

    def __init__(self, api_key: str, model: str, max_tokens: int) -> None:
        _check_placeholder(api_key, "OPENAI_API_KEY")
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
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                max_completion_tokens=self._max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except Exception as e:
            msg = str(e)
            if "model" in msg.lower() and ("not found" in msg.lower() or "404" in msg or "does not exist" in msg.lower()):
                raise ValueError(
                    f"OpenAI model {self._model!r} was not found. "
                    f"Set AGENT_MODEL in your .env to a valid model (e.g. gpt-4.1, gpt-4o). "
                    f"Check available models at: https://platform.openai.com/docs/models"
                ) from e
            if "401" in msg or "incorrect api key" in msg.lower() or "invalid_api_key" in msg.lower():
                raise ValueError(
                    "OPENAI_API_KEY is invalid or expired. "
                    "Update it in your .env file."
                ) from e
            raise
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

    def _normalize_error(self, error: Exception, *, context: str) -> ValueError | Exception:
        msg = str(error)
        if "model" in msg.lower() and ("not found" in msg.lower() or "404" in msg or "does not exist" in msg.lower()):
            return ValueError(
                f"OpenAI model {self._model!r} was not found while {context}. "
                "Set AGENT_MODEL in your .env to a valid model (e.g. gpt-4.1, gpt-4o). "
                "Check available models at: https://platform.openai.com/docs/models"
            )
        if "401" in msg or "incorrect api key" in msg.lower() or "invalid_api_key" in msg.lower():
            return ValueError(
                "OPENAI_API_KEY is invalid or expired. "
                "Update it in your .env file."
            )
        return error

    def list_models(self) -> List[str]:
        """Return available OpenAI model IDs (filters to GPT/o-series chat models)."""
        try:
            all_models = self._client.models.list()
            chat_prefixes = ("gpt-", "o1", "o3", "o4", "chatgpt-")
            ids = [
                m.id for m in all_models.data
                if any(m.id.startswith(p) for p in chat_prefixes)
            ]
            return sorted(ids)
        except Exception as e:
            raise self._normalize_error(e, context="listing available models") from e


class GeminiProvider(LLMProvider):
    """Google Gemini provider via the google-genai SDK (v1+)."""

    def __init__(self, api_key: str, model: str, max_tokens: int) -> None:
        _check_placeholder(api_key, "GEMINI_API_KEY")
        try:
            from google import genai
            from google.genai import types as genai_types
        except ImportError:
            raise ImportError(
                "google-genai package is required for GeminiProvider. "
                "Install it with: pip install google-genai"
            )
        self._client = genai.Client(api_key=api_key)
        self._types = genai_types
        self._model = model
        self._max_tokens = max_tokens

    def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=user_prompt,
                config=self._types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    max_output_tokens=self._max_tokens,
                ),
            )
        except Exception as e:
            msg = str(e)
            if "not found" in msg.lower() or "404" in msg:
                raise ValueError(
                    f"Gemini model {self._model!r} was not found. "
                    f"Set AGENT_MODEL in your .env (e.g. gemini-2.0-flash, gemini-1.5-flash). "
                    f"List available models: https://ai.google.dev/gemini-api/docs/models"
                ) from e
            if "429" in msg or "quota" in msg.lower() or "rate" in msg.lower():
                raise ValueError(
                    f"Gemini API quota exceeded for model {self._model!r}. "
                    "Upgrade your Google AI plan or switch to a different provider."
                ) from e
            if "401" in msg or "api_key" in msg.lower() or "invalid" in msg.lower():
                raise ValueError(
                    "GEMINI_API_KEY is invalid or expired. "
                    "Update it in your .env file."
                ) from e
            raise

        if not response.candidates:
            raise ValueError(
                "GeminiProvider received an empty response (no candidates). "
                "Check for content filtering or an invalid prompt."
            )
        text = response.text
        if not text:
            finish_reason = str(response.candidates[0].finish_reason) if response.candidates else "unknown"
            raise ValueError(
                f"GeminiProvider received an empty response "
                f"(finish_reason={finish_reason!r}). "
                "Check for content filtering or an invalid prompt."
            )
        input_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
        output_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) or 0
        return LLMResponse(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    def _normalize_error(self, error: Exception, *, context: str) -> ValueError | Exception:
        msg = str(error)
        if "not found" in msg.lower() or "404" in msg:
            return ValueError(
                f"Gemini model {self._model!r} was not found while {context}. "
                "Set AGENT_MODEL in your .env (e.g. gemini-2.0-flash, gemini-1.5-flash). "
                "List available models: https://ai.google.dev/gemini-api/docs/models"
            )
        if "429" in msg or "quota" in msg.lower() or "rate" in msg.lower():
            return ValueError(
                f"Gemini API quota exceeded for model {self._model!r}. "
                "Upgrade your Google AI plan or switch to a different provider."
            )
        if "401" in msg or "api_key" in msg.lower() or "invalid" in msg.lower():
            return ValueError(
                "GEMINI_API_KEY is invalid or expired. "
                "Update it in your .env file."
            )
        return error

    def list_models(self) -> List[str]:
        """Return available Gemini model IDs that support generateContent."""
        try:
            models = self._client.models.list()
            ids = [
                m.name.removeprefix("models/")
                for m in models
                if hasattr(m, "supported_actions") and "generateContent" in (m.supported_actions or [])
                or hasattr(m, "name") and "gemini" in m.name.lower()
            ]
            return sorted(set(ids))
        except Exception as e:
            raise self._normalize_error(e, context="listing available models") from e


class OllamaProvider(LLMProvider):
    """Ollama local model provider via HTTP (uses httpx, already a project dependency)."""

    def __init__(self, base_url: str, model: str, max_tokens: int) -> None:
        import httpx
        self._base_url = base_url
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
        try:
            response = self._client.post("/api/chat", json=payload)
            response.raise_for_status()
        except Exception as e:
            msg = str(e)
            if "connection" in msg.lower() or "connect" in msg.lower():
                raise ValueError(
                    f"Cannot connect to Ollama at {self._base_url}. "
                    "Make sure Ollama is running: https://ollama.com"
                ) from e
            if "404" in msg or "not found" in msg.lower():
                raise ValueError(
                    f"Ollama model {self._model!r} is not available locally. "
                    f"Pull it first with: ollama pull {self._model}"
                ) from e
            raise
        data = response.json()
        content = data.get("message", {}).get("content")
        if not content:
            raise ValueError(
                "OllamaProvider received an empty or missing message.content. "
                f"Raw response keys: {list(data.keys())}"
            )
        return LLMResponse(
            text=content,
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
        )

    def _normalize_error(self, error: Exception, *, context: str) -> ValueError | Exception:
        msg = str(error)
        if "connection" in msg.lower() or "connect" in msg.lower():
            return ValueError(
                f"Cannot connect to Ollama at {self._base_url} while {context}. "
                "Make sure Ollama is running: https://ollama.com"
            )
        if "404" in msg or "not found" in msg.lower():
            return ValueError(
                f"Ollama model {self._model!r} is not available locally. "
                f"Pull it first with: ollama pull {self._model}"
            )
        return error

    def list_models(self) -> List[str]:
        """Return locally available Ollama model names via GET /api/tags."""
        try:
            response = self._client.get("/api/tags")
            data = response.json()
            return sorted(m["name"] for m in data.get("models", []))
        except Exception as e:
            raise self._normalize_error(e, context="listing available models") from e


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
