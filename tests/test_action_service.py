import asyncio
import pytest
from datetime import date
from typing import Tuple, Dict, Any

from src.db.action_store import ActionStore
from src.actions.service import ActionService
from src.actions.adapters import BaseActionAdapter
from src.models import ActionRequest, ActionType

class MockAdapter(BaseActionAdapter):
    def __init__(self, succeed=True):
        self.succeed = succeed
        
    async def execute(self, action_type: str, payload: dict) -> Tuple[bool, str, Dict[str, Any]]:
        if self.succeed:
            return True, "", {"remote": "ok"}
        return False, "Failed downstream", {"err": "1"}

def test_action_service_success():
    store = ActionStore(db_path=":memory:")
    service = ActionService(store, adapter=MockAdapter(succeed=True))
    
    req = ActionRequest(
        request_id="req-1", exception_id="e-1", run_date=date.today(),
        action_type=ActionType.DEFER, requested_by="u1", requested_by_role="analyst", payload={}
    )
    result = asyncio.run(service.submit_action(req))
    assert result["status"] == "completed"
    assert result["downstream_response"]["remote"] == "ok"

def test_action_service_failure_and_retry():
    store = ActionStore(db_path=":memory:")
    adapter = MockAdapter(succeed=False)
    service = ActionService(store, adapter=adapter)
    
    req = ActionRequest(
        request_id="req-2", exception_id="e-2", run_date=date.today(),
        action_type=ActionType.STORE_CHECK, requested_by="u1", requested_by_role="planner", payload={}
    )
    result = asyncio.run(service.submit_action(req))
    assert result["status"] == "failed"
    assert result["failure_reason"] == "Failed downstream"
    
    # Now retry with successful adapter
    adapter.succeed = True
    retry_res = asyncio.run(service.retry_action("req-2"))
    assert retry_res["status"] == "completed"


def test_action_service_rejects_planner_only_action_for_analyst():
    store = ActionStore(db_path=":memory:")
    service = ActionService(store, adapter=MockAdapter(succeed=True))

    req = ActionRequest(
        request_id="req-3", exception_id="e-3", run_date=date.today(),
        action_type=ActionType.STORE_CHECK, requested_by="u1", requested_by_role="analyst", payload={}
    )

    with pytest.raises(PermissionError, match="requires planner role"):
        asyncio.run(service.submit_action(req))

    assert store.get_action("req-3") is None


# Tests for SlackWebhookAdapter
import httpx
from src.actions.adapters import SlackWebhookAdapter, build_default_adapter, GenericWebhookAdapter


class TestSlackAdapter:
    def test_posts_payload_and_succeeds(self, monkeypatch):
        # Mock httpx.AsyncClient.post to verify the call
        post_called = []

        async def fake_post(self, url, json=None, **kwargs):
            post_called.append({"url": url, "json": json})
            return httpx.Response(200, text="ok")

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        adapter = SlackWebhookAdapter("https://hooks.slack.example/T000/B000/XXX")
        ok, reason, resp = asyncio.run(adapter.execute("VENDOR_FOLLOW_UP", {"note": "check PO 123"}))

        assert ok is True and reason == ""
        assert len(post_called) == 1
        assert "hooks.slack" in post_called[0]["url"]
        assert "VENDOR_FOLLOW_UP" in post_called[0]["json"]["text"]

    def test_http_error_reports_failure(self, monkeypatch):
        async def fake_post(self, url, json=None, **kwargs):
            return httpx.Response(500, text="internal error")

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        adapter = SlackWebhookAdapter("https://hooks.slack.example/T000/B000/XXX")
        ok, reason, resp = asyncio.run(adapter.execute("STORE_CHECK", {}))

        assert ok is False and "500" in reason

    def test_factory_uses_slack_when_env_set(self, monkeypatch):
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.example/x")
        result = build_default_adapter()
        assert isinstance(result, SlackWebhookAdapter)

    def test_factory_falls_back_to_mock(self, monkeypatch):
        monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
        result = build_default_adapter()
        assert isinstance(result, GenericWebhookAdapter)

    def test_reads_notes_key_from_real_frontend_payload(self, monkeypatch):
        """Test that payload with 'notes' key (from real frontend) is correctly included in Slack message."""
        post_called = []

        async def fake_post(self, url, json=None, **kwargs):
            post_called.append({"url": url, "json": json})
            return httpx.Response(200, text="ok")

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        adapter = SlackWebhookAdapter("https://hooks.slack.example/T000/B000/XXX")
        ok, reason, resp = asyncio.run(
            adapter.execute("VENDOR_FOLLOW_UP", {"notes": "check PO 123", "exception_id": "EXC-1"})
        )

        assert ok is True and reason == ""
        assert len(post_called) == 1
        # Verify that the notes text appears in the posted Slack message
        assert "check PO 123" in post_called[0]["json"]["text"]
        assert "EXC-1" in post_called[0]["json"]["text"]
