"""Phantom Inventory Webhook module (Task 5.3).

Author: Mohith Kunta <mohith.kunta@gmail.com>
"""

from __future__ import annotations

import httpx
from loguru import logger

from src.models import ExceptionType, Priority, TriageResult
from src.utils.config_loader import AgentConfig


def process_phantom_inventory(triage_result: TriageResult, config: AgentConfig) -> None:
    """Fire webhook for potential phantom inventory exceptions.
    
    Triggered when 'POTENTIAL_PHANTOM_INVENTORY' is in compounding_risks.
    Makes HTTP POST to configured webhook URL. If confirmed, updates exception type
    and priority (if returned by webhook).
    """
    if "POTENTIAL_PHANTOM_INVENTORY" not in triage_result.compounding_risks:
        return

    if not config.phantom_webhook_enabled or not config.phantom_webhook_url:
        logger.warning(
            f"Phantom inventory flagged for {triage_result.exception_id} "
            "but webhook is disabled or URL not configured."
        )
        return

    payload = {
        "exception_id": triage_result.exception_id,
        "item_id": triage_result.item_id,
        "store_id": triage_result.store_id,
        "trigger": "TRIAGE_AGENT_FLAG",
        "dc_inventory_days": triage_result.dc_inventory_days,
        "vendor_fill_rate_90d": triage_result.vendor_fill_rate_90d,
        "enrichment_confidence": triage_result.confidence.value,
    }

    try:
        # Strict 5-second timeout to avoid blocking the pipeline
        response = httpx.post(
            config.phantom_webhook_url,
            json=payload,
            timeout=5.0
        )

        if response.status_code != 200:
            logger.warning(
                f"Phantom webhook returned HTTP {response.status_code} "
                f"for {triage_result.exception_id}. Skipping confirmation."
            )
            return

        try:
            data = response.json()
        except Exception as json_err:
            logger.warning(
                f"Phantom webhook returned non-JSON response (HTTP 200) "
                f"for {triage_result.exception_id}: {json_err}"
            )
            return

        if data.get("phantom_confirmed") is True:
            # exception_type is Optional[str] on TriageResult (carried-forward field)
            triage_result.exception_type = ExceptionType.DATA_INTEGRITY.value
            triage_result.phantom_flag = True

            # Use webhook-provided priority, or default to MEDIUM —
            # confirmed phantom = data integrity issue, not urgent stock risk
            if "priority" in data:
                try:
                    triage_result.priority = Priority(data["priority"])
                except ValueError:
                    logger.warning(
                        f"Webhook returned invalid priority {data['priority']!r} "
                        f"for {triage_result.exception_id} — defaulting to MEDIUM."
                    )
                    triage_result.priority = Priority.MEDIUM
            else:
                triage_result.priority = Priority.MEDIUM

            logger.info(
                f"Phantom inventory confirmed for {triage_result.exception_id} "
                f"→ reclassified as DATA_INTEGRITY, priority={triage_result.priority.value}."
            )
        else:
            logger.debug(
                f"Phantom webhook responded — not confirmed for {triage_result.exception_id}."
            )

    except httpx.TimeoutException:
        logger.warning(f"Phantom webhook timed out after 5.0s for {triage_result.exception_id}.")
    except httpx.HTTPError as e:
        logger.warning(f"Phantom webhook connection error for {triage_result.exception_id}: {e}")
    except Exception as e:
        logger.warning(f"Phantom webhook unexpected error for {triage_result.exception_id}: {e}")
