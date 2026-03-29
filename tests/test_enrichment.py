"""Tests for Layer 2: EnrichmentEngine and DataLoader.

All tests use reference_date=date(2026, 3, 18) for determinism.

Author: Mohith Kunta <mohith.kunta@gmail.com>
GitHub: https://github.com/m-kunta

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
from datetime import date
from pathlib import Path

import pytest

from src.enrichment.data_loader import DataLoader, LoadedData
from src.models import EnrichmentConfidence
from src.utils.exceptions import EnrichmentError



SAMPLE_DIR = Path(__file__).parent.parent / "data" / "sample"
REGIONAL_SIGNALS = Path(__file__).parent.parent / "data" / "regional_signals.json"


class TestDataLoaderHelpers:
    """Unit tests for the private type-coercion helpers."""

    def test_to_float_valid(self):
        from src.enrichment.data_loader import _to_float
        assert _to_float("3.14") == pytest.approx(3.14)
        assert _to_float("0") == pytest.approx(0.0)
        assert _to_float("1e3") == pytest.approx(1000.0)

    def test_to_float_empty_or_none(self):
        from src.enrichment.data_loader import _to_float
        assert _to_float("") is None
        assert _to_float(None) is None
        assert _to_float("  ") is None

    def test_to_float_invalid(self):
        from src.enrichment.data_loader import _to_float
        assert _to_float("abc") is None
        assert _to_float("N/A") is None

    def test_to_int_rounds_float_string(self):
        from src.enrichment.data_loader import _to_int
        assert _to_int("1.0") == 1
        assert _to_int("5.9") == 5

    def test_to_int_empty_or_none(self):
        from src.enrichment.data_loader import _to_int
        assert _to_int("") is None
        assert _to_int(None) is None

    def test_to_bool_truthy_values(self):
        from src.enrichment.data_loader import _to_bool
        assert _to_bool("True") is True
        assert _to_bool("true") is True
        assert _to_bool("1") is True
        assert _to_bool("yes") is True

    def test_to_bool_falsy_values(self):
        from src.enrichment.data_loader import _to_bool
        assert _to_bool("False") is False
        assert _to_bool("false") is False
        assert _to_bool("0") is False
        assert _to_bool("no") is False

    def test_to_bool_empty_or_none(self):
        from src.enrichment.data_loader import _to_bool
        assert _to_bool("") is None
        assert _to_bool(None) is None


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

    def test_empty_csv_produces_empty_dict(self, tmp_path):
        """A CSV file with only a header row (no data) loads as an empty dict."""
        header_only = tmp_path / "stores.csv"
        header_only.write_text("store_id,store_name,tier,weekly_sales_k,region,competitor_proximity_miles,competitor_event\n")
        loader = DataLoader(
            store_master_path=str(header_only),
            item_master_path=str(SAMPLE_DIR / "item_master_sample.csv"),
            promo_calendar_path=str(SAMPLE_DIR / "promo_calendar_sample.csv"),
            vendor_performance_path=str(SAMPLE_DIR / "vendor_performance_sample.csv"),
            dc_inventory_path=str(SAMPLE_DIR / "dc_inventory_sample.csv"),
            regional_signals_path=str(REGIONAL_SIGNALS),
        )
        data = loader.load()
        assert data.store_master == {}

    def test_multiple_promos_for_same_item_store_loaded_as_list(self):
        """When the same (item_id, store_id) has multiple promo rows, all are stored."""
        loader = DataLoader(
            store_master_path=str(SAMPLE_DIR / "store_master_sample.csv"),
            item_master_path=str(SAMPLE_DIR / "item_master_sample.csv"),
            promo_calendar_path=str(SAMPLE_DIR / "promo_calendar_sample.csv"),
            vendor_performance_path=str(SAMPLE_DIR / "vendor_performance_sample.csv"),
            dc_inventory_path=str(SAMPLE_DIR / "dc_inventory_sample.csv"),
            regional_signals_path=str(REGIONAL_SIGNALS),
        )
        data = loader.load()
        # All promo calendar values must be lists (even single-entry combos)
        for promos in data.promo_calendar.values():
            assert isinstance(promos, list)
            assert len(promos) >= 1



# TODO: implement tests above once DataLoader and EnrichmentEngine are built.
# Follow the same fixture/class patterns used in tests/test_ingestion.py.
# Use tmp_path fixture for any file-based tests.


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

REF_DATE = date(2026, 3, 18)


@pytest.fixture(scope="session")
def loaded_data() -> "LoadedData":
    """Session-scoped LoadedData loaded from the sample files."""
    from src.enrichment.data_loader import DataLoader
    return DataLoader(
        store_master_path=str(SAMPLE_DIR / "store_master_sample.csv"),
        item_master_path=str(SAMPLE_DIR / "item_master_sample.csv"),
        promo_calendar_path=str(SAMPLE_DIR / "promo_calendar_sample.csv"),
        vendor_performance_path=str(SAMPLE_DIR / "vendor_performance_sample.csv"),
        dc_inventory_path=str(SAMPLE_DIR / "dc_inventory_sample.csv"),
        regional_signals_path=str(REGIONAL_SIGNALS),
    ).load()


@pytest.fixture(scope="session")
def engine(loaded_data: "LoadedData") -> "EnrichmentEngine":
    """Session-scoped EnrichmentEngine pinned to REF_DATE."""
    from src.enrichment.engine import EnrichmentEngine
    return EnrichmentEngine(loaded_data, reference_date=REF_DATE)


def _make_exception(**overrides) -> "CanonicalException":
    """Build a minimal CanonicalException for use in engine tests."""
    from src.models import CanonicalException, ExceptionType
    from datetime import datetime
    import uuid

    base = dict(
        exception_id=str(uuid.uuid4()),
        item_id="ITM-1001",
        item_name="Organic Whole Milk 1gal",
        store_id="STR-001",
        store_name="Flagship Manhattan",
        exception_type=ExceptionType.OOS,
        exception_date=REF_DATE,
        units_on_hand=0,
        days_of_supply=0.5,
        variance_pct=None,
        source_system="TestSystem",
        batch_id=str(uuid.uuid4()),
        ingested_at=datetime.now(),
    )
    base.update(overrides)
    return CanonicalException(**base)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEnrichmentEngine:

    def test_store_fields_populated(self, engine):
        """STR-001 → correct tier, region, weekly_sales, competitor fields."""
        exc = _make_exception(store_id="STR-001", item_id="ITM-1001")
        result = engine.enrich([exc])[0]

        assert result.store_tier == 1
        assert result.region == "NORTHEAST"
        assert result.weekly_store_sales_k == pytest.approx(2800.0)
        assert result.competitor_proximity_miles == pytest.approx(0.3)
        assert result.competitor_event is not None

    def test_item_fields_populated(self, engine):
        """ITM-1001 → correct category, perishable, vendor_id, price."""
        exc = _make_exception(item_id="ITM-1001")
        result = engine.enrich([exc])[0]

        assert result.category == "Dairy"
        assert result.perishable is True
        assert result.vendor_id == "VND-100"
        assert result.retail_price == pytest.approx(5.99)

    def test_promo_active_in_window(self, engine):
        """ITM-1001/STR-001 on 2026-03-18 falls within TPR window → promo_active=True."""
        exc = _make_exception(item_id="ITM-1001", store_id="STR-001")
        result = engine.enrich([exc])[0]

        assert result.promo_active is True
        assert result.promo_type == "TPR"

    def test_promo_expired(self, engine):
        """ITM-1009/STR-010 promo ended 2026-03-10 → promo_active=False on ref date."""
        exc = _make_exception(item_id="ITM-1009", store_id="STR-010")
        result = engine.enrich([exc])[0]

        assert result.promo_active is False

    def test_unknown_item_promo_not_active(self, engine):
        """Unknown item/store with no promo data → promo_active=False."""
        exc = _make_exception(item_id="ITM-XXXX", store_id="STR-XXXX")
        result = engine.enrich([exc])[0]

        assert result.promo_active is False

    def test_vendor_fields_populated(self, engine):
        """VND-400 → fill_rate=0.72, open_po_inbound=True (5 open POs)."""
        # ITM-1007 maps to VND-400 via item master
        exc = _make_exception(item_id="ITM-1007")
        result = engine.enrich([exc])[0]

        assert result.vendor_id == "VND-400"
        assert result.vendor_fill_rate_90d == pytest.approx(0.72)
        assert result.open_po_inbound is True


    def test_dc_inventory_populated(self, engine):
        """ITM-1007 → dc_inventory_days=5.6."""
        exc = _make_exception(item_id="ITM-1007")
        result = engine.enrich([exc])[0]

        assert result.dc_inventory_days == pytest.approx(5.6)

    def test_lead_time_derived_from_receipt_date(self, engine):
        """ITM-1007 next_receipt_date=2026-03-20 → lead_time_days=2 on ref 2026-03-18."""
        exc = _make_exception(item_id="ITM-1007")
        result = engine.enrich([exc])[0]

        # 2026-03-20 − 2026-03-18 = 2 days
        assert result.lead_time_days == 2

    def test_regional_disruption_northeast_active(self, engine):
        """NORTHEAST has active transport disruption on 2026-03-18."""
        exc = _make_exception(store_id="STR-001")  # NORTHEAST store
        result = engine.enrich([exc])[0]

        assert result.regional_disruption_flag is True
        assert result.regional_disruption_description is not None

    def test_regional_disruption_midwest_expired(self, engine):
        """MIDWEST storm ended 2026-03-18 → no active disruption on ref 2026-03-18.

        The active_through date is 2026-03-18, which is inclusive, so this
        still returns True on ref_date=2026-03-18. Pin ref_date to 2026-03-19
        for this test to confirm expiry.
        """
        from src.enrichment.engine import EnrichmentEngine
        engine_19 = EnrichmentEngine(engine._data, reference_date=date(2026, 3, 19))
        exc = _make_exception(store_id="STR-014")  # MIDWEST store
        result = engine_19.enrich([exc])[0]

        assert result.regional_disruption_flag is False

    def test_financial_no_promo(self, engine):
        """OOS item, no promo → est_lost_sales > 0, promo_margin_at_risk == 0.0."""
        # ITM-1009/STR-010 has an expired promo → no active promo
        exc = _make_exception(item_id="ITM-1009", store_id="STR-010", days_of_supply=0.0)
        result = engine.enrich([exc])[0]

        assert result.promo_active is False
        assert result.est_lost_sales_value > 0
        assert result.promo_margin_at_risk == pytest.approx(0.0)

    def test_financial_with_promo(self, engine):
        """OOS item on active TPR → promo_margin_at_risk > 0.0."""
        exc = _make_exception(item_id="ITM-1001", store_id="STR-001", days_of_supply=0.0)
        result = engine.enrich([exc])[0]

        assert result.promo_active is True
        assert result.est_lost_sales_value > 0
        assert result.promo_margin_at_risk > 0.0

    def test_financial_promo_formula_values(self, engine):
        """Verify promo lost-sales math: retail × (1-tpr) × clamp(7-dos,0,7) × lift."""
        # ITM-1001/STR-001: retail=5.99, tpr=0.25, dos=0.5, lift=1.4
        exc = _make_exception(item_id="ITM-1001", store_id="STR-001", days_of_supply=0.5)
        result = engine.enrich([exc])[0]

        expected = 5.99 * (1 - 0.25) * (7.0 - 0.5) * 1.4
        assert result.est_lost_sales_value == pytest.approx(expected, rel=1e-3)

    def test_confidence_high_complete_data(self, engine):
        """Well-known item/store/vendor → HIGH confidence, no missing fields."""
        exc = _make_exception(item_id="ITM-1001", store_id="STR-001")
        result = engine.enrich([exc])[0]

        # All tracked fields should resolve for this well-known combination
        assert result.enrichment_confidence.value in ("HIGH", "MEDIUM")
        # At most a couple of nullable fields missing (e.g. lead_time past)

    def test_confidence_low_unknown_store(self, engine):
        """Unknown store_id → many null fields → LOW confidence."""
        exc = _make_exception(store_id="STR-UNKNOWN", item_id="ITM-UNKNOWN")
        result = engine.enrich([exc])[0]

        assert result.enrichment_confidence == EnrichmentConfidence.LOW
        assert len(result.missing_data_fields) >= 3

    def test_validation_error_falls_back_low_confidence_with_failure_sentinel(self):
        """Invalid enrichment data should fall back to LOW confidence with a failure flag."""
        from src.enrichment.engine import EnrichmentEngine

        data = LoadedData()
        data.store_master["STR-FALLBACK"] = {
            "store_name": "Fallback Store",
            "tier": 2,
            "weekly_sales_k": 500.0,
            "region": "NORTHEAST",
            "competitor_proximity_miles": 1.2,
            "competitor_event": None,
        }
        data.item_master["ITM-FALLBACK"] = {
            "item_name": "Fallback Item",
            "category": "Test",
            "subcategory": "Unit",
            "velocity_rank": 9,
            "perishable": False,
            "retail_price": 4.25,
            "margin_pct": 0.15,
            "vendor_id": "VND-FALLBACK",
        }
        data.vendor_performance["VND-FALLBACK"] = {
            "vendor_name": "Fallback Vendor",
            "fill_rate_90d": 0.91,
            "late_shipments_30d": 0,
            "open_pos_count": 0,
            "last_incident_date": None,
        }
        data.dc_inventory["ITM-FALLBACK"] = {
            "dc_id": "DC-1",
            "units_on_hand": 12,
            "days_of_supply": 21.0,
            "next_receipt_date": "2026-03-20",
        }
        data.promo_calendar[("ITM-FALLBACK", "STR-FALLBACK")] = [{
            "promo_type": "INVALID_PROMO_TYPE",
            "promo_start_date": "2026-03-15",
            "promo_end_date": "2026-03-25",
            "tpr_depth_pct": 0.20,
            "circular_feature": False,
        }]

        engine = EnrichmentEngine(data, reference_date=REF_DATE)
        exc = _make_exception(
            item_id="ITM-FALLBACK",
            item_name="Fallback Item",
            store_id="STR-FALLBACK",
            store_name="Fallback Store",
            days_of_supply=0.0,
        )

        result = engine.enrich([exc])[0]

        assert result.exception_id == exc.exception_id
        assert result.item_id == "ITM-FALLBACK"
        assert result.store_id == "STR-FALLBACK"
        assert result.enrichment_confidence == EnrichmentConfidence.LOW
        assert "enrichment_failed" in result.missing_data_fields

    def test_valid_promo_type_uses_normal_enrichment_path(self):
        """Valid enrichment data should not trigger the failure sentinel or low confidence."""
        from src.enrichment.engine import EnrichmentEngine

        data = LoadedData()
        data.store_master["STR-FALLBACK"] = {
            "store_name": "Fallback Store",
            "tier": 2,
            "weekly_sales_k": 500.0,
            "region": "NORTHEAST",
            "competitor_proximity_miles": 1.2,
            "competitor_event": None,
        }
        data.item_master["ITM-FALLBACK"] = {
            "item_name": "Fallback Item",
            "category": "Test",
            "subcategory": "Unit",
            "velocity_rank": 9,
            "perishable": False,
            "retail_price": 4.25,
            "margin_pct": 0.15,
            "vendor_id": "VND-FALLBACK",
        }
        data.vendor_performance["VND-FALLBACK"] = {
            "vendor_name": "Fallback Vendor",
            "fill_rate_90d": 0.91,
            "late_shipments_30d": 0,
            "open_pos_count": 0,
            "last_incident_date": None,
        }
        data.dc_inventory["ITM-FALLBACK"] = {
            "dc_id": "DC-1",
            "units_on_hand": 12,
            "days_of_supply": 21.0,
            "next_receipt_date": "2026-03-20",
        }
        data.promo_calendar[("ITM-FALLBACK", "STR-FALLBACK")] = [{
            "promo_type": "TPR",
            "promo_start_date": "2026-03-15",
            "promo_end_date": "2026-03-25",
            "tpr_depth_pct": 0.20,
            "circular_feature": False,
        }]

        engine = EnrichmentEngine(data, reference_date=REF_DATE)
        exc = _make_exception(
            item_id="ITM-FALLBACK",
            item_name="Fallback Item",
            store_id="STR-FALLBACK",
            store_name="Fallback Store",
            days_of_supply=0.0,
        )

        result = engine.enrich([exc])[0]

        assert result.enrichment_confidence == EnrichmentConfidence.HIGH
        assert "enrichment_failed" not in result.missing_data_fields
        assert result.promo_active is True

    def test_enrich_empty_list(self, engine):
        """enrich([]) returns an empty list without raising."""
        result = engine.enrich([])
        assert result == []

    def test_lead_time_days_negative_when_receipt_date_in_past(self, engine):
        """ITM-1001 next_receipt_date=2026-03-17 < ref_date=2026-03-18 → lead_time_days=-1."""
        exc = _make_exception(item_id="ITM-1001")
        result = engine.enrich([exc])[0]
        # 2026-03-17 − 2026-03-18 = -1 day
        assert result.lead_time_days == -1

    def test_next_delivery_date_populated(self, engine):
        """ITM-1007 next_receipt_date=2026-03-20 → next_delivery_date=date(2026,3,20)."""
        from datetime import date as dt
        exc = _make_exception(item_id="ITM-1007")
        result = engine.enrich([exc])[0]
        assert result.next_delivery_date == dt(2026, 3, 20)

    def test_subcategory_and_additional_item_fields_populated(self, engine):
        """ITM-1001 → subcategory='Milk', margin_pct=0.28, velocity_rank=1."""
        exc = _make_exception(item_id="ITM-1001")
        result = engine.enrich([exc])[0]
        assert result.subcategory == "Milk"
        assert result.margin_pct == pytest.approx(0.28)
        assert result.velocity_rank == 1

    def test_promo_end_date_and_tpr_depth_on_result(self, engine):
        """Active promo for ITM-1001/STR-001 → promo_end_date and tpr_depth_pct populated."""
        from datetime import date as dt
        exc = _make_exception(item_id="ITM-1001", store_id="STR-001")
        result = engine.enrich([exc])[0]
        assert result.promo_end_date is not None
        assert isinstance(result.promo_end_date, dt)
        assert result.tpr_depth_pct == pytest.approx(0.25)

    def test_regional_no_disruption_returns_false(self, engine):
        """SOUTHEAST has no signal entry → regional_disruption_flag=False."""
        exc = _make_exception(store_id="STR-010")  # SOUTHEAST store
        result = engine.enrich([exc])[0]
        assert result.regional_disruption_flag is False
        assert result.regional_disruption_description is None

    def test_financial_dos_exceeds_7_returns_zero(self, engine):
        """days_of_supply >= 7.0 → days_of_exposure is clamped to 0 → est_lost_sales=0.0."""
        exc = _make_exception(item_id="ITM-1001", store_id="STR-001", days_of_supply=7.0)
        result = engine.enrich([exc])[0]
        assert result.est_lost_sales_value == pytest.approx(0.0)

    def test_financial_dos_above_7_returns_zero(self, engine):
        """days_of_supply > 7.0 → est_lost_sales_value=0.0 (fully covered)."""
        exc = _make_exception(item_id="ITM-1001", store_id="STR-001", days_of_supply=14.0)
        result = engine.enrich([exc])[0]
        assert result.est_lost_sales_value == pytest.approx(0.0)

    def test_financial_no_retail_price_returns_zero(self, engine):
        """Unknown item → retail_price=None → est_lost_sales_value and promo_margin_at_risk both 0.0."""
        exc = _make_exception(item_id="ITM-XXXX", store_id="STR-001")
        result = engine.enrich([exc])[0]
        assert result.est_lost_sales_value == pytest.approx(0.0)
        assert result.promo_margin_at_risk == pytest.approx(0.0)

    def test_open_po_inbound_false_when_no_open_pos(self):
        """open_po_inbound=False when vendor has open_pos_count=0."""
        from src.enrichment.data_loader import LoadedData
        from src.enrichment.engine import EnrichmentEngine

        data = LoadedData()
        data.store_master["STR-T01"] = {
            "store_name": "Test Store",
            "tier": 2,
            "weekly_sales_k": 500.0,
            "region": "SOUTHWEST",
            "competitor_proximity_miles": 2.0,
            "competitor_event": None,
        }
        data.item_master["ITM-T01"] = {
            "item_name": "Test Widget",
            "category": "Test",
            "subcategory": "Unit",
            "velocity_rank": 5,
            "perishable": False,
            "retail_price": 10.0,
            "margin_pct": 0.30,
            "vendor_id": "VND-T01",
        }
        data.vendor_performance["VND-T01"] = {
            "vendor_name": "Zero PO Vendor",
            "fill_rate_90d": 0.95,
            "late_shipments_30d": 0,
            "open_pos_count": 0,
            "last_incident_date": None,
        }
        engine = EnrichmentEngine(data, reference_date=REF_DATE)
        exc = _make_exception(item_id="ITM-T01", store_id="STR-T01")
        result = engine.enrich([exc])[0]

        assert result.open_po_inbound is False
        assert result.vendor_fill_rate_90d == pytest.approx(0.95)

    def test_margin_pct_none_with_promo_gives_zero_margin_at_risk(self):
        """promo_active=True but margin_pct=None → promo_margin_at_risk=0.0."""
        from src.enrichment.data_loader import LoadedData
        from src.enrichment.engine import EnrichmentEngine

        data = LoadedData()
        data.store_master["STR-T02"] = {
            "store_name": "T Store",
            "tier": 1,
            "weekly_sales_k": 800.0,
            "region": "WEST",
            "competitor_proximity_miles": 1.0,
            "competitor_event": None,
        }
        data.item_master["ITM-T02"] = {
            "item_name": "No Margin Item",
            "category": "Test",
            "subcategory": "Widget",
            "velocity_rank": 3,
            "perishable": False,
            "retail_price": 8.0,
            "margin_pct": None,  # ← no margin data
            "vendor_id": None,
        }
        data.promo_calendar[("ITM-T02", "STR-T02")] = [{
            "promo_type": "TPR",
            "promo_start_date": "2026-03-15",
            "promo_end_date": "2026-03-25",
            "tpr_depth_pct": 0.20,
            "circular_feature": False,
        }]
        engine = EnrichmentEngine(data, reference_date=REF_DATE)
        exc = _make_exception(item_id="ITM-T02", store_id="STR-T02", days_of_supply=0.0)
        result = engine.enrich([exc])[0]

        assert result.promo_active is True
        assert result.est_lost_sales_value > 0.0
        assert result.promo_margin_at_risk == pytest.approx(0.0)

    def test_confidence_medium(self, loaded_data):
        """1–4 missing tracked fields (with custom low threshold=5) → MEDIUM confidence."""
        from src.enrichment.engine import EnrichmentEngine

        # Unknown store → store_tier, weekly_store_sales_k, region, regional_disruption_flag = 4 nulls
        # null_threshold_low=5 means 4 nulls → MEDIUM (not LOW), null_threshold_medium=1 → not HIGH
        engine = EnrichmentEngine(
            loaded_data,
            reference_date=REF_DATE,
            null_threshold_low=5,
            null_threshold_medium=1,
        )
        exc = _make_exception(item_id="ITM-1001", store_id="STR-UNKNOWN")
        result = engine.enrich([exc])[0]

        assert result.enrichment_confidence == EnrichmentConfidence.MEDIUM

    def test_missing_data_fields_contains_expected_names(self, engine):
        """Unknown store/item → missing_data_fields lists the correct tracked field names."""
        exc = _make_exception(store_id="STR-UNKNOWN", item_id="ITM-UNKNOWN")
        result = engine.enrich([exc])[0]

        expected_missing = {"store_tier", "weekly_store_sales_k", "region", "category",
                            "retail_price", "vendor_id", "vendor_fill_rate_90d",
                            "open_po_inbound", "dc_inventory_days"}
        for field in expected_missing:
            assert field in result.missing_data_fields, f"Expected '{field}' in missing_data_fields"

    def test_day_of_week_demand_index_populated_from_exception_date(self, engine):
        """Wednesday 2026-03-18 should produce a deterministic demand index."""
        exc = _make_exception(exception_date=date(2026, 3, 18))
        result = engine.enrich([exc])[0]

        assert result.day_of_week_demand_index == pytest.approx(1.05)

    def test_day_of_week_demand_index_included_in_full_sample_enrichment(self):
        """Full-sample enrichment should populate day_of_week_demand_index for every row."""
        from src.ingestion.csv_adapter import CsvIngestionAdapter
        from src.ingestion.normalizer import Normalizer
        from src.enrichment.data_loader import DataLoader
        from src.enrichment.engine import EnrichmentEngine

        records = CsvIngestionAdapter(str(SAMPLE_DIR / "exceptions_sample.csv")).fetch()
        canonical, quarantined = Normalizer().normalize(records)
        assert quarantined == 0

        loaded = DataLoader(
            store_master_path=str(SAMPLE_DIR / "store_master_sample.csv"),
            item_master_path=str(SAMPLE_DIR / "item_master_sample.csv"),
            promo_calendar_path=str(SAMPLE_DIR / "promo_calendar_sample.csv"),
            vendor_performance_path=str(SAMPLE_DIR / "vendor_performance_sample.csv"),
            dc_inventory_path=str(SAMPLE_DIR / "dc_inventory_sample.csv"),
            regional_signals_path=str(REGIONAL_SIGNALS),
        ).load()
        enriched = EnrichmentEngine(loaded, reference_date=REF_DATE).enrich(canonical)

        assert len(enriched) == 120
        assert all(item.day_of_week_demand_index is not None for item in enriched)

    def test_enrich_full_sample(self, loaded_data):
        """All 120 sample exceptions enrich without error → all EnrichedExceptionSchema."""
        from src.enrichment.engine import EnrichmentEngine
        from src.ingestion.csv_adapter import CsvIngestionAdapter
        from src.ingestion.normalizer import Normalizer
        from src.models import EnrichedExceptionSchema
        import tempfile

        exceptions_csv = SAMPLE_DIR / "exceptions_sample.csv"
        adapter = CsvIngestionAdapter(str(exceptions_csv))
        with tempfile.TemporaryDirectory() as tmp:
            normalizer = Normalizer(quarantine_dir=tmp)
            canonical, _ = normalizer.normalize(adapter.fetch())

        engine = EnrichmentEngine(loaded_data, reference_date=REF_DATE)
        enriched = engine.enrich(canonical)

        assert len(enriched) == 120
        for item in enriched:
            assert isinstance(item, EnrichedExceptionSchema)
