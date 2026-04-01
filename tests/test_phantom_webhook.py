"""Tests for the Phantom Inventory Webhook module (Task 5.3).

Author: Mohith Kunta <mohith.kunta@gmail.com>
"""

from unittest.mock import patch, MagicMock
import httpx
import pytest

from src.agent.phantom_webhook import process_phantom_inventory
from src.models import ExceptionType, Priority, TriageResult, EnrichmentConfidence
from src.utils.config_loader import AgentConfig


@pytest.fixture
def mock_config() -> AgentConfig:
    return AgentConfig(
        provider="claude",
        model="test-model",
        phantom_webhook_enabled=True,
        phantom_webhook_url="http://test-webhook.local/api/phantom",
    )


@pytest.fixture
def mock_result() -> TriageResult:
    return TriageResult(
        exception_id="exc-001",
        item_id="itm-123",
        store_id="str-456",
        priority=Priority.HIGH,
        confidence=EnrichmentConfidence.HIGH,
        root_cause="Test root cause",
        recommended_action="Test action",
        financial_impact_statement="Test financial impact",
        planner_brief="Test brief",
        compounding_risks=["POTENTIAL_PHANTOM_INVENTORY"],
        dc_inventory_days=45.0,
        vendor_fill_rate_90d=98.5,
    )


@patch("httpx.post")
def test_returns_early_if_no_flag(mock_post, mock_config, mock_result):
    mock_result.compounding_risks = []
    process_phantom_inventory(mock_result, mock_config)
    mock_post.assert_not_called()


@patch("httpx.post")
def test_returns_early_if_webhook_disabled(mock_post, mock_config, mock_result):
    mock_config.phantom_webhook_enabled = False
    process_phantom_inventory(mock_result, mock_config)
    mock_post.assert_not_called()


@patch("httpx.post")
def test_updates_record_on_confirmed_phantom(mock_post, mock_config, mock_result):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"phantom_confirmed": True, "priority": "MEDIUM"}
    mock_post.return_value = mock_response

    process_phantom_inventory(mock_result, mock_config)

    # Validate post request payload
    mock_post.assert_called_once()
    kwargs = mock_post.call_args[1]
    args = mock_post.call_args[0]
    assert args[0] == "http://test-webhook.local/api/phantom"
    assert kwargs["timeout"] == 5.0
    payload = kwargs["json"]
    assert payload["exception_id"] == "exc-001"
    assert payload["trigger"] == "TRIAGE_AGENT_FLAG"

    # Validate mutation
    assert mock_result.phantom_flag is True
    assert mock_result.exception_type == ExceptionType.DATA_INTEGRITY.value
    assert mock_result.priority == Priority.MEDIUM


@patch("httpx.post")
def test_ignores_record_if_not_confirmed(mock_post, mock_config, mock_result):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"phantom_confirmed": False}
    mock_post.return_value = mock_response

    process_phantom_inventory(mock_result, mock_config)

    assert mock_result.phantom_flag is False
    assert mock_result.exception_type != ExceptionType.DATA_INTEGRITY.value
    assert mock_result.priority == Priority.HIGH


@patch("httpx.post")
def test_gracefully_handles_timeout(mock_post, mock_config, mock_result):
    mock_post.side_effect = httpx.TimeoutException("Timeout")
    # Should not raise
    process_phantom_inventory(mock_result, mock_config)

    assert mock_result.phantom_flag is False


@patch("httpx.post")
def test_gracefully_handles_http_error(mock_post, mock_config, mock_result):
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_post.side_effect = httpx.HTTPStatusError("500", request=MagicMock(), response=mock_response)
    # Should not raise
    process_phantom_inventory(mock_result, mock_config)
    
    assert mock_result.phantom_flag is False
