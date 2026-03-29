"""EnrichmentEngine for Layer 2: joins CanonicalExceptions with reference data.

Takes the output of Layer 1 (list[CanonicalException]) and produces
list[EnrichedExceptionSchema] ready for Layer 3 (Claude reasoning engine).

Joins applied per exception:
    store_id  → store_master  : store_tier, weekly_store_sales_k, region,
                                competitor_proximity_miles, competitor_event
    item_id   → item_master   : velocity_rank, category, subcategory,
                                retail_price, margin_pct, perishable, vendor_id
    (item_id, store_id) → promo_calendar  : promo_active, promo_type,
                                            promo_end_date, tpr_depth_pct
    vendor_id → vendor_perf   : vendor_fill_rate_90d, open_po_inbound
    item_id   → dc_inventory  : dc_inventory_days, next_delivery_date, lead_time_days
    region    → regional_sig  : regional_disruption_flag, regional_disruption_description

Computed fields:
    est_lost_sales_value  — see _compute_financials (promo / no-promo paths)
    promo_margin_at_risk  — est_lost_sales_value × margin_pct (only if promo_active)
    missing_data_fields   — list of enrichment field names that resolved to None
    enrichment_confidence — HIGH / MEDIUM / LOW based on null count thresholds

Design decisions (resolve after Layer 3 integration):
    1. Promo lost-sales uses promotional price: retail_price × (1 - tpr_depth_pct)
    2. open_po_inbound = open_pos_count > 0
    3. lead_time_days derived as (next_receipt_date − reference_date).days

Usage:
    data = DataLoader().load()
    engine = EnrichmentEngine(data, reference_date=date.today())
    enriched = engine.enrich(canonical_exceptions)

Author: Mohith Kunta <mohith.kunta@gmail.com>
GitHub: https://github.com/m-kunta
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from src.enrichment.data_loader import LoadedData
from src.models import CanonicalException, EnrichedExceptionSchema, EnrichmentConfidence

# Day-of-week demand multipliers relative to the weekly average (1.0 = average day).
# Values reflect typical retail demand patterns: weekend lift, mid-week shoulder.
# These are business constants — calibrate against historical sales data before
# using in financial impact calculations for Layer 3.
_DAY_OF_WEEK_DEMAND_INDEX = {
    0: 0.93,  # Monday   — post-weekend dip
    1: 0.98,  # Tuesday  — recovery begins
    2: 1.05,  # Wednesday — mid-week normalisation
    3: 1.08,  # Thursday  — pre-weekend stock-up starts
    4: 1.15,  # Friday    — peak pre-weekend demand
    5: 1.22,  # Saturday  — highest traffic day
    6: 1.10,  # Sunday    — strong but below Saturday
}

# ---------------------------------------------------------------------------
# Tracked enrichment fields for null-counting / confidence scoring
#
# Only fields that depend on external reference-data joins are tracked here.
# If a join misses (e.g., store_id not in store_master), the field resolves to
# None and is counted toward the enrichment_confidence downgrade.
#
# Excluded from tracking (intentionally):
#   - competitor_proximity_miles / competitor_event: present only for select stores
#   - subcategory: optional merchandising metadata
#   - promo_type / promo_end_date / tpr_depth_pct: derived from promo_active; only
#     meaningful when promo_active is True
#   - next_delivery_date / vendor_id: used for context, not core confidence signal
#   - day_of_week_demand_index: always computed from exception_date; never None
#   - est_lost_sales_value / promo_margin_at_risk: computed fields, not lookups
#   - regional_disruption_description: present only when flag is True
# ---------------------------------------------------------------------------
_TRACKED_ENRICHMENT_FIELDS: List[str] = [
    "store_tier",
    "weekly_store_sales_k",
    "region",
    "velocity_rank",
    "category",
    "retail_price",
    "margin_pct",
    "perishable",
    "vendor_id",
    "vendor_fill_rate_90d",
    "open_po_inbound",
    "dc_inventory_days",
    "promo_active",
    "regional_disruption_flag",
    "lead_time_days",
]


class EnrichmentEngine:
    """Joins each CanonicalException with reference data and computes derived fields.

    Args:
        loaded_data: Pre-loaded reference datasets from DataLoader.
        reference_date: Date to use for all date-sensitive checks (promo windows,
            regional disruptions). Defaults to date.today().
        null_threshold_low: Missing-field count at or above which confidence is LOW.
            Defaults to 3.
        null_threshold_medium: Missing-field count at or above which confidence is
            MEDIUM (below null_threshold_low). Defaults to 1.
        promo_lift_factor: Velocity uplift multiplier for active promotions.
            Defaults to 1.4.
    """

    def __init__(
        self,
        loaded_data: LoadedData,
        reference_date: Optional[date] = None,
        null_threshold_low: int = 3,
        null_threshold_medium: int = 1,
        promo_lift_factor: float = 1.4,
    ) -> None:
        self._data = loaded_data
        self._ref_date = reference_date or date.today()
        self._null_threshold_low = null_threshold_low
        self._null_threshold_medium = null_threshold_medium
        self._promo_lift_factor = promo_lift_factor

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enrich(self, exceptions: List[CanonicalException]) -> List[EnrichedExceptionSchema]:
        """Enrich a list of canonical exceptions with reference data.

        Processes exceptions in order. Never raises — any unexpected error
        for a single exception is caught, logged, and that exception is
        returned with all optional enrichment fields as None.

        Args:
            exceptions: Output from Layer 1 normalizer.

        Returns:
            List of EnrichedExceptionSchema in the same order as input.
        """
        results: List[EnrichedExceptionSchema] = []
        for exc in exceptions:
            try:
                enriched = self._enrich_one(exc)
            except Exception as e:  # pylint: disable=broad-except
                logger.error(
                    f"Unexpected error enriching {exc.exception_id}: {e}. "
                    "Returning a low-confidence fallback record."
                )
                enriched = self._build_failed_enrichment_record(exc)
            results.append(enriched)
        logger.info(f"Enriched {len(results)} exceptions (ref_date={self._ref_date})")
        return results

    # ------------------------------------------------------------------
    # Core enrichment
    # ------------------------------------------------------------------

    def _enrich_one(self, exc: CanonicalException) -> EnrichedExceptionSchema:
        """Enrich a single exception. Returns a fully populated schema."""
        store = self._join_store(exc.store_id)
        item = self._join_item(exc.item_id)

        # vendor_id comes from item master, not from the exception itself
        vendor_id: Optional[str] = item.get("vendor_id")
        vendor = self._join_vendor(vendor_id) if vendor_id else {}

        region: Optional[str] = store.get("region")
        promo = self._join_promo(exc.item_id, exc.store_id)
        dc = self._join_dc(exc.item_id)
        regional = self._join_regional(region) if region else {}

        # Compute financials
        est_lost_sales, promo_margin = self._compute_financials(
            retail_price=item.get("retail_price"),
            days_of_supply=exc.days_of_supply,
            margin_pct=item.get("margin_pct"),
            promo_active=promo.get("promo_active", False),
            tpr_depth_pct=promo.get("tpr_depth_pct"),
        )

        # Collect all enrichment field values for null tracking
        enriched_fields: Dict[str, Any] = {
            "store_tier": store.get("tier"),
            "weekly_store_sales_k": store.get("weekly_sales_k"),
            "region": store.get("region"),
            "competitor_proximity_miles": store.get("competitor_proximity_miles"),
            "competitor_event": store.get("competitor_event"),
            "velocity_rank": item.get("velocity_rank"),
            "category": item.get("category"),
            "subcategory": item.get("subcategory"),
            "retail_price": item.get("retail_price"),
            "margin_pct": item.get("margin_pct"),
            "perishable": item.get("perishable"),
            "vendor_id": vendor_id,
            "vendor_fill_rate_90d": vendor.get("vendor_fill_rate_90d"),
            "open_po_inbound": vendor.get("open_po_inbound"),
            "dc_inventory_days": dc.get("dc_inventory_days"),
            "next_delivery_date": dc.get("next_delivery_date"),
            "lead_time_days": dc.get("lead_time_days"),
            "promo_active": promo.get("promo_active", False),
            "promo_type": promo.get("promo_type"),
            "promo_end_date": promo.get("promo_end_date"),
            "tpr_depth_pct": promo.get("tpr_depth_pct"),
            "regional_disruption_flag": regional.get("regional_disruption_flag"),
            "regional_disruption_description": regional.get("regional_disruption_description"),
            "est_lost_sales_value": est_lost_sales,
            "promo_margin_at_risk": promo_margin,
            "day_of_week_demand_index": self._compute_day_of_week_demand_index(exc.exception_date),
        }

        missing = self._collect_missing(enriched_fields)
        confidence = self._compute_confidence(missing)

        return EnrichedExceptionSchema(
            **exc.model_dump(),
            **enriched_fields,
            missing_data_fields=missing,
            enrichment_confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Join helpers — return {} on miss, never raise
    # ------------------------------------------------------------------

    def _join_store(self, store_id: str) -> Dict[str, Any]:
        """Look up store master by store_id."""
        return self._data.store_master.get(store_id, {})

    def _join_item(self, item_id: str) -> Dict[str, Any]:
        """Look up item master by item_id."""
        return self._data.item_master.get(item_id, {})

    def _join_promo(self, item_id: str, store_id: str) -> Dict[str, Any]:
        """Find active promo for (item_id, store_id) on reference_date.

        Filters promo rows where promo_start_date <= ref_date <= promo_end_date.
        Returns the first matching row as a dict with promo_active=True,
        or {"promo_active": False} if no active promo exists.
        """
        rows = self._data.promo_calendar.get((item_id, store_id), [])
        for row in rows:
            start_str = row.get("promo_start_date", "")
            end_str = row.get("promo_end_date", "")
            try:
                start = date.fromisoformat(start_str)
                end = date.fromisoformat(end_str)
            except (ValueError, TypeError):
                continue
            if start <= self._ref_date <= end:
                return {
                    "promo_active": True,
                    "promo_type": row.get("promo_type"),
                    "promo_end_date": end,
                    "tpr_depth_pct": row.get("tpr_depth_pct"),
                }
        return {"promo_active": False}

    def _join_vendor(self, vendor_id: str) -> Dict[str, Any]:
        """Look up vendor performance by vendor_id.

        open_po_inbound is derived as open_pos_count > 0 (Decision #2).
        """
        row = self._data.vendor_performance.get(vendor_id, {})
        if not row:
            return {}
        open_pos = row.get("open_pos_count")
        return {
            "vendor_fill_rate_90d": row.get("fill_rate_90d"),
            "open_po_inbound": (open_pos > 0) if open_pos is not None else None,
        }

    def _join_dc(self, item_id: str) -> Dict[str, Any]:
        """Look up DC inventory by item_id.

        lead_time_days is derived as (next_receipt_date - reference_date).days
        (Decision #3). Falls back to None if the date is absent or unparseable.
        """
        row = self._data.dc_inventory.get(item_id, {})
        if not row:
            return {}

        lead_time_days: Optional[int] = None
        next_receipt_str = row.get("next_receipt_date")
        next_delivery: Optional[date] = None
        if next_receipt_str:
            try:
                next_delivery = date.fromisoformat(next_receipt_str)
                lead_time_days = (next_delivery - self._ref_date).days
            except (ValueError, TypeError):
                pass

        return {
            "dc_inventory_days": row.get("days_of_supply"),
            "next_delivery_date": next_delivery,
            "lead_time_days": lead_time_days,
        }

    def _join_regional(self, region: str) -> Dict[str, Any]:
        """Find active regional disruption for region on reference_date.

        Filters disruptions where active_from <= ref_date <= active_through.
        Returns regional_disruption_flag=True/False + description.
        """
        disruptions = self._data.regional_signals.get(region, [])
        for d in disruptions:
            try:
                active_from = date.fromisoformat(d.get("active_from", ""))
                active_through = date.fromisoformat(d.get("active_through", ""))
            except (ValueError, TypeError):
                continue
            if active_from <= self._ref_date <= active_through:
                return {
                    "regional_disruption_flag": True,
                    "regional_disruption_description": d.get("description"),
                }
        return {
            "regional_disruption_flag": False,
            "regional_disruption_description": None,
        }

    # ------------------------------------------------------------------
    # Computed fields
    # ------------------------------------------------------------------

    def _compute_financials(
        self,
        retail_price: Optional[float],
        days_of_supply: float,
        margin_pct: Optional[float],
        promo_active: bool,
        tpr_depth_pct: Optional[float],
    ) -> Tuple[float, float]:
        """Compute est_lost_sales_value and promo_margin_at_risk.

        No-promo: retail_price × clamp(7 − dos, 0, 7)
        Promo:    retail_price × (1 − tpr_depth_pct) × clamp(7 − dos, 0, 7) × lift

        Returns (0.0, 0.0) if retail_price is None.
        """
        if retail_price is None:
            return (0.0, 0.0)

        days_of_exposure = max(0.0, min(7.0, 7.0 - days_of_supply))

        if promo_active and tpr_depth_pct is not None:
            # Decision #1: use promotional (discounted) price
            est_lost_sales = (
                retail_price
                * (1.0 - tpr_depth_pct)
                * days_of_exposure
                * self._promo_lift_factor
            )
        else:
            est_lost_sales = retail_price * days_of_exposure

        promo_margin = 0.0
        if promo_active and margin_pct is not None:
            promo_margin = est_lost_sales * margin_pct

        return (round(est_lost_sales, 2), round(promo_margin, 2))

    def _collect_missing(self, enriched_dict: Dict[str, Any]) -> List[str]:
        """Return list of tracked enrichment field names whose value is None."""
        return [f for f in _TRACKED_ENRICHMENT_FIELDS if enriched_dict.get(f) is None]

    def _compute_confidence(self, missing_fields: List[str]) -> EnrichmentConfidence:
        """Assign enrichment confidence based on number of null fields.

        0 nulls → HIGH | 1-2 → MEDIUM | ≥3 → LOW
        Thresholds are configurable via constructor params.
        """
        count = len(missing_fields)
        if count >= self._null_threshold_low:
            return EnrichmentConfidence.LOW
        if count >= self._null_threshold_medium:
            return EnrichmentConfidence.MEDIUM
        return EnrichmentConfidence.HIGH

    def _compute_day_of_week_demand_index(self, exception_date: date) -> float:
        """Return the demand index for the day of the week of exception_date.

        Uses date.weekday() (0=Monday … 6=Sunday), which is always a key in
        _DAY_OF_WEEK_DEMAND_INDEX, so the lookup never raises KeyError.
        """
        return _DAY_OF_WEEK_DEMAND_INDEX[exception_date.weekday()]

    def _build_failed_enrichment_record(
        self, exc: CanonicalException
    ) -> EnrichedExceptionSchema:
        """Build a safe fallback record when _enrich_one raises an unexpected error.

        All optional enrichment fields default to None. The sentinel value
        "enrichment_failed" in missing_data_fields signals to Layer 3 that
        the enrichment pipeline itself failed (not just a missing lookup), so
        the AI reasoning layer can handle it with appropriate caution rather
        than treating it as a normally low-confidence record.
        """
        return EnrichedExceptionSchema(
            **exc.model_dump(),
            missing_data_fields=["enrichment_failed"],
            enrichment_confidence=EnrichmentConfidence.LOW,
        )
