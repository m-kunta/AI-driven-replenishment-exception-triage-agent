"""Utility for safe, atomic .env mutation from the Settings API."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Dict, Any
from dotenv import dotenv_values

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_ENV_PATH = _REPO_ROOT / ".env"

_ALLOWLIST: set[str] = {
    "AGENT_PROVIDER",
    "AGENT_MODEL",
    "API_USER_ROLE",
    "API_USER_ROLES",
    "OLLAMA_BASE_URL",
    "BACKEND_PORT",
}

_ALL_RESTART_REQUIRED: set[str] = _ALLOWLIST  # every editable key requires restart

_VALID_PROVIDERS = {"claude", "openai", "gemini", "ollama"}
_VALID_ROLES = {"analyst", "planner"}


class EnvValidationError(ValueError):
    pass


class EnvWriter:
    """Validates and atomically writes a subset of .env keys."""

    @staticmethod
    def read_persisted_values(env_path: Path = _DEFAULT_ENV_PATH) -> Dict[str, str]:
        """Read the current persisted editable .env values for safe frontend baselines."""
        if not env_path.exists():
            return {}
        raw_values = dotenv_values(env_path)
        return {
            key: value
            for key, value in raw_values.items()
            if key in _ALLOWLIST and value is not None
        }

    @staticmethod
    def validate(payload: Dict[str, str]) -> Dict[str, str]:
        """Validate a partial settings payload.

        Returns a dict of {key: error_message} for every invalid or
        disallowed key. An empty dict means the payload is valid.
        """
        errors: Dict[str, str] = {}

        for key, value in payload.items():
            if key not in _ALLOWLIST:
                errors[key] = f"Key '{key}' is not editable via the API."
                continue

            if key == "AGENT_PROVIDER":
                if value not in _VALID_PROVIDERS:
                    errors[key] = (
                        f"Must be one of: {', '.join(sorted(_VALID_PROVIDERS))}."
                    )

            elif key == "AGENT_MODEL":
                if not value.strip():
                    errors[key] = "Model name must not be empty."

            elif key == "API_USER_ROLE":
                if value not in _VALID_ROLES:
                    errors[key] = "Must be 'analyst' or 'planner'."

            elif key == "API_USER_ROLES":
                err = EnvWriter._validate_user_roles(value)
                if err:
                    errors[key] = err

            elif key == "OLLAMA_BASE_URL":
                if not (value.startswith("http://") or value.startswith("https://")):
                    errors[key] = "Must be a valid URL starting with http:// or https://."

            elif key == "BACKEND_PORT":
                try:
                    port = int(value)
                    if not (1024 <= port <= 65535):
                        raise ValueError
                except ValueError:
                    errors[key] = "Must be an integer between 1024 and 65535."

        return errors

    @staticmethod
    def _validate_user_roles(value: str) -> str:
        """Return an error string or empty string for API_USER_ROLES value."""
        if not value.strip():
            return ""  # empty is valid (clears all role mappings)
        for entry in value.split(","):
            entry = entry.strip()
            if not entry:
                continue
            if ":" not in entry:
                return f"Entry '{entry}' must use username:role format."
            username, role = (p.strip() for p in entry.split(":", 1))
            if not username:
                return "Each entry must include a username."
            if role not in _VALID_ROLES:
                return f"Role '{role}' must be 'analyst' or 'planner'."
        return ""

    @staticmethod
    def apply(
        payload: Dict[str, str],
        env_path: Path = _DEFAULT_ENV_PATH,
    ) -> Dict[str, Any]:
        """Atomically write the payload keys to the .env file.

        Updates existing KEY=value lines in-place, appends missing keys.
        Preserves comments and ordering. Uses a temp file + os.replace()
        for atomicity.

        Returns:
            {"applied": [...], "restart_required": [...], "errors": {}}
        """
        # Read existing file, or start empty
        if env_path.exists():
            lines = env_path.read_text().splitlines(keepends=True)
        else:
            lines = []

        updated_keys: set[str] = set()
        new_lines = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#") or "=" not in stripped:
                new_lines.append(line)
                continue
            key = stripped.split("=", 1)[0].strip()
            if key in payload:
                new_lines.append(f"{key}={payload[key]}\n")
                updated_keys.add(key)
            else:
                new_lines.append(line)

        # Ensure the last line ends with a newline before appending new keys
        if new_lines and not new_lines[-1].endswith('\n'):
            new_lines[-1] += '\n'

        # Append keys that weren't already in the file
        for key, value in payload.items():
            if key not in updated_keys:
                new_lines.append(f"{key}={value}\n")

        # Atomic write via temp file in the same directory
        env_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=env_path.parent, prefix=".env.tmp.")
        try:
            with os.fdopen(fd, "w") as f:
                f.writelines(new_lines)
            os.replace(tmp, env_path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

        applied = list(payload.keys())
        restart_required = [k for k in applied if k in _ALL_RESTART_REQUIRED]
        return {"applied": applied, "restart_required": restart_required, "errors": {}}
