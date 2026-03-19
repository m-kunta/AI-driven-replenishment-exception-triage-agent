"""Tests for Layer 2: EnrichmentEngine and DataLoader.

All tests use reference_date=date(2026, 3, 18) for determinism.

Test coverage plan:
    DataLoader
        [x] test_data_loader_loads_all_sources
              → All 6 lookup dicts are non-empty after .load()
        [x] test_missing_file_raises_enrichment_error
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

import json
from pathlib import Path

import pytest

from src.enrichment.data_loader import DataLoader, LoadedData
from src.utils.exceptions import EnrichmentError


SAMPLE_DIR = Path(__file__).parent.parent / "data" / "sample"
REGIONAL_SIGNALS = Path(__file__).parent.parent / "data" / "regional_signals.json"


class TestDataLoader:
    def test_data_loader_loads_all_sources(self):
        """All 6 lookup dicts are non-empty after .load() against sample data."""
        loader = DataLoader(
            store_master_path=str(SAMPLE_DIR / "store_master_sample.csv"),
            item_master_path=str(SAMPLE_DIR / "item_master_sample.csv"),
            promo_calendar_path=str(SAMPLE_DIR / "promo_calendar_sample.csv"),
            vendor_performance_path=str(SAMPLE_DIR / "vendor_performance_sample.csv"),
            dc_inventory_path=str(SAMPLE_DIR / "dc_inventory_sample.csv"),
            regional_signals_path=str(REGIONAL_SIGNALS),
        )
        data = loader.load()

        assert isinstance(data, LoadedData)
        assert len(data.store_master) > 0, "store_master should not be empty"
        assert len(data.item_master) > 0, "item_master should not be empty"
        assert len(data.promo_calendar) > 0, "promo_calendar should not be empty"
        assert len(data.vendor_performance) > 0, "vendor_performance should not be empty"
        assert len(data.dc_inventory) > 0, "dc_inventory should not be empty"
        assert len(data.regional_signals) > 0, "regional_signals should not be empty"

        # Spot-check a known record from each source
        assert "STR-001" in data.store_master
        assert data.store_master["STR-001"]["tier"] == 1
        assert data.store_master["STR-001"]["region"] == "NORTHEAST"
        assert data.store_master["STR-001"]["weekly_sales_k"] == pytest.approx(2800.0)
        assert data.store_master["STR-001"]["competitor_proximity_miles"] == pytest.approx(0.3)

        assert "ITM-1001" in data.item_master
        assert data.item_master["ITM-1001"]["category"] == "Dairy"
        assert data.item_master["ITM-1001"]["perishable"] is True
        assert data.item_master["ITM-1001"]["vendor_id"] == "VND-100"
        assert data.item_master["ITM-1001"]["retail_price"] == pytest.approx(5.99)

        assert ("ITM-1001", "STR-001") in data.promo_calendar
        promo = data.promo_calendar[("ITM-1001", "STR-001")][0]
        assert promo["promo_type"] == "TPR"
        assert promo["tpr_depth_pct"] == pytest.approx(0.25)

        assert "VND-400" in data.vendor_performance
        assert data.vendor_performance["VND-400"]["fill_rate_90d"] == pytest.approx(0.72)

        assert "ITM-1001" in data.dc_inventory
        assert data.dc_inventory["ITM-1001"]["days_of_supply"] == pytest.approx(35.0)

        assert "NORTHEAST" in data.regional_signals
        assert len(data.regional_signals["NORTHEAST"]) >= 1

    def test_missing_file_raises_enrichment_error(self, tmp_path):
        """DataLoader raises EnrichmentError when a source file does not exist."""
        loader = DataLoader(
            store_master_path=str(tmp_path / "nonexistent_store_master.csv"),
            item_master_path=str(SAMPLE_DIR / "item_master_sample.csv"),
            promo_calendar_path=str(SAMPLE_DIR / "promo_calendar_sample.csv"),
            vendor_performance_path=str(SAMPLE_DIR / "vendor_performance_sample.csv"),
            dc_inventory_path=str(SAMPLE_DIR / "dc_inventory_sample.csv"),
            regional_signals_path=str(REGIONAL_SIGNALS),
        )
        with pytest.raises(EnrichmentError, match="not found"):
            loader.load()

    def test_missing_regional_signals_raises_enrichment_error(self, tmp_path):
        """DataLoader raises EnrichmentError when regional_signals JSON is missing."""
        loader = DataLoader(
            store_master_path=str(SAMPLE_DIR / "store_master_sample.csv"),
            item_master_path=str(SAMPLE_DIR / "item_master_sample.csv"),
            promo_calendar_path=str(SAMPLE_DIR / "promo_calendar_sample.csv"),
            vendor_performance_path=str(SAMPLE_DIR / "vendor_performance_sample.csv"),
            dc_inventory_path=str(SAMPLE_DIR / "dc_inventory_sample.csv"),
            regional_signals_path=str(tmp_path / "nonexistent_signals.json"),
        )
        with pytest.raises(EnrichmentError, match="not found"):
            loader.load()

    def test_malformed_regional_signals_raises_enrichment_error(self, tmp_path):
        """DataLoader raises EnrichmentError on malformed regional signals JSON."""
        bad_json = tmp_path / "bad_signals.json"
        bad_json.write_text("this is not valid json {{{")
        loader = DataLoader(
            store_master_path=str(SAMPLE_DIR / "store_master_sample.csv"),
            item_master_path=str(SAMPLE_DIR / "item_master_sample.csv"),
            promo_calendar_path=str(SAMPLE_DIR / "promo_calendar_sample.csv"),
            vendor_performance_path=str(SAMPLE_DIR / "vendor_performance_sample.csv"),
            dc_inventory_path=str(SAMPLE_DIR / "dc_inventory_sample.csv"),
            regional_signals_path=str(bad_json),
        )
        with pytest.raises(EnrichmentError, match="Failed to parse"):
            loader.load()

    def test_promo_calendar_indexed_by_item_store_tuple(self):
        """Promo calendar keys are (item_id, store_id) tuples."""
        loader = DataLoader(
            store_master_path=str(SAMPLE_DIR / "store_master_sample.csv"),
            item_master_path=str(SAMPLE_DIR / "item_master_sample.csv"),
            promo_calendar_path=str(SAMPLE_DIR / "promo_calendar_sample.csv"),
            vendor_performance_path=str(SAMPLE_DIR / "vendor_performance_sample.csv"),
            dc_inventory_path=str(SAMPLE_DIR / "dc_inventory_sample.csv"),
            regional_signals_path=str(REGIONAL_SIGNALS),
        )
        data = loader.load()
        for key in data.promo_calendar:
            assert isinstance(key, tuple), "Keys must be (item_id, store_id) tuples"
            assert len(key) == 2

    def test_competitor_event_none_when_empty(self):
        """competitor_event is None (not empty string) when the CSV cell is blank."""
        loader = DataLoader(
            store_master_path=str(SAMPLE_DIR / "store_master_sample.csv"),
            item_master_path=str(SAMPLE_DIR / "item_master_sample.csv"),
            promo_calendar_path=str(SAMPLE_DIR / "promo_calendar_sample.csv"),
            vendor_performance_path=str(SAMPLE_DIR / "vendor_performance_sample.csv"),
            dc_inventory_path=str(SAMPLE_DIR / "dc_inventory_sample.csv"),
            regional_signals_path=str(REGIONAL_SIGNALS),
        )
        data = loader.load()
        # STR-002 has an empty competitor_event in the sample data
        store = data.store_master.get("STR-002", {})
        assert store.get("competitor_event") is None


# TODO: implement tests above once DataLoader and EnrichmentEngine are built.
# Follow the same fixture/class patterns used in tests/test_ingestion.py.
# Use tmp_path fixture for any file-based tests.
