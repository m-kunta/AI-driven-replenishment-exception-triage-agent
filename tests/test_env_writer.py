"""Tests for EnvWriter — .env validation and atomic write."""
from __future__ import annotations

import pytest
from pathlib import Path

from src.api.env_writer import EnvWriter, EnvValidationError

ALLOWLIST = {"AGENT_PROVIDER", "AGENT_MODEL", "API_USER_ROLE", "API_USER_ROLES",
             "OLLAMA_BASE_URL", "BACKEND_PORT"}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_valid_provider_passes(self):
        errors = EnvWriter.validate({"AGENT_PROVIDER": "openai"})
        assert errors == {}

    def test_invalid_provider_fails(self):
        errors = EnvWriter.validate({"AGENT_PROVIDER": "unknown_llm"})
        assert "AGENT_PROVIDER" in errors

    def test_valid_role_passes(self):
        errors = EnvWriter.validate({"API_USER_ROLE": "planner"})
        assert errors == {}

    def test_invalid_role_fails(self):
        errors = EnvWriter.validate({"API_USER_ROLE": "admin"})
        assert "API_USER_ROLE" in errors

    def test_valid_user_roles_passes(self):
        errors = EnvWriter.validate({"API_USER_ROLES": "alice:planner,bob:analyst"})
        assert errors == {}

    def test_invalid_user_roles_bad_format_fails(self):
        errors = EnvWriter.validate({"API_USER_ROLES": "alice-planner"})
        assert "API_USER_ROLES" in errors

    def test_invalid_user_roles_bad_role_fails(self):
        errors = EnvWriter.validate({"API_USER_ROLES": "alice:superadmin"})
        assert "API_USER_ROLES" in errors

    def test_valid_port_passes(self):
        errors = EnvWriter.validate({"BACKEND_PORT": "8080"})
        assert errors == {}

    def test_port_below_range_fails(self):
        errors = EnvWriter.validate({"BACKEND_PORT": "80"})
        assert "BACKEND_PORT" in errors

    def test_port_above_range_fails(self):
        errors = EnvWriter.validate({"BACKEND_PORT": "99999"})
        assert "BACKEND_PORT" in errors

    def test_non_numeric_port_fails(self):
        errors = EnvWriter.validate({"BACKEND_PORT": "abc"})
        assert "BACKEND_PORT" in errors

    def test_valid_ollama_url_passes(self):
        errors = EnvWriter.validate({"OLLAMA_BASE_URL": "http://localhost:11434"})
        assert errors == {}

    def test_invalid_ollama_url_fails(self):
        errors = EnvWriter.validate({"OLLAMA_BASE_URL": "ftp://bad"})
        assert "OLLAMA_BASE_URL" in errors

    def test_key_outside_allowlist_fails(self):
        errors = EnvWriter.validate({"API_PASSWORD": "secret"})
        assert "API_PASSWORD" in errors

    def test_empty_model_fails(self):
        errors = EnvWriter.validate({"AGENT_MODEL": ""})
        assert "AGENT_MODEL" in errors

    def test_non_empty_model_passes(self):
        errors = EnvWriter.validate({"AGENT_MODEL": "gpt-4.1"})
        assert errors == {}


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

class TestWrite:
    def test_updates_existing_key(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("AGENT_PROVIDER=claude\nAPI_PASSWORD=secret\n")

        EnvWriter.apply({"AGENT_PROVIDER": "openai"}, env_path=env)

        content = env.read_text()
        assert "AGENT_PROVIDER=openai" in content
        assert "API_PASSWORD=secret" in content  # untouched

    def test_appends_missing_key(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("API_PASSWORD=secret\n")

        EnvWriter.apply({"AGENT_MODEL": "gpt-4.1"}, env_path=env)

        assert "AGENT_MODEL=gpt-4.1" in env.read_text()

    def test_preserves_comments(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("# provider\nAGENT_PROVIDER=claude\n")

        EnvWriter.apply({"AGENT_PROVIDER": "openai"}, env_path=env)

        assert "# provider" in env.read_text()

    def test_write_is_atomic(self, tmp_path):
        """Verify no partial write: original is intact if an error occurs mid-write."""
        env = tmp_path / ".env"
        original = "AGENT_PROVIDER=claude\n"
        env.write_text(original)

        # Make parent directory read-only to trigger error during temp file creation
        import os as os_module
        import stat
        os_module.chmod(tmp_path, stat.S_IRUSR | stat.S_IXUSR)  # r-x------
        try:
            with pytest.raises(Exception):
                EnvWriter.apply({"AGENT_PROVIDER": "openai"}, env_path=env)
        finally:
            # Restore write permission for cleanup
            os_module.chmod(tmp_path, stat.S_IRWXU)

        # Original is intact
        assert env.read_text() == original

    def test_returns_applied_and_restart_required(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("AGENT_PROVIDER=claude\n")

        result = EnvWriter.apply({"AGENT_PROVIDER": "openai"}, env_path=env)

        assert "AGENT_PROVIDER" in result["applied"]
        assert "AGENT_PROVIDER" in result["restart_required"]

    def test_appends_to_file_without_trailing_newline(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("API_PASSWORD=secret")  # no trailing newline

        EnvWriter.apply({"AGENT_MODEL": "gpt-4.1"}, env_path=env)

        content = env.read_text()
        assert "API_PASSWORD=secret" in content
        assert "AGENT_MODEL=gpt-4.1" in content
        # Key must be on its own line
        lines = content.splitlines()
        assert any(line == "AGENT_MODEL=gpt-4.1" for line in lines)
