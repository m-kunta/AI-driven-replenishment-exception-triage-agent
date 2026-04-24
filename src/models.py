"""Pydantic models for all data schemas used across the triage pipeline.

Author: Mohith Kunta <mohith.kunta@gmail.com>
GitHub: https://github.com/m-kunta
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class ExceptionType(str, enum.Enum):
    """Type of replenishment exception surfaced by the planning system.

    OOS             — On-hand units are zero; item is out of stock.
    LOW_STOCK       — On-hand is above zero but below a safety-stock threshold.
    FORECAST_VARIANCE — Actual sales deviate materially from the forecast.
    ORDER_FAILURE   — A replenishment order failed to generate or transmit.
    VENDOR_LATE     — Expected vendor shipment has not arrived by the due date.
    DATA_INTEGRITY  — Record-level data quality issue (phantom inventory, etc.).
    """

    OOS = "OOS"
    LOW_STOCK = "LOW_STOCK"
    FORECAST_VARIANCE = "FORECAST_VARIANCE"
    ORDER_FAILURE = "ORDER_FAILURE"
    VENDOR_LATE = "VENDOR_LATE"
    DATA_INTEGRITY = "DATA_INTEGRITY"


class PromoType(str, enum.Enum):
    """Promotional mechanic active for an item at a store.

    TPR     — Temporary Price Reduction (shelf price is discounted).
    FEATURE — Item featured in a weekly circular or end-cap display.
    DISPLAY — Secondary display (off-shelf placement, e.g. aisle cap).
    BOTH    — TPR combined with a circular feature in the same week.
    NONE    — No active promotion.
    """

    TPR = "TPR"
    FEATURE = "FEATURE"
    DISPLAY = "DISPLAY"
    BOTH = "BOTH"
    NONE = "NONE"


class EnrichmentConfidence(str, enum.Enum):
    """Confidence that the enriched record has sufficient context for AI triage.

    Derived by counting how many tracked enrichment fields resolved to None
    after all reference-data joins. Thresholds are configurable on EnrichmentEngine.

    HIGH   — 0 tracked fields are null; all key signals are present.
    MEDIUM — 1–2 tracked fields are null; triage can proceed with caveats.
    LOW    — ≥3 tracked fields are null, or enrichment itself raised an exception.
    """

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class Priority(str, enum.Enum):
    """AI-assigned triage priority for a replenishment exception.

    CRITICAL — Immediate action required; high financial impact or customer risk.
    HIGH     — Urgent but allows same-day resolution window.
    MEDIUM   — Important; can be queued for same-week resolution.
    LOW      — Informational; no immediate action needed.
    """

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class PatternType(str, enum.Enum):
    """Type of systemic pattern identified across multiple exceptions.

    VENDOR   — Multiple exceptions share the same underperforming vendor.
    DC_LANE  — Multiple exceptions originate from the same DC-to-store lane.
    CATEGORY — Multiple exceptions cluster within a single product category.
    REGION   — Multiple exceptions are concentrated in a geographic region.
    MACRO    — Broad cross-cutting pattern spanning multiple dimensions.
    """

    VENDOR = "VENDOR"
    DC_LANE = "DC_LANE"
    CATEGORY = "CATEGORY"
    REGION = "REGION"
    MACRO = "MACRO"


# --- Layer 1: Canonical Exception Schema ---

class CanonicalException(BaseModel):
    """Schema for normalized exception records output by the ingestion layer."""
    model_config = ConfigDict(extra="forbid")

    exception_id: str = Field(description="Unique identifier for this exception instance")
    item_id: str = Field(description="Internal SKU identifier")
    item_name: str = Field(description="Human-readable item description")
    store_id: str = Field(description="Store identifier")
    store_name: str = Field(description="Human-readable store name")
    exception_type: ExceptionType = Field(description="Type of replenishment exception")
    exception_date: date = Field(description="Date the exception occurred")
    units_on_hand: int = Field(description="Current units on hand at store")
    days_of_supply: float = Field(description="Days of supply at current velocity")
    variance_pct: Optional[float] = Field(default=None, description="Forecast vs actual variance percentage")
    source_system: str = Field(description="Name of originating planning system")
    batch_id: str = Field(description="UUID for the ingestion batch")
    ingested_at: datetime = Field(description="Timestamp when the exception was ingested")


# --- Layer 2: Enriched Exception Schema ---

class EnrichedExceptionSchema(BaseModel):
    """Schema for enriched exception records, input to the AI triage layer."""
    model_config = ConfigDict(extra="forbid")

    # Canonical fields — carried forward unchanged from Layer 1
    exception_id: str = Field(description="Unique identifier for this exception instance")
    item_id: str = Field(description="Internal SKU identifier")
    item_name: str = Field(description="Human-readable item description")
    store_id: str = Field(description="Store identifier")
    store_name: str = Field(description="Human-readable store name")
    exception_type: ExceptionType = Field(description="Type of replenishment exception")
    exception_date: date = Field(description="Date the exception occurred")
    units_on_hand: int = Field(description="Current units on hand at store")
    days_of_supply: float = Field(description="Days of supply at current velocity")
    variance_pct: Optional[float] = Field(default=None, description="Forecast vs actual variance percentage")
    source_system: str = Field(description="Name of originating planning system")
    batch_id: str = Field(description="UUID for the ingestion batch")
    ingested_at: datetime = Field(description="Timestamp when the exception was ingested")

    # Enrichment fields
    velocity_rank: Optional[int] = Field(default=None, description="Item rank within category by weekly units")
    category: Optional[str] = Field(default=None, description="Item category")
    subcategory: Optional[str] = Field(default=None, description="Item subcategory")
    retail_price: Optional[float] = Field(default=None, description="Item retail price in USD")
    margin_pct: Optional[float] = Field(default=None, description="Item margin percentage")
    store_tier: Optional[int] = Field(default=None, description="Store tier 1 (highest) to 4 (lowest)")
    weekly_store_sales_k: Optional[float] = Field(default=None, description="Store weekly revenue in thousands USD")
    region: Optional[str] = Field(default=None, description="Store region")
    promo_active: Optional[bool] = Field(default=None, description="Whether item is on active promo")
    promo_type: Optional[PromoType] = Field(
        default=None,
        description="Promo type: TPR, FEATURE, DISPLAY, BOTH, NONE",
    )
    promo_end_date: Optional[date] = Field(default=None, description="Promo end date")
    tpr_depth_pct: Optional[float] = Field(default=None, description="TPR depth percentage")
    dc_inventory_days: Optional[float] = Field(default=None, description="Days of supply at DC for this item")
    vendor_id: Optional[str] = Field(default=None, description="Vendor identifier")
    vendor_fill_rate_90d: Optional[float] = Field(default=None, description="Vendor fill rate % last 90 days")
    open_po_inbound: Optional[bool] = Field(default=None, description="Whether there is an open PO inbound")
    next_delivery_date: Optional[date] = Field(default=None, description="Next expected delivery date")
    lead_time_days: Optional[int] = Field(default=None, description="Lead time in days")
    competitor_proximity_miles: Optional[float] = Field(default=None, description="Distance to nearest competitor in miles")
    competitor_event: Optional[str] = Field(default=None, description="Description of competitor activity")
    perishable: Optional[bool] = Field(default=None, description="Whether item is perishable")
    day_of_week_demand_index: Optional[float] = Field(default=None, description="Day-of-week demand index (1.0 = average)")
    est_lost_sales_value: Optional[float] = Field(default=None, description="Estimated lost sales in USD")
    promo_margin_at_risk: Optional[float] = Field(default=None, description="Promo margin at risk in USD")
    regional_disruption_flag: Optional[bool] = Field(default=None, description="Whether regional disruption is active")
    regional_disruption_description: Optional[str] = Field(default=None, description="Description of regional disruption")
    missing_data_fields: List[str] = Field(
        default_factory=list,
        description="Missing enrichment field names or sentinel flags such as 'enrichment_failed'",
    )
    enrichment_confidence: EnrichmentConfidence = Field(default=EnrichmentConfidence.HIGH, description="Confidence based on missing data count")


# --- Layer 3: AI Triage Output ---

class TriageResult(BaseModel):
    """AI triage output for a single replenishment exception (Layer 3 → Layer 4).

    Produced by the Claude reasoning engine for each EnrichedExceptionSchema.
    Contains the priority decision, human-readable briefs, financial impact,
    compounding risk flags, and optional pattern linkage.

    Fields marked as "carried forward" are copied from the enriched record so
    the output layer does not need to rejoin back to Layer 2 data.

    Mutable by design: the phantom webhook and pattern analyzer both mutate
    fields (exception_type, priority, phantom_flag, pattern_id, escalated_from)
    after initial AI assignment.
    """
    model_config = ConfigDict(extra="ignore")

    exception_id: str
    priority: Priority
    confidence: EnrichmentConfidence
    root_cause: str = Field(description="AI-determined root cause (max 30 words)")
    recommended_action: str = Field(description="Specific action for the planner (max 25 words)")
    financial_impact_statement: str = Field(description="Financial impact in plain English (max 20 words)")
    planner_brief: str = Field(description="Full context brief for the planner (max 75 words)")
    compounding_risks: List[str] = Field(default_factory=list, description="List of compounding risk flags")
    missing_data_flags: List[str] = Field(default_factory=list, description="Fields that were missing during triage")
    pattern_id: Optional[str] = Field(default=None, description="Pattern group ID if part of a systemic pattern")
    escalated_from: Optional[str] = Field(default=None, description="Original priority if escalated due to pattern")
    phantom_flag: bool = Field(default=False, description="Whether phantom inventory was flagged")
    reasoning_trace: Optional[str] = Field(default=None, description="Chain-of-thought reasoning (if enabled)")

    # Enrichment data carried forward for output layer
    item_id: Optional[str] = None
    item_name: Optional[str] = None
    store_id: Optional[str] = None
    store_name: Optional[str] = None
    exception_type: Optional[str] = None
    exception_date: Optional[date] = None
    days_of_supply: Optional[float] = None
    store_tier: Optional[int] = None
    promo_active: Optional[bool] = None
    est_lost_sales_value: Optional[float] = Field(default=0.0)
    promo_margin_at_risk: Optional[float] = Field(default=0.0)
    dc_inventory_days: Optional[float] = None
    vendor_fill_rate_90d: Optional[float] = None


class PatternDetail(BaseModel):
    """A single systemic pattern identified across multiple triage results.

    Patterns are detected by the Layer 3 reasoning engine when multiple
    exceptions share a common root cause (same vendor, DC lane, category,
    or region). Exceptions within a pattern may be escalated in priority.
    """
    pattern_id: str
    pattern_type: PatternType
    group_key: str = Field(description="The vendor/dc/category/region identifier")
    affected_count: int
    critical_count: int = 0
    high_count: int = 0
    description: str
    escalation_count: int = 0
    affected_exception_ids: List[str] = Field(default_factory=list)


class MacroPatternReport(BaseModel):
    """Aggregated report of all systemic patterns detected in a single triage run.

    Included in TriageRunResult and surfaced in the morning briefing document.
    """
    patterns: List[PatternDetail] = Field(default_factory=list)
    total_patterns: int = 0
    total_escalations: int = 0


class RunStatistics(BaseModel):
    """Execution and outcome statistics for a completed triage run.

    Tracks priority distribution, batch success/failure counts, pattern
    escalations, phantom inventory flags, API token usage, and wall-clock
    duration. Used for observability, cost tracking, and run-over-run comparison.
    """
    total_exceptions: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    batches_completed: int = 0
    batches_failed: int = 0
    pattern_escalations: int = 0
    phantom_flags: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    pipeline_duration_seconds: float = 0.0


class TriageRunResult(BaseModel):
    """Top-level container for the complete output of one triage pipeline run.

    Produced by Layer 3 and consumed by Layer 4 (routing, alerting, briefing).
    Contains all individual triage results, the macro pattern report, and run
    statistics in a single serializable object.
    """
    run_id: str
    run_date: date
    triage_results: List[TriageResult] = Field(default_factory=list)
    pattern_report: MacroPatternReport = Field(default_factory=MacroPatternReport)
    statistics: RunStatistics = Field(default_factory=RunStatistics)
    run_timestamp: datetime


# --- Layer 4: Actions ---

class ActionType(str, enum.Enum):
    CREATE_REVIEW = "CREATE_REVIEW"
    REQUEST_VERIFICATION = "REQUEST_VERIFICATION"
    VENDOR_FOLLOW_UP = "VENDOR_FOLLOW_UP"
    STORE_CHECK = "STORE_CHECK"
    DEFER = "DEFER"

class ActionStatus(str, enum.Enum):
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"
    COMPLETED = "completed"

class ActionRequest(BaseModel):
    request_id: str
    exception_id: str
    run_date: date
    action_type: ActionType
    requested_by: Optional[str] = None
    requested_by_role: str
    payload: dict = Field(default_factory=dict)

class ActionRecord(BaseModel):
    request_id: str
    exception_id: str
    run_date: date
    action_type: ActionType
    requested_by: str
    requested_by_role: str
    payload: dict
    status: ActionStatus
    created_at: datetime
    updated_at: datetime
    failure_reason: Optional[str] = None
    downstream_response: Optional[dict] = None
