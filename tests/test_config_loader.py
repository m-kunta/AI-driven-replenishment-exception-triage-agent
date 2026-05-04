from __future__ import annotations

import textwrap

import pytest
import yaml

from src.utils.config_loader import ConfigurationError, load_config, validate_required_env_vars


def write_config(tmp_path, provider_line: str = "provider: claude") -> str:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        textwrap.dedent(
            f"""
            ingestion:
              adapter: csv
            enrichment: {{}}
            agent:
              {provider_line}
              model: test-model
              anthropic_api_key: ${{ANTHROPIC_API_KEY}}
              openai_api_key: ${{OPENAI_API_KEY}}
              gemini_api_key: ${{GEMINI_API_KEY}}
            output: {{}}
            backtest: {{}}
            """
        ).strip()
    )
    return str(config_path)


def test_env_override_can_switch_provider_to_gemini(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "gm-key")
    monkeypatch.setenv("AGENT_PROVIDER", "gemini")

    config = load_config(write_config(tmp_path, provider_line="provider: ${AGENT_PROVIDER}"))

    assert config.agent.provider == "gemini"
    validate_required_env_vars(config)


def test_claude_remains_default_without_provider_override(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anth-key")
    monkeypatch.delenv("AGENT_PROVIDER", raising=False)

    config = load_config(write_config(tmp_path))

    assert config.agent.provider == "claude"
    validate_required_env_vars(config)


def test_gemini_key_alone_does_not_change_provider_without_override(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gm-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("AGENT_PROVIDER", raising=False)

    config = load_config(write_config(tmp_path))

    assert config.agent.provider == "claude"
    with pytest.raises(Exception):
        validate_required_env_vars(config)


def test_invalid_agent_provider_override_raises_configuration_error(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_PROVIDER", "not-real")

    with pytest.raises(ConfigurationError):
        load_config(write_config(tmp_path))


_MINIMAL_YAML = yaml.dump({
    "agent": {
        "provider": "ollama",
        "model": "llama3.2",
        "batch_size": 10,
        "max_tokens": 8000,
        "retry_attempts": 3,
        "ollama_base_url": "http://localhost:11434",
    },
    "ingestion": {"adapter": "csv"},
    "output": {"log_dir": "output/logs"},
})


def test_ollama_base_url_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://custom-ollama:9999")
    monkeypatch.delenv("AGENT_PROVIDER", raising=False)
    monkeypatch.delenv("AGENT_MODEL", raising=False)

    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(_MINIMAL_YAML)

    cfg = load_config(config_path=str(cfg_path))

    assert cfg.agent.ollama_base_url == "http://custom-ollama:9999"


def test_ollama_base_url_env_override_absent_uses_yaml(monkeypatch, tmp_path):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("AGENT_PROVIDER", raising=False)
    monkeypatch.delenv("AGENT_MODEL", raising=False)

    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(_MINIMAL_YAML)

    cfg = load_config(config_path=str(cfg_path))

    assert cfg.agent.ollama_base_url == "http://localhost:11434"
