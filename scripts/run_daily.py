"""Run the daily triage pipeline and post the briefing to Slack.

Usage:
    .venv/bin/python scripts/run_daily.py [--date YYYY-MM-DD] [--dry-run]

Designed for cron. Exits non-zero if the pipeline fails.

Author: Claude Code
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

import httpx
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def dispatch_briefing(run_date: str, webhook_url: str) -> bool:
    """Post the day's briefing markdown to a Slack-style webhook.

    Args:
        run_date: ISO date string (YYYY-MM-DD).
        webhook_url: Slack webhook URL.

    Returns:
        True if dispatched successfully, False otherwise.
    """
    briefing_path = Path("output/briefings") / f"briefing_{run_date}.md"
    if not briefing_path.exists():
        logger.warning("No briefing found at {} — skipping dispatch", briefing_path)
        return False
    content = briefing_path.read_text(encoding="utf-8")
    try:
        response = httpx.post(webhook_url, json={"text": content}, timeout=10.0)
        response.raise_for_status()
        logger.info("Briefing for {} dispatched to webhook", run_date)
        return True
    except httpx.HTTPError as e:
        logger.error("Failed to dispatch briefing: {}", e)
        return False


def main() -> int:
    """Parse CLI arguments and run the daily pipeline.

    Returns:
        0 on success, 1 on failure.
    """
    parser = argparse.ArgumentParser(description="Daily triage run + briefing dispatch")
    parser.add_argument("--date", default=str(date.today()), help="Run date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Skip LLM calls")
    args = parser.parse_args()

    from src.main import run_triage_pipeline

    try:
        run_triage_pipeline(
            config_path="config/config.yaml",
            run_date=args.date,
            dry_run=args.dry_run,
            no_alerts=False,
            sample=True,
            verbose=False,
        )
    except Exception as e:
        logger.error("Daily pipeline run failed: {}", e)
        return 1

    webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if webhook_url:
        dispatch_briefing(args.date, webhook_url)
    else:
        logger.info("SLACK_WEBHOOK_URL not set — briefing not dispatched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
