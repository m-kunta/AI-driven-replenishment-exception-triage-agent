# Phase 4: AI Prompt System + Multi-Provider LLM Abstraction

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the AI prompt system (Tasks 4.1 and 4.2) and refactor the agent config to support Claude, OpenAI, Gemini, and Ollama interchangeably through a single provider abstraction.

**Architecture:** A provider-agnostic `LLMProvider` ABC isolates all model-specific API calls behind a single `complete(system, user) -> LLMResponse` interface. The prompt system composes a rich system prompt from 6 modular Markdown files and a few-shot JSON library, and formats each enriched exception into a structured text block for the user prompt.

**Tech Stack:** Python 3.9+, Pydantic v2, anthropic SDK, openai SDK, google-generativeai SDK, httpx (Ollama), pytest, unittest.mock

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `config/config.yaml` | Modify | Add `provider`, `openai_api_key`, `gemini_api_key`, `ollama_base_url` to `agent` section |
| `src/utils/config_loader.py` | Modify | Extend `AgentConfig` with new provider fields; update `validate_required_env_vars` |
| `requirements.txt` | Modify | Add `openai>=1.0.0`, `google-generativeai>=0.8.0` |
| `src/agent/llm_provider.py` | Create | `LLMResponse` dataclass, `LLMProvider` ABC, 4 provider classes, `get_provider` factory |
| `prompts/system_prompt.md` | Create | Persona block |
| `prompts/triage_framework.md` | Create | Priority tier definitions with criteria, examples, escalation rules |
| `prompts/output_contract.md` | Create | Exact JSON output schema Claude must follow |
| `prompts/pattern_detection.md` | Create | Pattern types, thresholds, escalation rules |
| `prompts/epistemic_honesty.md` | Create | Rules for handling UNKNOWN fields and low confidence |
| `prompts/phantom_inventory.md` | Create | Phantom inventory detection signals and action language |
| `prompts/few_shot_library.json` | Create | 5 annotated examples with complete EnrichedExceptionSchema + TriageResult objects |
| `src/agent/prompt_composer.py` | Create | Loads/caches prompt files; composes system + user prompts |
| `tests/test_llm_provider.py` | Create | Tests for provider factory and all 4 provider `complete()` calls (mocked) |
| `tests/test_prompt_composer.py` | Create | Tests for composition logic, field rendering, token estimates |

---

## Task 1: Multi-Provider Config Extension

**Files:**
- Modify: `config/config.yaml`
- Modify: `src/utils/config_loader.py`
- Modify: `requirements.txt`

### Step 1.1: Add new dependencies

Open `requirements.txt`. It currently reads:

```
anthropic>=0.40.0
pydantic>=2.0.0
pyyaml>=6.0
pandas>=2.0.0
loguru>=0.7.0
httpx>=0.27.0
SQLAlchemy>=2.0.0
python-dotenv>=1.0.0
pytest>=8.0.0
responses>=0.25.0
click>=8.0.0
jsonpath-ng>=1.6.0
```

Add two lines after `anthropic>=0.40.0`:

```
openai>=1.0.0
google-generativeai>=0.8.0
```

- [ ] **Step 1.1: Edit requirements.txt**

In `requirements.txt`, replace:
```
anthropic>=0.40.0
```
with:
```
anthropic>=0.40.0
openai>=1.0.0
google-generativeai>=0.8.0
```

- [ ] **Step 1.2: Install new dependencies**

```bash
cd /Users/MKunta/AGENTS/CODE/AI-driven-replenishment-exception-triage-agent
source .venv/bin/activate
pip install openai>=1.0.0 "google-generativeai>=0.8.0"
```

Expected: Both packages install without errors. Verify with `pip show openai google-generativeai`.

- [ ] **Step 1.3: Extend config.yaml agent section**

In `config/config.yaml`, replace the entire `agent:` block:
```yaml
agent:
  anthropic_api_key: ${ANTHROPIC_API_KEY}
  model: claude-sonnet-4-20250514
  max_tokens: 4000
  batch_size: 30
  retry_attempts: 3
  retry_backoff_seconds: 5
  reasoning_trace_enabled: false       # set true to include chain-of-thought in output
  phantom_webhook_enabled: true
  phantom_webhook_url: ${PHANTOM_WEBHOOK_URL}  # optional; leave blank to disable
  pattern_threshold: 3                 # minimum exceptions to flag a pattern
```
with:
```yaml
agent:
  provider: claude                     # claude | openai | gemini | ollama
  model: claude-sonnet-4-20250514      # model name for the selected provider
  max_tokens: 4000
  batch_size: 30
  retry_attempts: 3
  retry_backoff_seconds: 5
  reasoning_trace_enabled: false       # set true to include chain-of-thought in output
  phantom_webhook_enabled: true
  phantom_webhook_url: ${PHANTOM_WEBHOOK_URL}  # optional; leave blank to disable
  pattern_threshold: 3                 # minimum exceptions to flag a pattern
  # Provider API keys — set only the one matching your selected provider
  anthropic_api_key: ${ANTHROPIC_API_KEY}
  openai_api_key: ${OPENAI_API_KEY}
  gemini_api_key: ${GEMINI_API_KEY}
  ollama_base_url: http://localhost:11434  # base URL for local Ollama instance
```

- [ ] **Step 1.4: Extend AgentConfig in config_loader.py**

In `src/utils/config_loader.py`, replace the `AgentConfig` class:
```python
class AgentConfig(BaseModel):
    anthropic_api_key: str = ""
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4000
    batch_size: int = 30
    retry_attempts: int = 3
    retry_backoff_seconds: int = 5
    reasoning_trace_enabled: bool = False
    phantom_webhook_enabled: bool = True
    phantom_webhook_url: str = ""
    pattern_threshold: int = 3
```
with:
```python
class AgentConfig(BaseModel):
    provider: str = "claude"
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4000
    batch_size: int = 30
    retry_attempts: int = 3
    retry_backoff_seconds: int = 5
    reasoning_trace_enabled: bool = False
    phantom_webhook_enabled: bool = True
    phantom_webhook_url: str = ""
    pattern_threshold: int = 3
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
```

- [ ] **Step 1.5: Update validate_required_env_vars**

In `src/utils/config_loader.py`, replace the `validate_required_env_vars` function:
```python
def validate_required_env_vars(config: AppConfig, adapter: str = "csv", alerts_enabled: bool = False) -> None:
    if not config.agent.anthropic_api_key:
        raise ConfigurationError("Missing required environment variable: ANTHROPIC_API_KEY")
    ...
```
with:
```python
def validate_required_env_vars(config: AppConfig, adapter: str = "csv", alerts_enabled: bool = False) -> None:
    """Validate that required environment variables are set based on runtime mode.

    Args:
        config: The loaded AppConfig.
        adapter: The active ingestion adapter type.
        alerts_enabled: Whether alerting is enabled.

    Raises:
        ConfigurationError: If a required env var is missing.
    """
    provider = config.agent.provider.lower()
    if provider == "claude" and not config.agent.anthropic_api_key:
        raise ConfigurationError("Missing required environment variable: ANTHROPIC_API_KEY (provider=claude)")
    elif provider == "openai" and not config.agent.openai_api_key:
        raise ConfigurationError("Missing required environment variable: OPENAI_API_KEY (provider=openai)")
    elif provider == "gemini" and not config.agent.gemini_api_key:
        raise ConfigurationError("Missing required environment variable: GEMINI_API_KEY (provider=gemini)")
    elif provider not in ("claude", "openai", "gemini", "ollama"):
        raise ConfigurationError(
            f"Invalid agent.provider: {config.agent.provider!r}. Must be one of: claude, openai, gemini, ollama"
        )

    if adapter == "api":
        if not config.ingestion.api.endpoint:
            raise ConfigurationError("Missing required environment variable: EXCEPTION_API_ENDPOINT")
        if not config.ingestion.api.api_key:
            raise ConfigurationError("Missing required environment variable: EXCEPTION_API_KEY")

    if adapter == "sql":
        if not config.ingestion.sql.connection_string:
            raise ConfigurationError("Missing required environment variable: DB_CONNECTION_STRING")
```

- [ ] **Step 1.6: Run existing tests to confirm no regressions**

```bash
cd /Users/MKunta/AGENTS/CODE/AI-driven-replenishment-exception-triage-agent
source .venv/bin/activate
pytest tests/test_ingestion.py tests/test_enrichment.py -v
```

Expected: All tests pass. If any fail, the config change broke something — check that `AgentConfig` field defaults are unchanged.

- [ ] **Step 1.7: Commit**

```bash
git add requirements.txt config/config.yaml src/utils/config_loader.py
git commit -m "feat: extend agent config for multi-provider LLM support (claude/openai/gemini/ollama)"
```

---

## Task 2: LLM Provider Abstraction

**Files:**
- Create: `src/agent/llm_provider.py`
- Create: `tests/test_llm_provider.py`

- [ ] **Step 2.1: Write the failing tests first**

Create `tests/test_llm_provider.py`:

```python
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
```

- [ ] **Step 2.2: Run tests to confirm they fail**

```bash
pytest tests/test_llm_provider.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.agent.llm_provider'` — all tests fail. Good.

- [ ] **Step 2.3: Create src/agent/llm_provider.py**

```python
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
        return LLMResponse(
            text=choice.message.content,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
        )


class GeminiProvider(LLMProvider):
    """Google Gemini provider via the google-generativeai SDK."""

    def __init__(self, api_key: str, model: str, max_tokens: int) -> None:
        try:
            import google.generativeai as genai
        except ImportError:
            raise ImportError(
                "google-generativeai package is required for GeminiProvider. "
                "Install it with: pip install google-generativeai"
            )
        genai.configure(api_key=api_key)
        self._genai = genai
        self._model_name = model
        self._max_tokens = max_tokens

    def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        from google.generativeai.types import GenerationConfig
        model = self._genai.GenerativeModel(
            model_name=self._model_name,
            system_instruction=system_prompt,
        )
        result = model.generate_content(
            user_prompt,
            generation_config=GenerationConfig(max_output_tokens=self._max_tokens),
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
```

- [ ] **Step 2.4: Run tests — they should all pass**

```bash
pytest tests/test_llm_provider.py -v
```

Expected: All 14 tests pass. If GeminiProvider tests fail due to `google` namespace, the patch needs both `google.generativeai` and `google` in sys.modules — confirm the test already does this.

- [ ] **Step 2.5: Confirm all existing tests still pass**

```bash
pytest tests/test_ingestion.py tests/test_enrichment.py -v
```

Expected: All tests pass (no regressions from config changes).

- [ ] **Step 2.6: Commit**

```bash
git add src/agent/llm_provider.py tests/test_llm_provider.py
git commit -m "feat: add multi-provider LLM abstraction (Claude, OpenAI, Gemini, Ollama)"
```

---

## Task 3: Task 4.1 — Prompt Files

**Files:**
- Create: `prompts/system_prompt.md`
- Create: `prompts/triage_framework.md`
- Create: `prompts/output_contract.md`
- Create: `prompts/pattern_detection.md`
- Create: `prompts/epistemic_honesty.md`
- Create: `prompts/phantom_inventory.md`
- Create: `prompts/few_shot_library.json`
- Create: `tests/test_prompt_files.py`

- [ ] **Step 3.1: Write prompt file validation tests first**

Create `tests/test_prompt_files.py`:

```python
"""Structural validation tests for prompt files (Task 4.1).

These tests verify that all required prompt files exist and contain
the key sections expected by the prompt composer and LLM engine.

Author: Mohith Kunta <mohith.kunta@gmail.com>
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

PROMPTS_DIR = Path("prompts")

REQUIRED_MD_FILES = [
    "system_prompt.md",
    "triage_framework.md",
    "output_contract.md",
    "pattern_detection.md",
    "epistemic_honesty.md",
    "phantom_inventory.md",
]


class TestPromptFilesExist:
    def test_all_markdown_files_exist(self):
        for filename in REQUIRED_MD_FILES:
            path = PROMPTS_DIR / filename
            assert path.exists(), f"Missing required prompt file: {path}"

    def test_few_shot_library_exists(self):
        assert (PROMPTS_DIR / "few_shot_library.json").exists()


class TestFewShotLibrary:
    @pytest.fixture
    def examples(self):
        return json.loads((PROMPTS_DIR / "few_shot_library.json").read_text())

    def test_has_exactly_five_examples(self, examples):
        assert len(examples) == 5

    def test_each_example_has_required_keys(self, examples):
        for ex in examples:
            assert "id" in ex
            assert "description" in ex
            assert "exception" in ex
            assert "correct_output" in ex
            assert "reasoning" in ex

    def test_exception_objects_have_required_fields(self, examples):
        required = [
            "exception_id", "item_id", "item_name", "store_id", "store_name",
            "exception_type", "exception_date", "units_on_hand", "days_of_supply",
            "enrichment_confidence", "missing_data_fields",
        ]
        for ex in examples:
            for field in required:
                assert field in ex["exception"], (
                    f"Example {ex['id']} exception missing field: {field}"
                )

    def test_correct_output_has_required_fields(self, examples):
        required = [
            "exception_id", "priority", "confidence", "root_cause",
            "recommended_action", "financial_impact_statement", "planner_brief",
            "compounding_risks", "missing_data_flags", "phantom_flag",
        ]
        for ex in examples:
            for field in required:
                assert field in ex["correct_output"], (
                    f"Example {ex['id']} correct_output missing field: {field}"
                )

    def test_priorities_are_valid_values(self, examples):
        valid = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
        for ex in examples:
            assert ex["correct_output"]["priority"] in valid, (
                f"Example {ex['id']} has invalid priority: {ex['correct_output']['priority']}"
            )

    def test_covers_all_priority_levels(self, examples):
        priorities = {ex["correct_output"]["priority"] for ex in examples}
        assert "CRITICAL" in priorities
        assert "HIGH" in priorities
        assert "MEDIUM" in priorities
        assert "LOW" in priorities

    def test_phantom_flag_is_false_in_all_outputs(self, examples):
        # phantom_flag is set by the webhook module, not the LLM
        for ex in examples:
            assert ex["correct_output"]["phantom_flag"] is False


class TestSystemPromptContent:
    @pytest.fixture
    def content(self):
        return (PROMPTS_DIR / "system_prompt.md").read_text()

    def test_contains_supply_chain_persona(self, content):
        assert "supply chain" in content.lower()

    def test_contains_consequence_not_magnitude_principle(self, content):
        assert "consequence" in content.lower()
        assert "magnitude" in content.lower()


class TestTriageFrameworkContent:
    @pytest.fixture
    def content(self):
        return (PROMPTS_DIR / "triage_framework.md").read_text()

    def test_contains_all_four_priority_tiers(self, content):
        for tier in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            assert tier in content

    def test_contains_escalation_rules(self, content):
        assert "escalat" in content.lower()


class TestOutputContractContent:
    @pytest.fixture
    def content(self):
        return (PROMPTS_DIR / "output_contract.md").read_text()

    def test_specifies_json_array_return(self, content):
        assert "JSON array" in content

    def test_forbids_markdown_fences(self, content):
        assert "code fence" in content.lower() or "```" in content

    def test_contains_pattern_analysis_object(self, content):
        assert "pattern_analysis" in content

    def test_contains_all_triage_result_fields(self, content):
        required_fields = [
            "exception_id", "priority", "confidence", "root_cause",
            "recommended_action", "financial_impact_statement", "planner_brief",
            "compounding_risks", "missing_data_flags", "phantom_flag",
        ]
        for field in required_fields:
            assert field in content, f"Output contract missing field spec: {field}"


class TestPatternDetectionContent:
    @pytest.fixture
    def content(self):
        return (PROMPTS_DIR / "pattern_detection.md").read_text()

    def test_contains_all_pattern_types(self, content):
        for pt in ["VENDOR", "DC_LANE", "CATEGORY", "REGION", "MACRO"]:
            assert pt in content

    def test_specifies_threshold(self, content):
        assert "3" in content  # minimum threshold


class TestEpistemicHonestyContent:
    @pytest.fixture
    def content(self):
        return (PROMPTS_DIR / "epistemic_honesty.md").read_text()

    def test_contains_unknown_handling_rules(self, content):
        assert "UNKNOWN" in content

    def test_contains_low_confidence_rules(self, content):
        assert "LOW" in content


class TestPhantomInventoryContent:
    @pytest.fixture
    def content(self):
        return (PROMPTS_DIR / "phantom_inventory.md").read_text()

    def test_contains_phantom_signal_description(self, content):
        assert "fill rate" in content.lower() or "vendor_fill_rate" in content

    def test_contains_potential_phantom_flag(self, content):
        assert "POTENTIAL_PHANTOM_INVENTORY" in content

    def test_contains_recommended_action_language(self, content):
        assert "physical count" in content.lower()
```

- [ ] **Step 3.2: Run tests to confirm they fail**

```bash
pytest tests/test_prompt_files.py -v
```

Expected: All tests fail with `AssertionError` on file existence or `FileNotFoundError`. Good.

- [ ] **Step 3.3: Create the prompts directory**

```bash
mkdir -p prompts
```

- [ ] **Step 3.4: Create prompts/system_prompt.md**

```markdown
You are a senior supply chain planner with 15 years of retail replenishment experience. You understand that the most dangerous exceptions are rarely the ones with the highest variance numbers. You think in terms of business consequence — revenue at risk, promotional commitments, vendor reliability, competitive exposure, and customer service impact. You do not sort by magnitude. You sort by consequence.

You reason carefully and systematically. You explain your thinking clearly. You flag when you are uncertain and when data is missing. You never invent data you were not given.
```

- [ ] **Step 3.5: Create prompts/triage_framework.md**

```markdown
## Triage Priority Framework

### CRITICAL

An exception is CRITICAL when immediate action is required within hours to prevent material financial harm or customer service failure.

**Criteria (any one is sufficient):**
- Item is OOS or <1.5 days of supply at a Tier 1 store with an active promo (TPR, FEATURE, BOTH)
- Item is perishable with <1.0 days of supply, regardless of store tier
- Item is OOS at a Tier 1 or Tier 2 store AND a competitor is within 2 miles AND a competitor event is active
- Item is part of a vendor pattern with 5+ exceptions from the same vendor with fill rate <80%
- ORDER_FAILURE for a Tier 1 store item with promo active and no inbound PO

**Compounding escalation to CRITICAL:**
- Any HIGH exception where ALL THREE are true: promo active + perishable + Tier 1 store

**Examples:**
1. OOS on Organic Whole Milk at a Flagship Tier 1 store with active 15% TPR and a competitor dairy promotion 0.3 miles away → CRITICAL
2. Perishable item at 0.5 days of supply at any store → CRITICAL
3. 7 vendor-late exceptions from the same distributor (fill rate 72%) → flag all CRITICAL

---

### HIGH

An exception is HIGH when same-day resolution is required to prevent significant but manageable risk.

**Criteria (any one is sufficient):**
- Item is <3.0 days of supply at a Tier 1 or Tier 2 store
- Item is OOS at a Tier 3 store with active TPR
- VENDOR_LATE exception for a Tier 1/2 store item with open promo and no alternative inbound
- Item is part of a confirmed VENDOR, DC_LANE, or CATEGORY pattern (even if individually MEDIUM)
- OOS with no inbound PO and lead time >7 days

**Examples:**
1. LOW_STOCK at 2.1 days of supply for a Tier 2 store item → HIGH
2. A MEDIUM exception joined by 4 others from the same vendor (pattern escalation) → HIGH

---

### MEDIUM

An exception is MEDIUM when same-week resolution is required. Significant but not urgent.

**Criteria:**
- OOS or LOW_STOCK at a Tier 3 store without active promo
- FORECAST_VARIANCE >25% at a Tier 1/2 store with no stock risk
- VENDOR_LATE at a Tier 3/4 store with adequate DC inventory
- Any exception with 3–7 days of supply and no compounding risk factors

**Examples:**
1. LOW_STOCK at a Tier 3 store ($280K/week), no promo, DC has 12 days supply → MEDIUM
2. FORECAST_VARIANCE of 35% at a Tier 2 store, 8 days on hand → MEDIUM

---

### LOW

An exception is LOW when it is informational only. No immediate action required.

**Criteria:**
- FORECAST_VARIANCE at a Tier 4 store, regardless of variance percentage
- OOS or LOW_STOCK at a Tier 4 store, non-perishable, no promo, DC has adequate inventory
- Any exception where enrichment_confidence is LOW and no CRITICAL signals are visible in the available data
- Exceptions representing normal replenishment cycle variation with no downstream risk

**Examples:**
1. FORECAST_VARIANCE of 45% at a Tier 4 store ($120K/week), non-perishable, 6 days on hand → LOW
2. LOW_STOCK at a Tier 4 store, vendor fill rate 95%, DC has 18 days supply → LOW

---

### Compound Risk Escalation Rules

Apply after initial priority assignment:

1. **MEDIUM → HIGH**: exception is part of a detected VENDOR, DC_LANE, CATEGORY, or REGION pattern (3+ exceptions in group)
2. **HIGH → CRITICAL**: exception is part of a pattern AND item is perishable AND promo is active
3. **Any priority → add "POTENTIAL_PHANTOM_INVENTORY" to compounding_risks** if: OOS or LOW_STOCK exception + vendor fill rate >90% + dc_inventory_days >14. Do not change priority based on phantom flag alone.
```

- [ ] **Step 3.6: Create prompts/output_contract.md**

```markdown
## Output Contract

Return the full batch as a JSON array. Do not include markdown code fences. Do not include any text before or after the JSON array.

Each element of the array must be a JSON object with exactly these fields:

```json
{
  "exception_id": "string — copy exactly from input",
  "priority": "CRITICAL | HIGH | MEDIUM | LOW",
  "confidence": "HIGH | MEDIUM | LOW — inherit from enrichment_confidence unless you have strong reason to downgrade",
  "root_cause": "string — max 30 words, specific and factual",
  "recommended_action": "string — max 25 words, one concrete action the planner can take now",
  "financial_impact_statement": "string — max 20 words, dollar amounts if available",
  "planner_brief": "string — max 75 words, context paragraph for the planner",
  "compounding_risks": ["use only: POTENTIAL_PHANTOM_INVENTORY, PROMO_COMMITMENT, COMPETITOR_EXPOSURE, VENDOR_RELIABILITY, PERISHABLE_URGENCY, DATA_INTEGRITY_RISK"],
  "missing_data_flags": ["list of field names that were UNKNOWN in input and affected your assessment"],
  "pattern_id": null,
  "escalated_from": null,
  "phantom_flag": false,
  "reasoning_trace": null
}
```

After the array of exception objects, include ONE additional JSON object as the last array element:

```json
{
  "_type": "pattern_analysis",
  "vendor_summary": {
    "VND-XXX": {"count": 0, "critical_count": 0, "high_count": 0}
  },
  "dc_summary": {
    "DC-XXX": {"count": 0}
  },
  "category_summary": {
    "CategoryName": {"count": 0}
  },
  "region_summary": {
    "RegionName": {"count": 0}
  },
  "preliminary_patterns": [
    {
      "pattern_type": "VENDOR | DC_LANE | CATEGORY | REGION | MACRO",
      "group_key": "identifier",
      "count": 0,
      "description": "one sentence describing the pattern"
    }
  ]
}
```

**Field constraints:**
- `priority`: must be exactly one of CRITICAL, HIGH, MEDIUM, LOW
- `confidence`: must be exactly one of HIGH, MEDIUM, LOW
- `root_cause`: must not exceed 30 words
- `recommended_action`: must not exceed 25 words
- `financial_impact_statement`: must not exceed 20 words
- `planner_brief`: must not exceed 75 words
- `compounding_risks`: use only flags from the allowed list; empty array if none apply
- `missing_data_flags`: list only fields that were UNKNOWN in your input
- `pattern_id`: always null — the pattern analyzer populates this after your response
- `escalated_from`: always null — the pattern analyzer populates this after your response
- `phantom_flag`: always false — the phantom webhook sets this after confirmation
- `reasoning_trace`: always null unless instructed otherwise in the user prompt
- Do NOT invent numbers not given in the input
- Do NOT use markdown formatting inside string field values
```

- [ ] **Step 3.7: Create prompts/pattern_detection.md**

```markdown
## Pattern Detection Directive

### When to Flag a Pattern

Flag a preliminary pattern when 3 or more exceptions in the current batch share the same value for any of these dimensions:

- `vendor_id` → VENDOR pattern
- `region` (same region, different vendors/categories) → REGION pattern
- `category` → CATEGORY pattern
- Multiple dimensions simultaneously → MACRO pattern

The default threshold is 3. Report what you observe in this batch in the `pattern_analysis` object.

### Pattern Types

**VENDOR:** Multiple exceptions trace to the same supplier. Signals: shared vendor_id, vendor_fill_rate_90d below 85%, correlated VENDOR_LATE exception types. Root cause: vendor capacity issue, raw material shortage, or logistics disruption.

**DC_LANE:** Multiple exceptions from stores in the same region without a vendor root cause. Root cause: DC out-of-stock, lane scheduling delay, or DC operational issue.

**CATEGORY:** Multiple exceptions clustered in a single product category across different stores and vendors. Root cause: demand spike, seasonal shift, forecast model failure, or category-wide supplier disruption.

**REGION:** Multiple exceptions concentrated in a geographic region cutting across vendors and categories. Root cause: regional demand event, weather, or competitive disruption.

**MACRO:** Exceptions spanning multiple vendors, categories, and regions simultaneously. Root cause: systemic forecasting or ordering system failure.

### Important: Do Not Apply Escalations Yourself

Report patterns in `preliminary_patterns`. The pattern analyzer module will:
- Confirm patterns with 3+ exceptions across all batches (not just this batch)
- Escalate MEDIUM exceptions to HIGH for confirmed pattern members
- Populate `pattern_id` and `escalated_from` in each TriageResult

### Pattern Analysis Object

Always include the `_type: pattern_analysis` object as the last element of your JSON array, even if no patterns are detected. If no patterns are detected, set `preliminary_patterns` to an empty array `[]`.
```

- [ ] **Step 3.8: Create prompts/epistemic_honesty.md**

```markdown
## Epistemic Honesty Rules

### Handling UNKNOWN Fields

Fields that appear as UNKNOWN in the exception template had null values in the enrichment data. Apply these rules:

**UNKNOWN store_tier:** Do not assume a tier. Flag `store_tier` in `missing_data_flags`. Treat as Tier 3 for priority purposes; state this assumption in `planner_brief`.

**UNKNOWN vendor_fill_rate_90d:** Cannot assess vendor reliability. Flag in `missing_data_flags`. Do not add VENDOR_RELIABILITY to `compounding_risks`.

**UNKNOWN dc_inventory_days:** Cannot assess replenishment coverage. Flag in `missing_data_flags`. If exception is OOS and dc_inventory_days is UNKNOWN, increase urgency and mention in `planner_brief`.

**UNKNOWN promo_type or promo_end_date when promo_active=True:** Cannot assess promotional exposure. Flag both in `missing_data_flags`. Add PROMO_COMMITMENT to `compounding_risks` to trigger human review.

**UNKNOWN competitor_proximity_miles:** Cannot assess competitive exposure. Do not add COMPETITOR_EXPOSURE to compounding_risks. Do not mention competitors in `planner_brief`.

### enrichment_confidence=LOW Rules

The record has 3 or more UNKNOWN enrichment fields.

- If available data contains CRITICAL signals (OOS at Tier 1, active promo): maintain CRITICAL priority, set `confidence` to LOW
- If available data shows no CRITICAL signals: cap priority at MEDIUM
- Always populate `missing_data_flags` with all UNKNOWN fields
- Always end `planner_brief` with: "⚠️ LOW CONFIDENCE — verify [list missing fields] before acting."

### Confidence Level Impact

- **enrichment_confidence=HIGH:** Trust the data; assign priority normally
- **enrichment_confidence=MEDIUM:** Proceed with caveats; mention 1–2 UNKNOWN fields in planner_brief
- **enrichment_confidence=LOW:** Cap at MEDIUM unless CRITICAL signals are unambiguous; always note in planner_brief

### Communication of Uncertainty

- Use "based on available data" when key fields are UNKNOWN
- Use "recommend verifying [field] before acting" when a missing field would change the priority decision
- Do NOT say "I cannot determine" — always give your best assessment with stated caveats
- Do NOT speculate about values not in the data
```

- [ ] **Step 3.9: Create prompts/phantom_inventory.md**

```markdown
## Phantom Inventory Detection

### What is Phantom Inventory?

Phantom inventory occurs when the system shows zero units on hand but physical stock is present — miscounted or mislocated. It is NOT a true replenishment failure. The item is physically available; the record is wrong.

### Signals That Suggest Phantom Inventory

A phantom inventory scenario is likely when the majority of these signals are present:

1. `exception_type` is OOS or LOW_STOCK (system shows zero or near-zero on hand)
2. `vendor_fill_rate_90d` is high (>90%) — the vendor reliably ships
3. `dc_inventory_days` is high (>14 days) — the DC has ample stock
4. `open_po_inbound` is true or lead time is short — replenishment is not blocked upstream
5. No competing explanation (regional disruption, promo surge) for the stock-out

When 3 or more of these signals are present, add "POTENTIAL_PHANTOM_INVENTORY" to `compounding_risks`.

### How to Flag

Add `"POTENTIAL_PHANTOM_INVENTORY"` to the `compounding_risks` array. This triggers the phantom webhook module.

Do NOT:
- Change `exception_type` yourself — leave it as OOS or LOW_STOCK
- Set `phantom_flag` to true — the webhook module sets this after confirmation
- Change priority solely because of phantom suspicion — the OOS or LOW_STOCK risk stands until confirmed

### Recommended Action Language for Phantom Scenarios

**recommended_action:** "Conduct physical count before placing emergency order — possible phantom inventory."

**planner_brief addition:** "Vendor fill rate of [N]% and [N] days DC inventory suggest stock may be present but miscounted. Physical count recommended before emergency replenishment."
```

- [ ] **Step 3.10: Create prompts/few_shot_library.json**

```json
[
  {
    "id": "fs_001",
    "description": "High variance, zero business risk — should be LOW",
    "exception": {
      "exception_id": "fs-001-low-variance-risk",
      "item_id": "ITM-5050",
      "item_name": "Paper Towels 6-Pack",
      "store_id": "STR-099",
      "store_name": "Rural Iowa Outlet",
      "exception_type": "FORECAST_VARIANCE",
      "exception_date": "2026-03-30",
      "units_on_hand": 48,
      "days_of_supply": 8.2,
      "variance_pct": 48.0,
      "source_system": "BlueYonder",
      "batch_id": "batch-demo",
      "ingested_at": "2026-03-30T06:00:00",
      "velocity_rank": 42,
      "category": "Paper & Cleaning",
      "subcategory": "Paper Towels",
      "retail_price": 8.99,
      "margin_pct": 22.0,
      "store_tier": 4,
      "weekly_store_sales_k": 115.0,
      "region": "Midwest",
      "promo_active": false,
      "promo_type": "NONE",
      "promo_end_date": null,
      "tpr_depth_pct": null,
      "dc_inventory_days": 31.0,
      "vendor_id": "VND-200",
      "vendor_fill_rate_90d": 96.0,
      "open_po_inbound": true,
      "next_delivery_date": "2026-04-02",
      "lead_time_days": 3,
      "competitor_proximity_miles": 18.4,
      "competitor_event": null,
      "perishable": false,
      "day_of_week_demand_index": 0.92,
      "est_lost_sales_value": 0.0,
      "promo_margin_at_risk": 0.0,
      "regional_disruption_flag": false,
      "regional_disruption_description": null,
      "missing_data_fields": [],
      "enrichment_confidence": "HIGH"
    },
    "correct_output": {
      "exception_id": "fs-001-low-variance-risk",
      "priority": "LOW",
      "confidence": "HIGH",
      "root_cause": "Forecast variance of 48% at a Tier 4 store with 8.2 days supply on hand and 31 days DC coverage.",
      "recommended_action": "No action required. Monitor next replenishment cycle.",
      "financial_impact_statement": "Zero lost sales risk; item adequately stocked.",
      "planner_brief": "Despite the 48% forecast variance flag, this exception poses no business risk. Paper Towels 6-Pack has 8.2 days of supply on hand at a Tier 4 store generating $115K/week. No promo is active, the item is non-perishable, and DC has 31 days of coverage. Vendor fill rate is 96% with a delivery arriving April 2.",
      "compounding_risks": [],
      "missing_data_flags": [],
      "pattern_id": null,
      "escalated_from": null,
      "phantom_flag": false,
      "reasoning_trace": null
    },
    "reasoning": "The 48% FORECAST_VARIANCE looks alarming but business consequence is zero. Tier 4 store, no promo, non-perishable, 8 days on hand, 31 days at DC. Magnitude is high; consequence is none. Sort by consequence, not magnitude → LOW."
  },
  {
    "id": "fs_002",
    "description": "Low variance, maximum risk — should be CRITICAL",
    "exception": {
      "exception_id": "fs-002-critical-oos-promo",
      "item_id": "ITM-1001",
      "item_name": "Organic Whole Milk 1gal",
      "store_id": "STR-001",
      "store_name": "Flagship Manhattan",
      "exception_type": "OOS",
      "exception_date": "2026-03-30",
      "units_on_hand": 0,
      "days_of_supply": 0.0,
      "variance_pct": 5.2,
      "source_system": "BlueYonder",
      "batch_id": "batch-demo",
      "ingested_at": "2026-03-30T06:00:00",
      "velocity_rank": 1,
      "category": "Dairy & Eggs",
      "subcategory": "Milk",
      "retail_price": 6.49,
      "margin_pct": 18.5,
      "store_tier": 1,
      "weekly_store_sales_k": 2100.0,
      "region": "Northeast",
      "promo_active": true,
      "promo_type": "TPR",
      "promo_end_date": "2026-04-05",
      "tpr_depth_pct": 15.0,
      "dc_inventory_days": 4.5,
      "vendor_id": "VND-101",
      "vendor_fill_rate_90d": 91.0,
      "open_po_inbound": true,
      "next_delivery_date": "2026-04-01",
      "lead_time_days": 2,
      "competitor_proximity_miles": 0.3,
      "competitor_event": "Competitor dairy promotion running through April 5",
      "perishable": true,
      "day_of_week_demand_index": 1.22,
      "est_lost_sales_value": 1847.50,
      "promo_margin_at_risk": 341.79,
      "regional_disruption_flag": false,
      "regional_disruption_description": null,
      "missing_data_fields": [],
      "enrichment_confidence": "HIGH"
    },
    "correct_output": {
      "exception_id": "fs-002-critical-oos-promo",
      "priority": "CRITICAL",
      "confidence": "HIGH",
      "root_cause": "OOS on top-velocity perishable at Tier 1 Flagship Manhattan during active TPR with competitor promotion 0.3 miles away.",
      "recommended_action": "Emergency transfer from DC or nearby store. Contact VND-101 for expedited delivery before March 31.",
      "financial_impact_statement": "$1,848 lost sales and $342 promo margin at risk through April 5.",
      "planner_brief": "Organic Whole Milk is OOS at the #1-velocity Flagship Manhattan store (Tier 1, $2.1M/week) with an active 15% TPR running through April 5. A competitor dairy promotion is active 0.3 miles away. DC has only 4.5 days of coverage; next scheduled delivery is April 1 — too late for today. Requires emergency transfer or expedited vendor shipment immediately.",
      "compounding_risks": ["PROMO_COMMITMENT", "COMPETITOR_EXPOSURE", "PERISHABLE_URGENCY"],
      "missing_data_flags": [],
      "pattern_id": null,
      "escalated_from": null,
      "phantom_flag": false,
      "reasoning_trace": null
    },
    "reasoning": "Variance percentage of 5.2% is unremarkable. Five compounding factors override it: OOS + Tier 1 + perishable + active TPR + competitor event 0.3 miles away. Business consequence is maximum → CRITICAL."
  },
  {
    "id": "fs_003",
    "description": "Vendor pattern — individually MEDIUM, flag for pattern escalation",
    "exception": {
      "exception_id": "fs-003-vendor-pattern-medium",
      "item_id": "ITM-3030",
      "item_name": "All-Purpose Cleaner 32oz",
      "store_id": "STR-022",
      "store_name": "Denver Tech Center",
      "exception_type": "VENDOR_LATE",
      "exception_date": "2026-03-30",
      "units_on_hand": 14,
      "days_of_supply": 5.1,
      "variance_pct": null,
      "source_system": "BlueYonder",
      "batch_id": "batch-demo",
      "ingested_at": "2026-03-30T06:00:00",
      "velocity_rank": 18,
      "category": "Household Cleaners",
      "subcategory": "Multi-Surface",
      "retail_price": 4.29,
      "margin_pct": 31.0,
      "store_tier": 2,
      "weekly_store_sales_k": 920.0,
      "region": "Mountain West",
      "promo_active": false,
      "promo_type": "NONE",
      "promo_end_date": null,
      "tpr_depth_pct": null,
      "dc_inventory_days": 3.2,
      "vendor_id": "VND-400",
      "vendor_fill_rate_90d": 72.0,
      "open_po_inbound": false,
      "next_delivery_date": null,
      "lead_time_days": 7,
      "competitor_proximity_miles": 3.8,
      "competitor_event": null,
      "perishable": false,
      "day_of_week_demand_index": 1.05,
      "est_lost_sales_value": 312.40,
      "promo_margin_at_risk": 0.0,
      "regional_disruption_flag": false,
      "regional_disruption_description": null,
      "missing_data_fields": [],
      "enrichment_confidence": "HIGH"
    },
    "correct_output": {
      "exception_id": "fs-003-vendor-pattern-medium",
      "priority": "MEDIUM",
      "confidence": "HIGH",
      "root_cause": "Vendor-late shipment from VND-400 (72% fill rate) with 5.1 days supply, no open PO, and DC has only 3.2 days coverage.",
      "recommended_action": "Escalate to VND-400 for delivery ETA. Check cross-dock options; DC has 3.2 days only.",
      "financial_impact_statement": "$312 lost sales at risk if stock depletes within 5 days.",
      "planner_brief": "All-Purpose Cleaner at Denver Tech Center (Tier 2, $920K/week) has 5.1 days of supply with no inbound PO from VND-400, whose 90-day fill rate is only 72%. No promo is active and item is non-perishable — prevents a higher individual priority. However, VND-400 has multiple other exceptions in this run. If the pattern analyzer confirms a vendor pattern, this exception should escalate to HIGH.",
      "compounding_risks": ["VENDOR_RELIABILITY"],
      "missing_data_flags": [],
      "pattern_id": null,
      "escalated_from": null,
      "phantom_flag": false,
      "reasoning_trace": null
    },
    "reasoning": "Individually this is MEDIUM: 5.1 days supply, no promo, non-perishable, Tier 2. The 72% fill rate and no open PO are concerning but insufficient alone for HIGH. Priority is MEDIUM before pattern escalation; the pattern analyzer will escalate to HIGH when the VND-400 cluster is confirmed across batches."
  },
  {
    "id": "fs_004",
    "description": "Phantom inventory signal — flag POTENTIAL_PHANTOM_INVENTORY, do not change type",
    "exception": {
      "exception_id": "fs-004-phantom-inventory",
      "item_id": "ITM-1001",
      "item_name": "Organic Whole Milk 1gal",
      "store_id": "STR-005",
      "store_name": "Atlanta Midtown",
      "exception_type": "OOS",
      "exception_date": "2026-03-30",
      "units_on_hand": 0,
      "days_of_supply": 0.0,
      "variance_pct": 2.1,
      "source_system": "BlueYonder",
      "batch_id": "batch-demo",
      "ingested_at": "2026-03-30T06:00:00",
      "velocity_rank": 1,
      "category": "Dairy & Eggs",
      "subcategory": "Milk",
      "retail_price": 6.49,
      "margin_pct": 18.5,
      "store_tier": 2,
      "weekly_store_sales_k": 875.0,
      "region": "Southeast",
      "promo_active": false,
      "promo_type": "NONE",
      "promo_end_date": null,
      "tpr_depth_pct": null,
      "dc_inventory_days": 35.0,
      "vendor_id": "VND-101",
      "vendor_fill_rate_90d": 97.0,
      "open_po_inbound": true,
      "next_delivery_date": "2026-03-31",
      "lead_time_days": 1,
      "competitor_proximity_miles": 2.1,
      "competitor_event": null,
      "perishable": true,
      "day_of_week_demand_index": 1.10,
      "est_lost_sales_value": 890.20,
      "promo_margin_at_risk": 0.0,
      "regional_disruption_flag": false,
      "regional_disruption_description": null,
      "missing_data_fields": [],
      "enrichment_confidence": "HIGH"
    },
    "correct_output": {
      "exception_id": "fs-004-phantom-inventory",
      "priority": "HIGH",
      "confidence": "HIGH",
      "root_cause": "System shows OOS but vendor fill rate is 97% and DC holds 35 days supply — phantom inventory strongly suspected.",
      "recommended_action": "Conduct physical count before placing emergency order — possible phantom inventory.",
      "financial_impact_statement": "$890 lost sales at risk, recoverable today if phantom inventory confirmed.",
      "planner_brief": "Organic Whole Milk shows OOS at Atlanta Midtown (Tier 2, $875K/week) yet vendor fill rate is 97% and DC holds 35 days of supply with a delivery due March 31. These signals strongly suggest the system record is wrong and physical stock is present. Conduct a physical count immediately. Do not place an emergency order until count is complete.",
      "compounding_risks": ["POTENTIAL_PHANTOM_INVENTORY", "PERISHABLE_URGENCY"],
      "missing_data_flags": [],
      "pattern_id": null,
      "escalated_from": null,
      "phantom_flag": false,
      "reasoning_trace": null
    },
    "reasoning": "OOS on a perishable at Tier 2 would normally be HIGH. But 97% vendor fill rate and 35 days DC supply contradict a true OOS — this is the phantom inventory pattern (all 4 signals present). Priority stays HIGH (perishable + Tier 2 + OOS) but POTENTIAL_PHANTOM_INVENTORY is flagged. Physical count before ordering."
  },
  {
    "id": "fs_005",
    "description": "Low confidence output — correct CRITICAL flag with LOW confidence and populated missing_data_flags",
    "exception": {
      "exception_id": "fs-005-low-confidence-critical",
      "item_id": "ITM-2020",
      "item_name": "Infant Formula Stage 1 32oz",
      "store_id": "STR-044",
      "store_name": "Phoenix Arcadia",
      "exception_type": "OOS",
      "exception_date": "2026-03-30",
      "units_on_hand": 0,
      "days_of_supply": 0.0,
      "variance_pct": null,
      "source_system": "BlueYonder",
      "batch_id": "batch-demo",
      "ingested_at": "2026-03-30T06:00:00",
      "velocity_rank": 3,
      "category": "Baby & Infant",
      "subcategory": "Infant Formula",
      "retail_price": 34.99,
      "margin_pct": null,
      "store_tier": 1,
      "weekly_store_sales_k": 1650.0,
      "region": "Southwest",
      "promo_active": true,
      "promo_type": null,
      "promo_end_date": null,
      "tpr_depth_pct": null,
      "dc_inventory_days": null,
      "vendor_id": "VND-055",
      "vendor_fill_rate_90d": null,
      "open_po_inbound": null,
      "next_delivery_date": null,
      "lead_time_days": null,
      "competitor_proximity_miles": null,
      "competitor_event": null,
      "perishable": false,
      "day_of_week_demand_index": 1.08,
      "est_lost_sales_value": 0.0,
      "promo_margin_at_risk": 0.0,
      "regional_disruption_flag": false,
      "regional_disruption_description": null,
      "missing_data_fields": ["promo_type", "promo_end_date", "dc_inventory_days", "vendor_fill_rate_90d", "open_po_inbound", "next_delivery_date", "lead_time_days", "margin_pct"],
      "enrichment_confidence": "LOW"
    },
    "correct_output": {
      "exception_id": "fs-005-low-confidence-critical",
      "priority": "CRITICAL",
      "confidence": "LOW",
      "root_cause": "OOS on infant formula at Tier 1 store during active promo with no replenishment visibility due to missing enrichment data.",
      "recommended_action": "Verify DC inventory and vendor status immediately. Confirm promo type before any emergency order.",
      "financial_impact_statement": "Financial exposure unquantifiable — margin, DC levels, and promo terms unknown.",
      "planner_brief": "Infant Formula Stage 1 is OOS at Phoenix Arcadia (Tier 1, $1.65M/week) with an active promotion. Available signals are unambiguous: OOS + Tier 1 + active promo + high-sensitivity category. However, DC inventory, vendor fill rate, inbound PO status, lead time, and promo terms are all unknown. ⚠️ LOW CONFIDENCE — verify dc_inventory_days, vendor_fill_rate_90d, open_po_inbound, lead_time_days, promo_type before acting.",
      "compounding_risks": ["PROMO_COMMITMENT"],
      "missing_data_flags": ["promo_type", "promo_end_date", "dc_inventory_days", "vendor_fill_rate_90d", "open_po_inbound", "next_delivery_date", "lead_time_days", "margin_pct"],
      "pattern_id": null,
      "escalated_from": null,
      "phantom_flag": false,
      "reasoning_trace": null
    },
    "reasoning": "Despite LOW enrichment confidence, the available signals are unambiguous: OOS + Tier 1 + active promo + infant formula (highest sensitivity category). Per epistemic honesty rules, maintain CRITICAL when CRITICAL signals are clear. Set confidence=LOW and populate all missing_data_flags. The LOW CONFIDENCE caveat must end the planner_brief."
  }
]
```

- [ ] **Step 3.11: Run prompt file tests**

```bash
pytest tests/test_prompt_files.py -v
```

Expected: All tests pass. If any content test fails, open the relevant prompt file and add the missing section.

- [ ] **Step 3.12: Commit**

```bash
git add prompts/ tests/test_prompt_files.py
git commit -m "feat: add task 4.1 prompt files — triage framework, output contract, few-shot library"
```

---

## Task 4: Task 4.2 — Prompt Composer

**Files:**
- Create: `src/agent/prompt_composer.py`
- Create: `tests/test_prompt_composer.py`

- [ ] **Step 4.1: Write the failing tests first**

Create `tests/test_prompt_composer.py`:

```python
"""Tests for the prompt composer (Task 4.2).

Verifies prompt assembly logic, field rendering, UNKNOWN handling,
and token budget compliance.

Author: Mohith Kunta <mohith.kunta@gmail.com>
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from src.models import (
    EnrichedExceptionSchema,
    EnrichmentConfidence,
    ExceptionType,
    PromoType,
)


@pytest.fixture
def prompts_dir(tmp_path: Path) -> Path:
    """Minimal prompt files for testing the composer in isolation."""
    (tmp_path / "system_prompt.md").write_text("You are a supply chain planner.")
    (tmp_path / "triage_framework.md").write_text("## Triage Framework\nCRITICAL: urgent action.")
    (tmp_path / "output_contract.md").write_text("## Output Contract\nReturn a JSON array.")
    (tmp_path / "pattern_detection.md").write_text("## Pattern Detection\nFlag 3+ exceptions.")
    (tmp_path / "epistemic_honesty.md").write_text("## Epistemic Honesty\nUNKNOWN means null.")
    (tmp_path / "phantom_inventory.md").write_text("## Phantom Inventory\nCheck fill rate.")
    few_shots = [
        {
            "id": "fs_001",
            "description": "Test example — LOW priority",
            "exception": {"exception_id": "test-exc-001"},
            "correct_output": {"priority": "LOW"},
            "reasoning": "No business risk.",
        }
    ]
    (tmp_path / "few_shot_library.json").write_text(json.dumps(few_shots))
    return tmp_path


@pytest.fixture
def composer(prompts_dir: Path):
    from src.agent.prompt_composer import PromptComposer
    return PromptComposer(prompts_dir=prompts_dir)


@pytest.fixture
def minimal_exception() -> EnrichedExceptionSchema:
    return EnrichedExceptionSchema(
        exception_id="test-exc-001",
        item_id="ITM-001",
        item_name="Test Item Alpha",
        store_id="STR-001",
        store_name="Test Store One",
        exception_type=ExceptionType.OOS,
        exception_date=date(2026, 3, 30),
        units_on_hand=0,
        days_of_supply=0.0,
        source_system="TestSystem",
        batch_id="batch-001",
        ingested_at=datetime(2026, 3, 30, 8, 0, 0),
        enrichment_confidence=EnrichmentConfidence.HIGH,
    )


@pytest.fixture
def fully_enriched_exception() -> EnrichedExceptionSchema:
    return EnrichedExceptionSchema(
        exception_id="test-exc-002",
        item_id="ITM-002",
        item_name="Organic Whole Milk 1gal",
        store_id="STR-001",
        store_name="Flagship Manhattan",
        exception_type=ExceptionType.OOS,
        exception_date=date(2026, 3, 30),
        units_on_hand=0,
        days_of_supply=0.0,
        source_system="BlueYonder",
        batch_id="batch-001",
        ingested_at=datetime(2026, 3, 30, 8, 0, 0),
        velocity_rank=1,
        category="Dairy & Eggs",
        store_tier=1,
        weekly_store_sales_k=2100.0,
        promo_active=True,
        promo_type=PromoType.TPR,
        promo_end_date=date(2026, 4, 5),
        tpr_depth_pct=15.0,
        dc_inventory_days=4.5,
        vendor_fill_rate_90d=91.0,
        open_po_inbound=True,
        next_delivery_date=date(2026, 4, 1),
        lead_time_days=2,
        competitor_proximity_miles=0.3,
        competitor_event="Competitor dairy promo through April 5",
        perishable=True,
        day_of_week_demand_index=1.22,
        est_lost_sales_value=1847.50,
        promo_margin_at_risk=341.79,
        regional_disruption_flag=False,
        enrichment_confidence=EnrichmentConfidence.HIGH,
    )


class TestPromptComposerInit:
    def test_raises_if_prompt_file_missing(self, tmp_path: Path):
        from src.agent.prompt_composer import PromptComposer
        # Only create some files — leave phantom_inventory.md missing
        (tmp_path / "system_prompt.md").write_text("x")
        (tmp_path / "triage_framework.md").write_text("x")
        (tmp_path / "output_contract.md").write_text("x")
        (tmp_path / "pattern_detection.md").write_text("x")
        (tmp_path / "epistemic_honesty.md").write_text("x")
        (tmp_path / "few_shot_library.json").write_text("[]")
        # phantom_inventory.md is missing
        with pytest.raises(FileNotFoundError, match="phantom_inventory.md"):
            PromptComposer(prompts_dir=tmp_path)

    def test_raises_if_few_shot_library_missing(self, tmp_path: Path):
        from src.agent.prompt_composer import PromptComposer
        for name in ["system_prompt.md", "triage_framework.md", "output_contract.md",
                     "pattern_detection.md", "epistemic_honesty.md", "phantom_inventory.md"]:
            (tmp_path / name).write_text("x")
        # few_shot_library.json is missing
        with pytest.raises(FileNotFoundError, match="few_shot_library.json"):
            PromptComposer(prompts_dir=tmp_path)


class TestComposeSystemPrompt:
    def test_contains_all_six_prompt_sections(self, composer):
        system = composer.compose_system_prompt()
        assert "You are a supply chain planner." in system
        assert "Triage Framework" in system
        assert "Output Contract" in system
        assert "Pattern Detection" in system
        assert "Epistemic Honesty" in system
        assert "Phantom Inventory" in system

    def test_contains_few_shot_examples_section(self, composer):
        system = composer.compose_system_prompt()
        assert "Few-Shot Examples" in system
        assert "Test example" in system  # the description from the fixture

    def test_few_shots_inserted_between_framework_and_contract(self, composer):
        system = composer.compose_system_prompt()
        framework_pos = system.index("Triage Framework")
        few_shot_pos = system.index("Few-Shot Examples")
        contract_pos = system.index("Output Contract")
        assert framework_pos < few_shot_pos < contract_pos

    def test_system_prompt_within_token_budget(self, composer):
        # Use real prompts from the actual prompts/ directory for this test
        from src.agent.prompt_composer import PromptComposer
        real_composer = PromptComposer(prompts_dir=Path("prompts"))
        system = real_composer.compose_system_prompt()
        # Rough estimate: 1 token ≈ 4 characters
        estimated_tokens = len(system) / 4
        assert estimated_tokens < 8000, (
            f"System prompt estimated at {estimated_tokens:.0f} tokens — exceeds 8000 limit"
        )


class TestComposeUserPrompt:
    def test_contains_exception_id(self, composer, minimal_exception):
        user = composer.compose_user_prompt([minimal_exception])
        assert minimal_exception.exception_id in user

    def test_contains_all_17_required_fields(self, composer, fully_enriched_exception):
        user = composer.compose_user_prompt([fully_enriched_exception])
        required_field_markers = [
            "exception_id:",
            "item:",
            "store:",
            "exception_type:",
            "units_on_hand:",
            "days_of_supply:",
            "promo_active:",
            "promo_type:",
            "promo_end:",
            "dc_inventory_days:",
            "vendor_fill_rate_90d:",
            "open_po_inbound:",
            "next_delivery:",
            "lead_time_days:",
            "competitor_proximity_miles:",
            "perishable:",
            "day_of_week_demand_index:",
            "est_lost_sales_value:",
            "promo_margin_at_risk:",
            "regional_disruption:",
            "enrichment_confidence:",
            "missing_data_fields:",
        ]
        for marker in required_field_markers:
            assert marker in user, f"User prompt missing field marker: {marker!r}"

    def test_null_enrichment_fields_render_as_UNKNOWN(self, composer, minimal_exception):
        # minimal_exception has all enrichment fields as None
        user = composer.compose_user_prompt([minimal_exception])
        assert "UNKNOWN" in user
        # Specifically, velocity_rank is None → should render UNKNOWN
        assert "velocity rank UNKNOWN" in user

    def test_batch_header_shows_correct_count(self, composer, minimal_exception):
        batch = [minimal_exception] * 5
        user = composer.compose_user_prompt(batch)
        assert "5 replenishment exceptions" in user
        assert "[EXCEPTION 1 of 5]" in user
        assert "[EXCEPTION 5 of 5]" in user

    def test_exceptions_are_separated_by_double_newlines(self, composer, minimal_exception):
        batch = [minimal_exception, minimal_exception]
        user = composer.compose_user_prompt(batch)
        # Each exception block ends with ---
        assert user.count("---") >= 2

    def test_reasoning_trace_flag_appends_instruction(self, composer, minimal_exception):
        user_without = composer.compose_user_prompt([minimal_exception], reasoning_trace_enabled=False)
        user_with = composer.compose_user_prompt([minimal_exception], reasoning_trace_enabled=True)
        assert "reasoning_trace" not in user_without
        assert "reasoning_trace" in user_with
        assert "150 words" in user_with

    def test_promo_type_none_renders_correctly(self, composer, minimal_exception):
        # promo_type is None — should render as UNKNOWN, not "None" or "NONE.value"
        user = composer.compose_user_prompt([minimal_exception])
        assert "promo_type: UNKNOWN" in user

    def test_user_prompt_30_records_within_token_budget(self, composer):
        from src.agent.prompt_composer import PromptComposer
        real_composer = PromptComposer(prompts_dir=Path("prompts"))
        # Build 30 minimal exceptions
        exceptions = [
            EnrichedExceptionSchema(
                exception_id=f"test-{i:03d}",
                item_id=f"ITM-{i:03d}",
                item_name=f"Item {i}",
                store_id=f"STR-{i:03d}",
                store_name=f"Store {i}",
                exception_type=ExceptionType.OOS,
                exception_date=date(2026, 3, 30),
                units_on_hand=0,
                days_of_supply=0.0,
                source_system="TestSystem",
                batch_id="batch-001",
                ingested_at=datetime(2026, 3, 30, 8, 0, 0),
                enrichment_confidence=EnrichmentConfidence.HIGH,
            )
            for i in range(30)
        ]
        user = real_composer.compose_user_prompt(exceptions)
        estimated_tokens = len(user) / 4
        assert estimated_tokens < 6000, (
            f"30-record user prompt estimated at {estimated_tokens:.0f} tokens — exceeds 6000 limit"
        )
```

- [ ] **Step 4.2: Run tests to confirm they fail**

```bash
pytest tests/test_prompt_composer.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.agent.prompt_composer'` — all tests fail. Good.

- [ ] **Step 4.3: Create src/agent/prompt_composer.py**

```python
"""Prompt composer for the triage agent (Task 4.2).

Loads all prompt files at startup (cached in memory) and provides two methods:
- compose_system_prompt() -> str: Full system prompt (persona + framework + few-shots + contract + ...)
- compose_user_prompt(batch, reasoning_trace_enabled) -> str: Formatted batch for the user turn

Usage:
    composer = PromptComposer()
    system = composer.compose_system_prompt()
    user = composer.compose_user_prompt(enriched_exceptions, reasoning_trace_enabled=False)

Author: Mohith Kunta <mohith.kunta@gmail.com>
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from src.models import EnrichedExceptionSchema

PROMPTS_DIR = Path("prompts")

_REQUIRED_FILES = [
    "system_prompt.md",
    "triage_framework.md",
    "output_contract.md",
    "pattern_detection.md",
    "epistemic_honesty.md",
    "phantom_inventory.md",
    "few_shot_library.json",
]


class PromptComposer:
    """Loads prompt files and composes system/user prompts for any LLM provider."""

    def __init__(self, prompts_dir: Path = PROMPTS_DIR) -> None:
        self._prompts_dir = prompts_dir
        self._cache: dict[str, str] = {}
        self._load_all()

    def _load_all(self) -> None:
        """Load and cache all required prompt files at startup."""
        for filename in _REQUIRED_FILES:
            path = self._prompts_dir / filename
            if not path.exists():
                raise FileNotFoundError(
                    f"Required prompt file missing: {path}. "
                    "Run Task 4.1 to create all prompt files."
                )
            self._cache[filename] = path.read_text(encoding="utf-8")

    def _format_few_shots(self) -> str:
        """Format few-shot examples as a readable block for the system prompt."""
        examples = json.loads(self._cache["few_shot_library.json"])
        lines = ["## Few-Shot Examples\n"]
        for ex in examples:
            lines.append(f"### Example: {ex['description']}")
            lines.append(
                f"**Input exception:**\n```json\n"
                f"{json.dumps(ex['exception'], indent=2, default=str)}\n```"
            )
            lines.append(
                f"**Correct output:**\n```json\n"
                f"{json.dumps(ex['correct_output'], indent=2, default=str)}\n```"
            )
            lines.append(f"**Reasoning:** {ex['reasoning']}\n")
        return "\n".join(lines)

    def compose_system_prompt(self) -> str:
        """Assemble the full system prompt from all prompt blocks.

        Assembly order:
          1. Persona (system_prompt.md)
          2. Triage framework (triage_framework.md)
          3. Few-shot examples (few_shot_library.json, formatted)
          4. Output contract (output_contract.md)
          5. Pattern detection (pattern_detection.md)
          6. Epistemic honesty (epistemic_honesty.md)
          7. Phantom inventory (phantom_inventory.md)

        Returns:
            Single string containing the full system prompt.
        """
        blocks = [
            self._cache["system_prompt.md"],
            self._cache["triage_framework.md"],
            self._format_few_shots(),
            self._cache["output_contract.md"],
            self._cache["pattern_detection.md"],
            self._cache["epistemic_honesty.md"],
            self._cache["phantom_inventory.md"],
        ]
        return "\n\n---\n\n".join(block.strip() for block in blocks)

    @staticmethod
    def _v(val: object) -> str:
        """Render a value as string; None becomes 'UNKNOWN'."""
        if val is None:
            return "UNKNOWN"
        return str(val)

    def _format_exception(
        self, exc: EnrichedExceptionSchema, n: int, total: int
    ) -> str:
        """Format a single enriched exception using the standard 22-field template."""
        promo_type_str = (
            exc.promo_type.value if exc.promo_type is not None else "UNKNOWN"
        )
        lost_sales = exc.est_lost_sales_value if exc.est_lost_sales_value is not None else 0.0
        promo_margin = exc.promo_margin_at_risk if exc.promo_margin_at_risk is not None else 0.0

        return (
            f"[EXCEPTION {n} of {total}]\n"
            f"exception_id: {exc.exception_id}\n"
            f"item: {exc.item_name} ({exc.item_id}) — velocity rank {self._v(exc.velocity_rank)} in {self._v(exc.category)}\n"
            f"store: {exc.store_id} ({exc.store_name}) — Tier {self._v(exc.store_tier)}, ${self._v(exc.weekly_store_sales_k)}K/week\n"
            f"exception_type: {exc.exception_type.value}\n"
            f"units_on_hand: {exc.units_on_hand} | days_of_supply: {exc.days_of_supply:.1f}\n"
            f"promo_active: {self._v(exc.promo_active)} | promo_type: {promo_type_str} | promo_end: {self._v(exc.promo_end_date)}\n"
            f"dc_inventory_days: {self._v(exc.dc_inventory_days)}\n"
            f"vendor_fill_rate_90d: {self._v(exc.vendor_fill_rate_90d)}% | open_po_inbound: {self._v(exc.open_po_inbound)} | next_delivery: {self._v(exc.next_delivery_date)}\n"
            f"lead_time_days: {self._v(exc.lead_time_days)}\n"
            f"competitor_proximity_miles: {self._v(exc.competitor_proximity_miles)} | competitor_event: {self._v(exc.competitor_event)}\n"
            f"perishable: {self._v(exc.perishable)}\n"
            f"day_of_week_demand_index: {self._v(exc.day_of_week_demand_index)}\n"
            f"est_lost_sales_value: ${lost_sales:.2f}\n"
            f"promo_margin_at_risk: ${promo_margin:.2f}\n"
            f"regional_disruption: {self._v(exc.regional_disruption_description)}\n"
            f"enrichment_confidence: {exc.enrichment_confidence.value}\n"
            f"missing_data_fields: {exc.missing_data_fields}\n"
            f"---"
        )

    def compose_user_prompt(
        self,
        batch: List[EnrichedExceptionSchema],
        reasoning_trace_enabled: bool = False,
    ) -> str:
        """Generate the user prompt for a batch of enriched exceptions.

        Args:
            batch: List of EnrichedExceptionSchema objects to triage.
            reasoning_trace_enabled: If True, instructs the LLM to include
                a reasoning_trace field in each output object.

        Returns:
            Formatted user prompt string ready to send to the LLM provider.
        """
        total = len(batch)
        exception_blocks = "\n\n".join(
            self._format_exception(exc, i + 1, total)
            for i, exc in enumerate(batch)
        )
        prompt = (
            f"Triage the following {total} replenishment exceptions.\n\n"
            f"{exception_blocks}\n\n"
            "Return a JSON array with one object per exception, followed by the "
            "pattern_analysis object, as specified in the output contract."
        )
        if reasoning_trace_enabled:
            prompt += (
                '\n\nFor each exception, include a "reasoning_trace" field in your '
                "JSON output with your full chain of thought before reaching the "
                "priority decision. Maximum 150 words."
            )
        return prompt
```

- [ ] **Step 4.4: Run composer tests**

```bash
pytest tests/test_prompt_composer.py -v
```

Expected: All tests pass. Common failure modes:
- `test_contains_all_17_required_fields` fails → check the template in `_format_exception` matches the field markers in the test
- `test_promo_type_none_renders_correctly` fails → confirm `promo_type_str` logic returns "UNKNOWN" when `promo_type is None`
- Token budget tests fail → real prompt files are too long — trim the few-shot library examples

- [ ] **Step 4.5: Run the full test suite**

```bash
pytest tests/ -v
```

Expected: All tests pass. Count should be approximately:
- `test_ingestion.py`: 25 tests
- `test_enrichment.py`: enrichment tests
- `test_llm_provider.py`: 14 tests
- `test_prompt_files.py`: ~17 tests
- `test_prompt_composer.py`: ~12 tests

If any pre-existing tests fail, do not proceed — investigate and fix before committing.

- [ ] **Step 4.6: Commit**

```bash
git add src/agent/prompt_composer.py tests/test_prompt_composer.py
git commit -m "feat: add prompt composer (task 4.2) — system/user prompt assembly for any LLM provider"
```

---

## Self-Review Checklist

After writing this plan, verified against the spec:

**Spec coverage:**
- [x] Task 4.1: All 6 `.md` prompt files with full content — covered in Task 3
- [x] Task 4.1: `few_shot_library.json` with 5 annotated examples — covered in Step 3.10
- [x] Task 4.1: Each few-shot example has complete enriched exception objects drawn from sample scenarios — covered
- [x] Task 4.2: `src/agent/prompt_composer.py` with `compose_system_prompt()` and `compose_user_prompt()` — covered in Task 4
- [x] Task 4.2: Prompt assembly order (persona → framework → few-shots → contract → patterns → honesty → phantom) — covered
- [x] Task 4.2: Per-exception template with all 17 fields — covered in `_format_exception`
- [x] Task 4.2: Null values render as UNKNOWN — covered in `_v()` method
- [x] Task 4.2: System prompt <8000 tokens, 30-record user prompt <6000 tokens — tested
- [x] Task 4.2: reasoning_trace_enabled flag adds extra instruction — covered
- [x] Multi-provider: claude, openai, gemini, ollama all supported — covered in Task 2
- [x] Config: provider field + per-provider keys in config.yaml and AgentConfig — covered in Task 1

**No gaps found.** All spec requirements map to a task.

**Placeholder scan:** No "TBD", "TODO", "implement later", or "similar to Task N" found.

**Type consistency:**
- `LLMResponse` defined in Task 2, referenced in Task 2 tests — consistent
- `LLMProvider.complete(system_prompt, user_prompt)` defined in Task 2, called in future batch_processor — consistent
- `PromptComposer.compose_system_prompt()` and `compose_user_prompt(batch, reasoning_trace_enabled)` — signatures match test fixture usage
- `get_provider(config: AgentConfig)` takes `AgentConfig` — config extension in Task 1 adds all required fields before Task 2

---

Plan complete and saved to `docs/superpowers/plans/2026-03-30-phase4-prompt-system-multi-provider.md`.
