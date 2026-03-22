"""Tests for src/utils/validators.py.

Covers validate_canonical_exception, validate_enriched_exception,
validate_canonical_batch, and load_json_schema.

Author: Mohith Kunta <mohith.kunta@gmail.com>
GitHub: https://github.com/m-kunta
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from src.utils.validators import (
    load_json_schema,
    validate_canonical_batch,
    validate_canonical_exception,
    validate_enriched_exception,
)
from src.utils.exceptions import IngestionError, EnrichmentError
from src.models import CanonicalException, EnrichedExceptionSchema, ExceptionType


SCHEMA_DIR = Path(__file__).parent.parent / "data" / "schema"

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _canonical_dict(**overrides) -> dict:
    base = dict(
        exception_id="EXC-001",
        item_id="ITM-1001",
        item_name="Organic Whole Milk 1gal",
        store_id="STR-001",
        store_name="Flagship Manhattan",
        exception_type="OOS",
        exception_date=date(2026, 3, 18),
        units_on_hand=0,
        days_of_supply=0.5,
        variance_pct=None,
        source_system="TestSystem",
        batch_id="aaaaaaaa-0000-0000-0000-000000000000",
        ingested_at=datetime(2026, 3, 18, 10, 0, 0),
    )
    base.update(overrides)
    return base


def _enriched_dict(**overrides) -> dict:
    base = _canonical_dict()
    base.update(dict(
        store_tier=1,
        region="NORTHEAST",
        weekly_store_sales_k=2800.0,
        category="Dairy",
        perishable=True,
        vendor_id="VND-100",
        retail_price=5.99,
        promo_active=True,
        promo_type="TPR",
        enrichment_confidence="HIGH",
        missing_data_fields=[],
    ))
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Tests: validate_canonical_exception
# ---------------------------------------------------------------------------


class TestValidateCanonicalException:
    def test_valid_record_returns_canonical_exception(self):
        result = validate_canonical_exception(_canonical_dict())
        assert isinstance(result, CanonicalException)
        assert result.item_id == "ITM-1001"
        assert result.exception_type == ExceptionType.OOS

    def test_invalid_exception_type_raises_ingestion_error(self):
        with pytest.raises(IngestionError, match="validation failed"):
            validate_canonical_exception(_canonical_dict(exception_type="BOGUS"))

    def test_missing_required_field_raises_ingestion_error(self):
        data = _canonical_dict()
        del data["item_id"]
        with pytest.raises(IngestionError, match="validation failed"):
            validate_canonical_exception(data)

    def test_wrong_type_for_units_on_hand_raises_ingestion_error(self):
        with pytest.raises(IngestionError, match="validation failed"):
            validate_canonical_exception(_canonical_dict(units_on_hand="not-a-number"))

    def test_null_variance_pct_is_accepted(self):
        result = validate_canonical_exception(_canonical_dict(variance_pct=None))
        assert result.variance_pct is None

    def test_float_variance_pct_is_accepted(self):
        result = validate_canonical_exception(_canonical_dict(variance_pct=12.5))
        assert result.variance_pct == pytest.approx(12.5)


# ---------------------------------------------------------------------------
# Tests: validate_enriched_exception
# ---------------------------------------------------------------------------


class TestValidateEnrichedException:
    def test_valid_record_returns_enriched_schema(self):
        result = validate_enriched_exception(_enriched_dict())
        assert isinstance(result, EnrichedExceptionSchema)
        assert result.store_tier == 1
        assert result.region == "NORTHEAST"

    def test_invalid_exception_type_raises_enrichment_error(self):
        with pytest.raises(EnrichmentError, match="validation failed"):
            validate_enriched_exception(_enriched_dict(exception_type="BOGUS"))

    def test_missing_required_field_raises_enrichment_error(self):
        data = _enriched_dict()
        del data["store_id"]
        with pytest.raises(EnrichmentError, match="validation failed"):
            validate_enriched_exception(data)

    def test_all_optional_enrichment_fields_can_be_none(self):
        """Every optional enrichment field set to None should still validate."""
        data = _enriched_dict(
            store_tier=None,
            region=None,
            weekly_store_sales_k=None,
            category=None,
            perishable=None,
            vendor_id=None,
            retail_price=None,
            promo_active=None,
            promo_type=None,
        )
        result = validate_enriched_exception(data)
        assert result.store_tier is None
        assert result.region is None


# ---------------------------------------------------------------------------
# Tests: validate_canonical_batch
# ---------------------------------------------------------------------------


class TestValidateCanonicalBatch:
    def test_all_valid_records(self):
        records = [_canonical_dict(), _canonical_dict(exception_id="EXC-002", item_id="ITM-1002")]
        valid, invalid = validate_canonical_batch(records)
        assert len(valid) == 2
        assert len(invalid) == 0

    def test_mixed_valid_and_invalid_records(self):
        records = [
            _canonical_dict(),                              # valid
            _canonical_dict(exception_type="BAD_TYPE"),     # invalid
            _canonical_dict(exception_id="EXC-003"),        # valid
        ]
        valid, invalid = validate_canonical_batch(records)
        assert len(valid) == 2
        assert len(invalid) == 1

    def test_invalid_record_includes_row_index_and_errors(self):
        bad = _canonical_dict(exception_type="BAD_TYPE")
        _, invalid = validate_canonical_batch([bad])
        assert invalid[0]["row_index"] == 0
        assert "errors" in invalid[0]
        assert len(invalid[0]["errors"]) > 0

    def test_empty_batch_returns_empty_lists(self):
        valid, invalid = validate_canonical_batch([])
        assert valid == []
        assert invalid == []

    def test_all_invalid_records(self):
        records = [
            _canonical_dict(units_on_hand="not-an-int"),
            _canonical_dict(exception_type="JUNK"),
        ]
        valid, invalid = validate_canonical_batch(records)
        assert len(valid) == 0
        assert len(invalid) == 2


# ---------------------------------------------------------------------------
# Tests: load_json_schema
# ---------------------------------------------------------------------------


class TestLoadJsonSchema:
    def test_loads_canonical_exception_schema(self):
        schema = load_json_schema("canonical_exception_schema.json")
        assert isinstance(schema, dict)
        assert schema.get("title") == "CanonicalException"
        assert "required" in schema
        assert "properties" in schema

    def test_schema_has_expected_required_fields(self):
        schema = load_json_schema("canonical_exception_schema.json")
        required = schema["required"]
        for field in ("exception_id", "item_id", "store_id", "exception_type",
                      "exception_date", "batch_id", "ingested_at"):
            assert field in required

    def test_missing_schema_file_raises_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_json_schema("nonexistent_schema.json")
