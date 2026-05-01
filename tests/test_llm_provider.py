"""Tests for the multi-provider LLM abstraction layer.

Author: Mohith Kunta <mohith.kunta@gmail.com>
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.utils.config_loader import AgentConfig


def _make_agent_config(**kwargs) -> AgentConfig:
    defaults = {
        "provider": "claude",
        "anthropic_api_key": "test-anthropic-key",
        "openai_api_key": "test-openai-key",
        "gemini_api_key": "test-gemini-key",
        "ollama_base_url": "http://localhost:11434",
        "model": "test-model",
        "max_tokens": 100,
    }
    defaults.update(kwargs)
    return AgentConfig(**defaults)


def _make_mock_google():
    """Build a sys.modules patch dict for google.genai."""
    mock_google = MagicMock()
    mock_genai = MagicMock()
    mock_types = MagicMock()
    mock_google.genai = mock_genai
    return {
        "google": mock_google,
        "google.genai": mock_genai,
        "google.genai.types": mock_types,
    }


class TestGetProviderFactory:
    def test_returns_claude_provider(self):
        from src.agent.llm_provider import ClaudeProvider, get_provider
        config = _make_agent_config(provider="claude")
        mock_anthropic = MagicMock()
        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            provider = get_provider(config)
        assert isinstance(provider, ClaudeProvider)

    def test_returns_openai_provider(self):
        from src.agent.llm_provider import OpenAIProvider, get_provider
        config = _make_agent_config(provider="openai")
        mock_openai = MagicMock()
        with patch.dict("sys.modules", {"openai": mock_openai}):
            provider = get_provider(config)
        assert isinstance(provider, OpenAIProvider)

    def test_returns_gemini_provider(self):
        from src.agent.llm_provider import GeminiProvider, get_provider
        config = _make_agent_config(provider="gemini")
        with patch.dict("sys.modules", _make_mock_google()):
            provider = get_provider(config)
        assert isinstance(provider, GeminiProvider)

    def test_returns_ollama_provider(self):
        from src.agent.llm_provider import OllamaProvider, get_provider
        config = _make_agent_config(provider="ollama")
        provider = get_provider(config)
        assert isinstance(provider, OllamaProvider)

    def test_raises_for_unsupported_provider(self):
        from src.agent.llm_provider import get_provider
        config = _make_agent_config(provider="unknown-llm")
        with pytest.raises(ValueError, match="Unsupported provider"):
            get_provider(config)

    def test_provider_name_is_case_insensitive(self):
        from src.agent.llm_provider import ClaudeProvider, get_provider
        config = _make_agent_config(provider="CLAUDE")
        mock_anthropic = MagicMock()
        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            provider = get_provider(config)
        assert isinstance(provider, ClaudeProvider)


class TestPlaceholderKeyRejection:
    def test_claude_rejects_placeholder_key(self):
        from src.agent.llm_provider import ClaudeProvider
        mock_anthropic = MagicMock()
        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            with pytest.raises(ValueError, match="placeholder"):
                ClaudeProvider(api_key="your_anthropic_api_key_here", model="m", max_tokens=100)

    def test_openai_rejects_placeholder_key(self):
        from src.agent.llm_provider import OpenAIProvider
        mock_openai = MagicMock()
        with patch.dict("sys.modules", {"openai": mock_openai}):
            with pytest.raises(ValueError, match="placeholder"):
                OpenAIProvider(api_key="your_openai_api_key_here", model="m", max_tokens=100)

    def test_gemini_rejects_placeholder_key(self):
        from src.agent.llm_provider import GeminiProvider
        with patch.dict("sys.modules", _make_mock_google()):
            with pytest.raises(ValueError, match="placeholder"):
                GeminiProvider(api_key="your_gemini_api_key_here", model="m", max_tokens=100)

    def test_empty_key_rejected(self):
        from src.agent.llm_provider import ClaudeProvider
        mock_anthropic = MagicMock()
        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            with pytest.raises(ValueError, match="placeholder"):
                ClaudeProvider(api_key="", model="m", max_tokens=100)


class TestClaudeProvider:
    def test_complete_returns_llm_response(self):
        from src.agent.llm_provider import ClaudeProvider, LLMResponse
        mock_anthropic = MagicMock()
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="triage result text")]
        mock_msg.usage.input_tokens = 120
        mock_msg.usage.output_tokens = 55
        mock_anthropic.Anthropic.return_value.messages.create.return_value = mock_msg

        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            provider = ClaudeProvider(api_key="key", model="claude-test", max_tokens=200)
            result = provider.complete("system prompt", "user prompt")

        assert isinstance(result, LLMResponse)
        assert result.text == "triage result text"
        assert result.input_tokens == 120
        assert result.output_tokens == 55

    def test_complete_passes_correct_arguments(self):
        from src.agent.llm_provider import ClaudeProvider
        mock_anthropic = MagicMock()
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="ok")]
        mock_msg.usage.input_tokens = 10
        mock_msg.usage.output_tokens = 5
        mock_client = mock_anthropic.Anthropic.return_value
        mock_client.messages.create.return_value = mock_msg

        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            provider = ClaudeProvider(api_key="my-key", model="claude-opus", max_tokens=500)
            provider.complete("sys", "usr")

        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-opus"
        assert call_kwargs["max_tokens"] == 500
        assert call_kwargs["system"] == "sys"
        assert call_kwargs["messages"] == [{"role": "user", "content": "usr"}]

    def test_model_not_found_raises_helpful_error(self):
        from src.agent.llm_provider import ClaudeProvider
        mock_anthropic = MagicMock()
        mock_client = mock_anthropic.Anthropic.return_value
        mock_client.messages.create.side_effect = Exception("404 model: bad-model is not found")

        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            provider = ClaudeProvider(api_key="valid-key", model="bad-model", max_tokens=100)
            with pytest.raises(ValueError, match="not found"):
                provider.complete("sys", "usr")

    def test_invalid_key_raises_helpful_error(self):
        from src.agent.llm_provider import ClaudeProvider
        mock_anthropic = MagicMock()
        mock_client = mock_anthropic.Anthropic.return_value
        mock_client.messages.create.side_effect = Exception("401 invalid x-api-key")

        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            provider = ClaudeProvider(api_key="valid-key", model="m", max_tokens=100)
            with pytest.raises(ValueError, match="invalid or expired"):
                provider.complete("sys", "usr")


class TestOpenAIProvider:
    def test_complete_returns_llm_response(self):
        from src.agent.llm_provider import LLMResponse, OpenAIProvider
        mock_openai = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "openai result"
        mock_response.usage.prompt_tokens = 80
        mock_response.usage.completion_tokens = 40
        mock_openai.OpenAI.return_value.chat.completions.create.return_value = mock_response

        with patch.dict("sys.modules", {"openai": mock_openai}):
            provider = OpenAIProvider(api_key="sk-test", model="gpt-4o", max_tokens=200)
            result = provider.complete("system", "user")

        assert isinstance(result, LLMResponse)
        assert result.text == "openai result"
        assert result.input_tokens == 80
        assert result.output_tokens == 40

    def test_complete_sends_system_as_message(self):
        from src.agent.llm_provider import OpenAIProvider
        mock_openai = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "ok"
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_client = mock_openai.OpenAI.return_value
        mock_client.chat.completions.create.return_value = mock_response

        with patch.dict("sys.modules", {"openai": mock_openai}):
            provider = OpenAIProvider(api_key="key", model="gpt-4o-mini", max_tokens=100)
            provider.complete("the system prompt", "the user prompt")

        messages = mock_client.chat.completions.create.call_args[1]["messages"]
        assert messages[0] == {"role": "system", "content": "the system prompt"}
        assert messages[1] == {"role": "user", "content": "the user prompt"}

    def test_uses_max_completion_tokens(self):
        from src.agent.llm_provider import OpenAIProvider
        mock_openai = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "ok"
        mock_response.usage.prompt_tokens = 5
        mock_response.usage.completion_tokens = 3
        mock_client = mock_openai.OpenAI.return_value
        mock_client.chat.completions.create.return_value = mock_response

        with patch.dict("sys.modules", {"openai": mock_openai}):
            provider = OpenAIProvider(api_key="key", model="gpt-4.1", max_tokens=512)
            provider.complete("sys", "usr")

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert "max_completion_tokens" in call_kwargs
        assert call_kwargs["max_completion_tokens"] == 512

    def test_model_not_found_raises_helpful_error(self):
        from src.agent.llm_provider import OpenAIProvider
        mock_openai = MagicMock()
        mock_client = mock_openai.OpenAI.return_value
        mock_client.chat.completions.create.side_effect = Exception("404 model does not exist")

        with patch.dict("sys.modules", {"openai": mock_openai}):
            provider = OpenAIProvider(api_key="sk-valid", model="bad-model", max_tokens=100)
            with pytest.raises(ValueError, match="not found"):
                provider.complete("sys", "usr")

    def test_list_models_surfaces_invalid_key_error(self):
        from src.agent.llm_provider import OpenAIProvider
        mock_openai = MagicMock()
        mock_client = mock_openai.OpenAI.return_value
        mock_client.models.list.side_effect = Exception("401 invalid_api_key")

        with patch.dict("sys.modules", {"openai": mock_openai}):
            provider = OpenAIProvider(api_key="sk-valid", model="gpt-4.1", max_tokens=100)
            with pytest.raises(ValueError, match="invalid or expired"):
                provider.list_models()


class TestGeminiProvider:
    def _make_provider(self, mock_modules=None):
        from src.agent.llm_provider import GeminiProvider
        modules = mock_modules or _make_mock_google()
        with patch.dict("sys.modules", modules):
            provider = GeminiProvider(api_key="gm-key", model="gemini-2.0-flash", max_tokens=200)
        return provider, modules

    def test_complete_returns_llm_response(self):
        from src.agent.llm_provider import GeminiProvider, LLMResponse
        modules = _make_mock_google()
        mock_result = MagicMock()
        mock_result.text = "gemini result"
        mock_result.candidates = [MagicMock()]
        mock_result.usage_metadata.prompt_token_count = 60
        mock_result.usage_metadata.candidates_token_count = 30

        with patch.dict("sys.modules", modules):
            provider = GeminiProvider(api_key="gm-key", model="gemini-2.0-flash", max_tokens=200)
            modules["google.genai"].Client.return_value.models.generate_content.return_value = mock_result
            result = provider.complete("system", "user")

        assert isinstance(result, LLMResponse)
        assert result.text == "gemini result"
        assert result.input_tokens == 60
        assert result.output_tokens == 30

    def test_quota_exceeded_raises_helpful_error(self):
        from src.agent.llm_provider import GeminiProvider
        modules = _make_mock_google()

        with patch.dict("sys.modules", modules):
            provider = GeminiProvider(api_key="gm-key", model="gemini-2.0-flash", max_tokens=200)
            provider._client.models.generate_content.side_effect = Exception("429 quota exceeded")
            with pytest.raises(ValueError, match="quota exceeded"):
                provider.complete("sys", "usr")

    def test_model_not_found_raises_helpful_error(self):
        from src.agent.llm_provider import GeminiProvider
        modules = _make_mock_google()

        with patch.dict("sys.modules", modules):
            provider = GeminiProvider(api_key="gm-key", model="bad-model", max_tokens=200)
            provider._client.models.generate_content.side_effect = Exception("404 not found")
            with pytest.raises(ValueError, match="not found"):
                provider.complete("sys", "usr")

    def test_list_models_surfaces_quota_error(self):
        from src.agent.llm_provider import GeminiProvider
        modules = _make_mock_google()

        with patch.dict("sys.modules", modules):
            provider = GeminiProvider(api_key="gm-key", model="gemini-2.0-flash", max_tokens=200)
            provider._client.models.list.side_effect = Exception("429 quota exceeded")
            with pytest.raises(ValueError, match="quota exceeded"):
                provider.list_models()


class TestOllamaProvider:
    def test_complete_returns_llm_response(self):
        from src.agent.llm_provider import LLMResponse, OllamaProvider
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "message": {"content": "ollama result"},
                "prompt_eval_count": 70,
                "eval_count": 35,
            }
            mock_client.post.return_value = mock_response

            provider = OllamaProvider(base_url="http://localhost:11434", model="llama3.2", max_tokens=200)
            result = provider.complete("system", "user")

        assert isinstance(result, LLMResponse)
        assert result.text == "ollama result"
        assert result.input_tokens == 70
        assert result.output_tokens == 35

    def test_complete_sends_system_and_user_messages(self):
        from src.agent.llm_provider import OllamaProvider
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "message": {"content": "ok"},
                "prompt_eval_count": 5,
                "eval_count": 3,
            }
            mock_client.post.return_value = mock_response

            provider = OllamaProvider(base_url="http://localhost:11434", model="llama3.2", max_tokens=100)
            provider.complete("sys prompt", "usr prompt")

        payload = mock_client.post.call_args[1]["json"]
        assert payload["messages"][0] == {"role": "system", "content": "sys prompt"}
        assert payload["messages"][1] == {"role": "user", "content": "usr prompt"}
        assert payload["stream"] is False

    def test_connection_error_raises_helpful_message(self):
        from src.agent.llm_provider import OllamaProvider
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.post.side_effect = Exception("connection refused")

            provider = OllamaProvider(base_url="http://localhost:11434", model="llama3.2", max_tokens=100)
            with pytest.raises(ValueError, match="Cannot connect to Ollama"):
                provider.complete("sys", "usr")

    def test_model_not_pulled_raises_helpful_message(self):
        from src.agent.llm_provider import OllamaProvider
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.post.side_effect = Exception("404 not found")

            provider = OllamaProvider(base_url="http://localhost:11434", model="llama3.2", max_tokens=100)
            with pytest.raises(ValueError, match="ollama pull"):
                provider.complete("sys", "usr")

    def test_list_models_surfaces_connection_error(self):
        from src.agent.llm_provider import OllamaProvider
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.get.side_effect = Exception("connection refused")

            provider = OllamaProvider(base_url="http://localhost:11434", model="llama3.2", max_tokens=100)
            with pytest.raises(ValueError, match="Cannot connect to Ollama"):
                provider.list_models()
