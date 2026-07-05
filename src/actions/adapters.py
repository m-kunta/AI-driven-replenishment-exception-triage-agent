import os
import httpx
from abc import ABC, abstractmethod
from typing import Dict, Tuple, Any


class BaseActionAdapter(ABC):
    @abstractmethod
    async def execute(self, action_type: str, payload: dict) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Executes the action against a downstream system.

        Returns:
            Tuple containing:
            - success (bool): True if successful
            - failure_reason (str): Empty if successful, otherwise reason for failure
            - downstream_response (dict): Any response payload from the downstream system
        """
        pass


class GenericWebhookAdapter(BaseActionAdapter):
    """A generic webhook adapter for v1 to mock or send simple HTTP payloads."""

    async def execute(self, action_type: str, payload: dict) -> Tuple[bool, str, Dict[str, Any]]:
        # In a real scenario, this would use httpx to hit an external URL.
        # For Phase 13 v1, we mock a successful execution (or failure if requested).
        import asyncio
        await asyncio.sleep(0.5) # Simulate network latency

        # Simulating a failure for testing purposes
        if payload.get("simulate_failure"):
            return False, "Simulated downstream failure", {"error": "simulated_error", "status_code": 500}

        return True, "", {"status": "accepted", "remote_id": f"EXT-{action_type}-{id(payload)}"}


class SlackWebhookAdapter(BaseActionAdapter):
    """Posts action requests to a Slack incoming webhook."""

    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    async def execute(self, action_type: str, payload: dict) -> Tuple[bool, str, Dict[str, Any]]:
        note = payload.get("notes") or payload.get("note") or payload.get("comment") or ""
        exception_id = payload.get("exception_id", "unknown")
        text = (
            f":package: *Triage Action: {action_type}*\n"
            f"Exception: `{exception_id}`\n"
            f"{note}".strip()
        )
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self.webhook_url, json={"text": text})
            if response.status_code >= 400:
                return False, f"Slack webhook returned HTTP {response.status_code}", {
                    "status_code": response.status_code, "body": response.text[:500],
                }
            return True, "", {"status": "delivered", "status_code": response.status_code}
        except httpx.HTTPError as e:
            return False, f"Slack webhook request failed: {e}", {}


def build_default_adapter() -> BaseActionAdapter:
    """Slack adapter when SLACK_WEBHOOK_URL is configured, otherwise the mock."""
    url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if url:
        return SlackWebhookAdapter(url)
    return GenericWebhookAdapter()
