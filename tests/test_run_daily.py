"""Tests for the daily run dispatch script.

Author: Claude Code
"""

from __future__ import annotations

import httpx
import pytest

from scripts.run_daily import dispatch_briefing


def test_dispatch_briefing_posts_content(tmp_path, monkeypatch):
    """Test that dispatch_briefing posts briefing content to a webhook."""
    briefing_dir = tmp_path / "output" / "briefings"
    briefing_dir.mkdir(parents=True)
    (briefing_dir / "briefing_2026-07-04.md").write_text("# Morning Briefing\nAll clear.")
    monkeypatch.chdir(tmp_path)

    calls = {}

    def fake_post(url, json=None, timeout=None):
        calls["url"], calls["json"] = url, json
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)

    assert dispatch_briefing("2026-07-04", "https://hooks.slack.example/x") is True
    assert "Morning Briefing" in calls["json"]["text"]


def test_dispatch_briefing_missing_file_returns_false(tmp_path, monkeypatch):
    """Test that dispatch_briefing returns False when briefing file is missing."""
    monkeypatch.chdir(tmp_path)
    assert dispatch_briefing("2026-07-04", "https://hooks.slack.example/x") is False


def test_dispatch_briefing_webhook_failure_returns_false(tmp_path, monkeypatch):
    """Test that dispatch_briefing returns False when webhook POST fails."""
    briefing_dir = tmp_path / "output" / "briefings"
    briefing_dir.mkdir(parents=True)
    (briefing_dir / "briefing_2026-07-04.md").write_text("# Morning Briefing\nAll clear.")
    monkeypatch.chdir(tmp_path)

    def fake_post_failure(url, json=None, timeout=None):
        raise httpx.HTTPError("Connection failed")

    monkeypatch.setattr(httpx, "post", fake_post_failure)

    assert dispatch_briefing("2026-07-04", "https://hooks.slack.example/x") is False
