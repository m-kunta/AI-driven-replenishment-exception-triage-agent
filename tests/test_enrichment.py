"""Tests for Layer 2: EnrichmentEngine and DataLoader.

All tests use reference_date=date(2026, 3, 18) for determinism.

Test coverage plan:
    DataLoader
        [ ] test_data_loader_loads_all_sources
              → All 6 lookup dicts are non-empty after .load()
        [ ] test_missing_file_raises_enrichment_error
              → DataLoader with a bad path raises EnrichmentError on .load()

    Store join
        [ ] test_store_fields_populated
              → STR-001 → store_tier=1, region="NORTHEAST", weekly_store_sales_k=2800.0
                           competitor_proximity_miles=0.3

    Item join
        [ ] test_item_fields_populated
              → ITM-1001 → category="Dairy", perishable=True, vendor_id="VND-100"
                            retail_price=5.99

    Promo join
        [ ] test_promo_active_in_window
              → ITM-1001 / STR-001 on 2026-03-18 → promo_active=True, promo_type="TPR"
        [ ] test_promo_expired
              → ITM-1009 / STR-010 (ended 2026-03-10) → promo_active=False

    Vendor join
        [ ] test_vendor_fields_populated
              → VND-400 → vendor_fill_rate_90d=0.72, open_po_inbound=True

    DC inventory join
        [ ] test_dc_inventory_populated
              → ITM-1007 → dc_inventory_days=5.6

    Regional signals join
        [ ] test_regional_disruption_northeast_active
              → STR-001 (NORTHEAST) → regional_disruption_flag=True
        [ ] test_regional_disruption_midwest_expired
              → STR-014 (MIDWEST) on 2026-03-19 (storm ended 2026-03-18)
                → regional_disruption_flag=False

    Financial fields
        [ ] test_financial_no_promo
              → OOS, no promo → est_lost_sales_value > 0, promo_margin_at_risk == 0.0
        [ ] test_financial_with_promo
              → OOS on active TPR item → promo_margin_at_risk > 0.0

    Confidence scoring
        [ ] test_confidence_high_complete_data
              → All enrichment data present → enrichment_confidence=HIGH, missing_data_fields=[]
        [ ] test_confidence_low_unknown_store
              → Unknown store_id → multiple null fields → enrichment_confidence=LOW

    Integration
        [ ] test_enrich_full_sample
              → All 120 sample exceptions enriched without raising
              → All results are EnrichedExceptionSchema instances
"""

from __future__ import annotations

# TODO: implement tests above once DataLoader and EnrichmentEngine are built.
# Follow the same fixture/class patterns used in tests/test_ingestion.py.
# Use tmp_path fixture for any file-based tests.
