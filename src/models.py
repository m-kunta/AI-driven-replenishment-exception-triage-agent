"""Pydantic models for all data schemas used across the triage pipeline."""

from __future__ import annotations

import enum
from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class ExceptionType(str, enum.Enum):
    OOS = "OOS"
    LOW_STOCK = "LOW_STOCK"
    FORECAST_VARIANCE = "FORECAST_VARIANCE"
    ORDER_FAILURE = "ORDER_FAILURE"
    VENDOR_LATE = "VENDOR_LATE"
    DATA_INTEGRITY = "DATA_INTEGRITY"


class PromoType(str, enum.Enum):
    TPR = "TPR"
    FEATURE = "FEATURE"
    DISPLAY = "DISPLAY"
    BOTH = "BOTH"
    NONE = "NONE"


class EnrichmentConfidence(str, enum.Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class Priority(str, enum.Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class PatternType(str, enum.Enum):
    VENDOR = "VENDOR"
    DC_LANE = "DC_LANE"
    CATEGORY = "CATEGORY"
    REGION = "REGION"
    MACRO = "MACRO"


# --- Layer 1: Canonical Exception Schema ---

class CanonicalException(BaseModel):
    """Schema for normalized exception records output by the ingestion layer."""
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
    # Canonical fields
    exception_id: str
    item_id: str
    item_name: str
    store_id: str
    store_name: str
    exception_type: ExceptionType
    exception_date: date
    units_on_hand: int
    days_of_supply: float
    variance_pct: Optional[float] = None
    source_system: str
    batch_id: str
    ingested_at: datetime

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
    promo_type: Optional[str] = Field(default=None, description="Promo type: TPR, FEATURE, DISPLAY, BOTH, NONE")
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
    missing_data_fields: List[str] = Field(default_factory=list, description="Field names that are null")
    enrichment_confidence: EnrichmentConfidence = Field(default=EnrichmentConfidence.HIGH, description="Confidence based on missing data count")


# --- Layer 3: AI Triage Output ---

class TriageResult(BaseModel):
    """AI triage output for a single exception."""
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
    days_of_supply: Optional[float] = None
    store_tier: Optional[int] = None
    promo_active: Optional[bool] = None
    est_lost_sales_value: Optional[float] = Field(default=0.0)
    promo_margin_at_risk: Optional[float] = Field(default=0.0)


class PatternDetail(BaseModel):
    """A single identified systemic pattern."""
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
    """Report of all systemic patterns detected in a triage run."""
    patterns: List[PatternDetail] = Field(default_factory=list)
    total_patterns: int = 0
    total_escalations: int = 0


class RunStatistics(BaseModel):
    """Statistics for a triage run."""
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
    """Complete result of a triage run."""
    run_id: str
    run_date: date
    triage_results: List[TriageResult] = Field(default_factory=list)
    pattern_report: MacroPatternReport = Field(default_factory=MacroPatternReport)
    statistics: RunStatistics = Field(default_factory=RunStatistics)
    run_timestamp: datetime
