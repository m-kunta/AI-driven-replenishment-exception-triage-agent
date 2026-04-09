"""Alert dispatcher for CRITICAL and HIGH priority triage exceptions.

Author: Mohith Kunta <mohith.kunta@gmail.com>
GitHub: https://github.com/m-kunta
"""
from __future__ import annotations

import logging
import smtplib
import threading
from email.message import EmailMessage

import httpx

from src.models import EnrichmentConfidence, Priority, TriageResult, TriageRunResult
from src.utils.config_loader import AppConfig

logger = logging.getLogger(__name__)


class AlertDispatcher:
    """Dispatches alerts for CRITICAL and HIGH priority exceptions."""

    def __init__(self, config: AppConfig):
        self.config = config

    def format_alert(self, result: TriageResult, run_result: TriageRunResult, is_escalation: bool = False) -> str:
        """Formats the alert text according to standard template."""
        
        miss_fields = result.missing_data_flags or []
        missing_data_note = f"Missing Data: {', '.join(miss_fields)}" if miss_fields else "Missing Data: None"
        
        confidence = result.confidence.value
        if result.confidence == EnrichmentConfidence.LOW:
            confidence += " ⚠️ LOW CONFIDENCE — verify " + (", ".join(miss_fields) if miss_fields else "data") + " before acting."
            
        header = f"🚨 REPLENISHMENT TRIAGE ALERT — {result.priority.value}"
        if is_escalation:
            # We don't have exact time in string unless passed, so we do a general string
            esc_mins = self.config.alerting.critical_sla_minutes
            header = f"[ESCALATION] Unacknowledged after {esc_mins} minutes.\n\n" + header

        days = "UNKNOWN"
        if result.days_of_supply is not None:
            days = f"{result.days_of_supply:.1f}"

        body = f"""{header}

Item: {result.item_name} | Store: {result.store_name} (Tier {result.store_tier})
Exception: {result.exception_type} | Days of Supply: {days}
Financial Exposure: ${result.est_lost_sales_value or 0.0:,.0f} lost sales | ${result.promo_margin_at_risk or 0.0:,.0f} promo margin at risk

ACTION REQUIRED: {result.recommended_action}

{result.planner_brief}

Root Cause: {result.root_cause}
Confidence: {confidence}
{missing_data_note}

Run ID: {run_result.run_id} | Generated: {run_result.run_timestamp.isoformat()}
"""
        return body

    def _send_webhook(self, url: str, content: str):
        """Dispatches an alert to an HTTP webhook."""
        try:
            response = httpx.post(url, json={"text": content}, timeout=10.0)
            response.raise_for_status()
            logger.info("Webhook dispatched successfully to %s", url)
        except httpx.HTTPError as e:
            logger.error("Failed to sequence webhook dispatch to %s: %s", url, e)

    def _send_email(self, host: str, port: int, from_addr: str, to_addrs: list[str], subject: str, content: str):
        """Dispatches an alert via SMTP."""
        msg = EmailMessage()
        msg.set_content(content)
        msg['Subject'] = subject
        msg['From'] = from_addr
        msg['To'] = ", ".join(to_addrs)

        try:
            with smtplib.SMTP(host, port) as server:
                server.send_message(msg)
            logger.info("Email dispatched successfully to %s", to_addrs)
        except smtplib.SMTPException as e:
            logger.error("SMTP error during email dispatch: %s", e)
        except OSError as e:
            logger.error("Network error connecting to SMTP server %s:%d — %s", host, port, e)

    def _dispatch_text(self, text: str, subject: str = "Triage Alert"):
        """Iterates over configured channels to dispatch a given text."""
        for channel in self.config.alerting.channels:
            if not channel.enabled:
                continue
                
            if channel.type in ("slack", "teams", "webhook") and channel.webhook_url:
                self._send_webhook(channel.webhook_url, text)
                
            elif channel.type == "email" and channel.smtp_host and channel.from_address and channel.to_addresses:
                self._send_email(
                    channel.smtp_host,
                    channel.smtp_port or 587,
                    channel.from_address,
                    channel.to_addresses,
                    subject,
                    text
                )

    def dispatch(self, run_result: TriageRunResult):
        """Scans for actionable exceptions and dispatches configured alerts."""
        for result in run_result.triage_results:
            if result.priority not in (Priority.CRITICAL, Priority.HIGH):
                continue
                
            alert_text = self.format_alert(result, run_result)
            self._dispatch_text(alert_text, subject=f"Triage Alert - {result.priority.value}: {result.item_name}")

            # Kick off SLA escalation timer for CRITICAL and HIGH
            if result.priority in (Priority.CRITICAL, Priority.HIGH):
                self.schedule_escalation(result, run_result)

    def schedule_escalation(self, result: TriageResult, run_result: TriageRunResult):
        """Schedules a thread timer for SLA escalation."""
        sla_seconds = self.config.alerting.critical_sla_minutes * 60
        
        def escalation_callback():
            # In a real environment we would check if it was acknowledged. 
            # For this MVP simulation, we just fire it.
            logger.warning("SLA Escalation triggered for %s", result.exception_id)
            escalated_text = self.format_alert(result, run_result, is_escalation=True)
            self._dispatch_text(escalated_text, subject=f"ESCALATION ALERT - {result.exception_id}")

        timer = threading.Timer(sla_seconds, escalation_callback)
        timer.daemon = True # Keep it daemon so it doesn't block shutdown
        timer.start()
        logger.info("Scheduled SLA escalation timer for %s in %d mins", result.exception_id, self.config.alerting.critical_sla_minutes)
