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
    est_lost_sales_value  — retail_price × max(0, 7 - days_of_supply) [× promo_lift if promo]
    promo_margin_at_risk  — est_lost_sales_value × margin_pct (only if promo_active)
    missing_data_fields   — list of enrichment field names that resolved to None
    enrichment_confidence — HIGH / MEDIUM / LOW based on null count thresholds in config

Usage:
    data = DataLoader().load()
    engine = EnrichmentEngine(data, reference_date=date.today())
    enriched = engine.enrich(canonical_exceptions)
"""

from __future__ import annotations

# TODO: implement EnrichmentEngine
# See implementation_plan.md for full spec.
#
# Implementation checklist:
#   [ ] EnrichmentEngine.__init__(self, loaded_data: LoadedData,
#                                  reference_date: date | None = None)
#         → default reference_date = date.today()
#         → read null_threshold_low_confidence and null_threshold_medium_confidence
#           from config (or accept as params for testability)
#         → read promo_lift_factor from config (default 1.4)
#
#   [ ] EnrichmentEngine.enrich(exceptions: list[CanonicalException])
#         → list[EnrichedExceptionSchema]  (same order, no raises)
#
#   [ ] EnrichmentEngine._enrich_one(exc: CanonicalException)
#         → EnrichedExceptionSchema
#         → call each join helper; catch KeyError/missing data gracefully
#
#   [ ] _join_store(store_id) → dict  (or {} on miss)
#   [ ] _join_item(item_id)   → dict  (or {} on miss)
#   [ ] _join_promo(item_id, store_id, reference_date) → dict | None
#         → filter promo rows where start <= reference_date <= end
#   [ ] _join_vendor(vendor_id) → dict (or {} on miss)
#   [ ] _join_dc(item_id) → dict (or {} on miss)
#   [ ] _join_regional(region, reference_date) → dict | None
#         → filter disruptions where active_from <= reference_date <= active_through
#
#   [ ] _compute_financials(enriched_fields) → (est_lost_sales, promo_margin_at_risk)
#         Promo path:  retail_price × (1 - tpr_depth_pct) × clamp(7 - dos, 0, 7) × lift
#         No-promo:    retail_price × max(0, 7 - days_of_supply)
#
#   [ ] _compute_confidence(missing_fields: list[str]) → EnrichmentConfidence
#         0 nulls → HIGH | 1-2 → MEDIUM | >=3 → LOW
#
#   [ ] _collect_missing(enriched_dict) → list[str]
#         → keys where value is None
