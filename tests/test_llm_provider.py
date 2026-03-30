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
        mock_genai = MagicMock()
        with patch.dict("sys.modules", {"google.generativeai": mock_genai, "google": MagicMock()}):
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


class TestGeminiProvider:
    def test_complete_returns_llm_response(self):
        from src.agent.llm_provider import GeminiProvider, LLMResponse
        mock_genai = MagicMock()
        mock_result = MagicMock()
        mock_result.text = "gemini result"
        mock_result.usage_metadata.prompt_token_count = 60
        mock_result.usage_metadata.candidates_token_count = 30
        mock_genai.GenerativeModel.return_value.generate_content.return_value = mock_result

        with patch.dict("sys.modules", {"google.generativeai": mock_genai, "google": MagicMock()}):
            provider = GeminiProvider(api_key="gm-key", model="gemini-1.5-pro", max_tokens=200)
            result = provider.complete("system", "user")

        assert isinstance(result, LLMResponse)
        assert result.text == "gemini result"
        assert result.input_tokens == 60
        assert result.output_tokens == 30


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

            provider = OllamaProvider(base_url="http://localhost:11434", model="llama3", max_tokens=200)
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

            provider = OllamaProvider(base_url="http://localhost:11434", model="llama3", max_tokens=100)
            provider.complete("sys prompt", "usr prompt")

        payload = mock_client.post.call_args[1]["json"]
        assert payload["messages"][0] == {"role": "system", "content": "sys prompt"}
        assert payload["messages"][1] == {"role": "user", "content": "usr prompt"}
        assert payload["stream"] is False
