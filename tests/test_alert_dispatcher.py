from datetime import date, datetime
from unittest.mock import MagicMock, call, patch

import httpx
import pytest

from src.models import (
    EnrichmentConfidence,
    Priority,
    TriageResult,
    TriageRunResult,
)
from src.output.alert_dispatcher import AlertDispatcher
from src.utils.config_loader import AlertChannelConfig, AppConfig


@pytest.fixture
def base_config():
    config = AppConfig()
    return config


@pytest.fixture
def mock_run_result():
    results = [
        TriageResult(
            exception_id="c1",
            priority=Priority.CRITICAL,
            confidence=EnrichmentConfidence.HIGH,
            item_name="Widget A",
            store_name="Main St",
            store_tier=1,
            exception_type="OOS",
            days_of_supply=0.0,
            est_lost_sales_value=1500.0,
            promo_margin_at_risk=500.0,
            recommended_action="Expedite PO 123",
            planner_brief="Critical stockout at Tier 1 store.",
            root_cause="Vendor Late",
            financial_impact_statement="High impact",
        )
    ]
    return TriageRunResult(
        run_id="test-run-123",
        run_date=date(2026, 4, 9),
        run_timestamp=datetime(2026, 4, 9, 12, 0, 0),
        triage_results=results
    )


def test_format_alert_standard_output(base_config, mock_run_result):
    dispatcher = AlertDispatcher(base_config)
    result = mock_run_result.triage_results[0]
    
    alert_text = dispatcher.format_alert(result, mock_run_result)
    
    assert "🚨 REPLENISHMENT TRIAGE ALERT — CRITICAL" in alert_text
    assert "Item: Widget A | Store: Main St (Tier 1)" in alert_text
    assert "Exception: OOS | Days of Supply: 0.0" in alert_text
    assert "Financial Exposure: $1,500 lost sales | $500 promo margin at risk" in alert_text
    assert "ACTION REQUIRED: Expedite PO 123" in alert_text
    assert "Critical stockout at Tier 1 store." in alert_text
    assert "Root Cause: Vendor Late" in alert_text
    assert "Confidence: HIGH" in alert_text
    assert "Missing Data: None" in alert_text
    assert "Run ID: test-run-123 | Generated: 2026-04-09T12:00:00" in alert_text
    assert "⚠️ LOW CONFIDENCE" not in alert_text


def test_format_alert_low_confidence_flag(base_config, mock_run_result):
    dispatcher = AlertDispatcher(base_config)
    result = mock_run_result.triage_results[0]
    
    # Modify for low confidence
    result.confidence = EnrichmentConfidence.LOW
    result.missing_data_flags = ["vendor_performance", "dc_inventory_days"]
    
    alert_text = dispatcher.format_alert(result, mock_run_result)
    
    assert "Confidence: LOW ⚠️ LOW CONFIDENCE — verify vendor_performance, dc_inventory_days before acting." in alert_text
    assert "Missing Data: vendor_performance, dc_inventory_days" in alert_text


@patch.object(AlertDispatcher, '_dispatch_text')
def test_dispatch_ignores_medium_low(mock_dispatch_text, base_config, mock_run_result):
    # Change result to MEDIUM and LOW
    mock_run_result.triage_results[0].priority = Priority.MEDIUM
    mock_run_result.triage_results.append(
        TriageResult(
            exception_id="l1",
            priority=Priority.LOW,
            confidence=EnrichmentConfidence.HIGH,
            root_cause="Test",
            recommended_action="Test",
            financial_impact_statement="Test",
            planner_brief="Test"
        )
    )
    
    dispatcher = AlertDispatcher(base_config)
    dispatcher.dispatch(mock_run_result)
    
    # Assert _dispatch_text never called since they are non-severe
    mock_dispatch_text.assert_not_called()


@patch("src.output.alert_dispatcher.httpx.post")
@patch("src.output.alert_dispatcher.smtplib.SMTP")
def test_channel_disabled_suppression(mock_smtp, mock_post, base_config, mock_run_result):
    base_config.alerting.channels = [
        AlertChannelConfig(
            type="webhook",
            enabled=False,
            webhook_url="https://hooks.slack.com/test"
        ),
        AlertChannelConfig(
            type="email",
            enabled=False,
            smtp_host="localhost",
            from_address="test@triage.com",
            to_addresses=["planner@triage.com"]
        )
    ]
    
    dispatcher = AlertDispatcher(base_config)
    dispatcher.dispatch(mock_run_result)
    
    mock_post.assert_not_called()
    mock_smtp.assert_not_called()


@patch("src.output.alert_dispatcher.httpx.post")
def test_http_webhook_dispatch_success(mock_post, base_config, mock_run_result):
    # Mock httpx.post returning a 200 OM
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response
    
    base_config.alerting.channels = [
        AlertChannelConfig(
            type="webhook",
            enabled=True,
            webhook_url="https://hooks.slack.com/test"
        )
    ]
    
    dispatcher = AlertDispatcher(base_config)
    # mock schedule_escalation to avoid thread launching in test
    dispatcher.schedule_escalation = MagicMock()
    
    dispatcher.dispatch(mock_run_result)
    
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "https://hooks.slack.com/test"
    assert "json" in kwargs
    assert "text" in kwargs["json"]
    assert "🚨 REPLENISHMENT TRIAGE ALERT — CRITICAL" in kwargs["json"]["text"]


@patch("src.output.alert_dispatcher.smtplib.SMTP")
def test_smtp_email_dispatch_success(mock_smtp, base_config, mock_run_result):
    # Setup mock SMTP instance
    mock_server = MagicMock()
    mock_smtp.return_value.__enter__.return_value = mock_server
    
    base_config.alerting.channels = [
        AlertChannelConfig(
            type="email",
            enabled=True,
            smtp_host="smtp.test.com",
            smtp_port=587,
            from_address="sys@test.com",
            to_addresses=["p1@test.com", "p2@test.com"]
        )
    ]
    
    dispatcher = AlertDispatcher(base_config)
    dispatcher.schedule_escalation = MagicMock()
    
    dispatcher.dispatch(mock_run_result)
    
    mock_smtp.assert_called_once_with("smtp.test.com", 587)
    mock_server.send_message.assert_called_once()
    
    sent_msg = mock_server.send_message.call_args[0][0]
    assert sent_msg["Subject"] == "Triage Alert - CRITICAL: Widget A"
    assert sent_msg["From"] == "sys@test.com"
    assert sent_msg["To"] == "p1@test.com, p2@test.com"
    assert "🚨 REPLENISHMENT TRIAGE ALERT — CRITICAL" in sent_msg.get_content()


@patch("src.output.alert_dispatcher.threading.Timer")
@patch("src.output.alert_dispatcher.httpx.post")
def test_sla_escalation_fires_for_critical_and_high(mock_post, mock_timer, base_config, mock_run_result):
    """Verify schedule_escalation is invoked for both CRITICAL and HIGH results."""
    mock_timer_instance = MagicMock()
    mock_timer.return_value = mock_timer_instance

    base_config.alerting.channels = []  # no channels needed for this test

    # Add a HIGH result alongside the existing CRITICAL
    mock_run_result.triage_results.append(
        TriageResult(
            exception_id="h1",
            priority=Priority.HIGH,
            confidence=EnrichmentConfidence.HIGH,
            root_cause="Low stock",
            recommended_action="Reorder",
            financial_impact_statement="Medium impact",
            planner_brief="High priority stock issue.",
            item_name="Widget B",
        )
    )

    dispatcher = AlertDispatcher(base_config)
    dispatcher.dispatch(mock_run_result)

    # Timer should have been constructed twice (once for CRITICAL c1, once for HIGH h1)
    assert mock_timer.call_count == 2
    mock_timer_instance.start.assert_called()
    assert mock_timer_instance.daemon is True


def test_escalation_format_header(base_config, mock_run_result):
    """Verify that is_escalation=True prepends the ESCALATION prefix."""
    dispatcher = AlertDispatcher(base_config)
    result = mock_run_result.triage_results[0]

    normal_text = dispatcher.format_alert(result, mock_run_result, is_escalation=False)
    escalated_text = dispatcher.format_alert(result, mock_run_result, is_escalation=True)

    assert not normal_text.startswith("[ESCALATION]")
    assert escalated_text.startswith("[ESCALATION]")
    assert "Unacknowledged after" in escalated_text
    assert "🚨 REPLENISHMENT TRIAGE ALERT — CRITICAL" in escalated_text


@patch("src.output.alert_dispatcher.httpx.post")
def test_http_webhook_failure_logs_gracefully(mock_post, base_config, mock_run_result):
    """Verify HTTP errors are caught and logged without raising."""
    mock_post.side_effect = httpx.HTTPError("Connection refused")

    base_config.alerting.channels = [
        AlertChannelConfig(
            type="webhook",
            enabled=True,
            webhook_url="https://hooks.slack.com/test"
        )
    ]

    dispatcher = AlertDispatcher(base_config)
    dispatcher.schedule_escalation = MagicMock()

    # Should not raise — the error must be swallowed and logged
    try:
        dispatcher.dispatch(mock_run_result)
    except Exception:
        pytest.fail("dispatch() raised an exception on webhook failure — it should log and continue")


def test_unknown_channel_type_silently_skipped(base_config, mock_run_result):
    """Verify dispatch silently ignores unknown channel types without error."""
    base_config.alerting.channels = [
        AlertChannelConfig(
            type="sms",       # not supported
            enabled=True,
            webhook_url=None  # no URL either
        )
    ]

    dispatcher = AlertDispatcher(base_config)
    dispatcher.schedule_escalation = MagicMock()

    # Should complete without raising
    try:
        dispatcher.dispatch(mock_run_result)
    except Exception:
        pytest.fail("dispatch() raised on unknown channel type — it should silently skip")
