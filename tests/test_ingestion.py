"""Tests for the ingestion layer: CSV adapter, normalizer, and end-to-end pipeline."""

from __future__ import annotations

import csv
import json
import os
import tempfile
from datetime import date
from pathlib import Path

import pytest

from src.ingestion.base_adapter import BaseIngestionAdapter
from src.ingestion.csv_adapter import CsvIngestionAdapter
from src.ingestion.normalizer import Normalizer
from src.models import CanonicalException, ExceptionType
from src.utils.exceptions import IngestionError


SAMPLE_DIR = Path(__file__).parent.parent / "data" / "sample"
EXCEPTIONS_CSV = SAMPLE_DIR / "exceptions_sample.csv"


# --- Base Adapter Tests ---


class TestBaseAdapter:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            BaseIngestionAdapter()

    def test_subclass_must_implement_fetch(self):
        class Incomplete(BaseIngestionAdapter):
            def validate_connection(self) -> bool:
                return True

        with pytest.raises(TypeError):
            Incomplete()


# --- CSV Adapter Tests ---


class TestCsvAdapter:
    def test_reads_sample_csv(self):
        adapter = CsvIngestionAdapter(str(EXCEPTIONS_CSV))
        records = adapter.fetch()
        assert len(records) == 120

    def test_returns_dicts_with_expected_fields(self):
        adapter = CsvIngestionAdapter(str(EXCEPTIONS_CSV))
        records = adapter.fetch()
        expected_fields = {
            "exception_id", "item_id", "item_name", "store_id", "store_name",
            "exception_type", "exception_date", "units_on_hand",
            "days_of_supply", "variance_pct", "source_system",
        }
        assert set(records[0].keys()) == expected_fields

    def test_all_values_are_strings(self):
        adapter = CsvIngestionAdapter(str(EXCEPTIONS_CSV))
        records = adapter.fetch()
        for record in records[:5]:
            for value in record.values():
                assert isinstance(value, str)

    def test_file_not_found_raises_ingestion_error(self):
        adapter = CsvIngestionAdapter("/nonexistent/path.csv")
        with pytest.raises(IngestionError, match="not accessible"):
            adapter.fetch()

    def test_validate_connection_returns_false_for_missing_file(self):
        adapter = CsvIngestionAdapter("/nonexistent/path.csv")
        assert adapter.validate_connection() is False

    def test_validate_connection_returns_true_for_existing_file(self):
        adapter = CsvIngestionAdapter(str(EXCEPTIONS_CSV))
        assert adapter.validate_connection() is True

    def test_handles_utf8_bom(self):
        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".csv", delete=False
        ) as f:
            # Write UTF-8 BOM + CSV content
            f.write(b"\xef\xbb\xbf")
            f.write(b"item_id,store_id\n")
            f.write(b"ITM-001,STR-001\n")
            tmp_path = f.name

        try:
            adapter = CsvIngestionAdapter(tmp_path)
            records = adapter.fetch()
            assert len(records) == 1
            assert "item_id" in records[0]
        finally:
            os.unlink(tmp_path)

    def test_skips_empty_rows(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write("item_id,store_id\n")
            f.write("ITM-001,STR-001\n")
            f.write(",\n")  # empty row
            f.write("ITM-002,STR-002\n")
            tmp_path = f.name

        try:
            adapter = CsvIngestionAdapter(tmp_path)
            records = adapter.fetch()
            assert len(records) == 2
        finally:
            os.unlink(tmp_path)

    def test_custom_delimiter(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write("item_id\tstore_id\n")
            f.write("ITM-001\tSTR-001\n")
            tmp_path = f.name

        try:
            adapter = CsvIngestionAdapter(tmp_path, delimiter="\t")
            records = adapter.fetch()
            assert len(records) == 1
            assert records[0]["item_id"] == "ITM-001"
        finally:
            os.unlink(tmp_path)


# --- Normalizer Tests ---


class TestNormalizer:
    def _make_raw_record(self, **overrides) -> dict:
        base = {
            "exception_id": "EXC-001",
            "item_id": "ITM-1001",
            "item_name": "Test Item",
            "store_id": "STR-001",
            "store_name": "Test Store",
            "exception_type": "OOS",
            "exception_date": "2026-03-16",
            "units_on_hand": "0",
            "days_of_supply": "0.5",
            "variance_pct": "5.2",
            "source_system": "TestSystem",
        }
        base.update(overrides)
        return base

    def test_normalizes_single_valid_record(self, tmp_path):
        normalizer = Normalizer(quarantine_dir=str(tmp_path))
        records = [self._make_raw_record()]
        valid, quarantined = normalizer.normalize(records)
        assert len(valid) == 1
        assert quarantined == 0
        assert isinstance(valid[0], CanonicalException)

    def test_assigns_batch_id(self, tmp_path):
        normalizer = Normalizer(quarantine_dir=str(tmp_path))
        records = [self._make_raw_record(), self._make_raw_record(item_id="ITM-1002")]
        valid, _ = normalizer.normalize(records)
        # All records in a batch share the same batch_id
        assert valid[0].batch_id == valid[1].batch_id
        assert len(valid[0].batch_id) == 36  # UUID format

    def test_generates_exception_id_when_missing(self, tmp_path):
        normalizer = Normalizer(quarantine_dir=str(tmp_path))
        records = [self._make_raw_record(exception_id="")]
        valid, _ = normalizer.normalize(records)
        assert len(valid[0].exception_id) == 36

    def test_type_coercion(self, tmp_path):
        normalizer = Normalizer(quarantine_dir=str(tmp_path))
        records = [self._make_raw_record()]
        valid, _ = normalizer.normalize(records)
        exc = valid[0]
        assert isinstance(exc.units_on_hand, int)
        assert isinstance(exc.days_of_supply, float)
        assert isinstance(exc.exception_date, date)
        assert isinstance(exc.variance_pct, float)
        assert exc.exception_type == ExceptionType.OOS

    def test_null_variance_pct(self, tmp_path):
        normalizer = Normalizer(quarantine_dir=str(tmp_path))
        records = [self._make_raw_record(variance_pct="")]
        valid, _ = normalizer.normalize(records)
        assert valid[0].variance_pct is None

    def test_deduplication(self, tmp_path):
        normalizer = Normalizer(quarantine_dir=str(tmp_path))
        records = [
            self._make_raw_record(),
            self._make_raw_record(),  # exact duplicate
        ]
        valid, quarantined = normalizer.normalize(records)
        assert len(valid) == 1
        assert quarantined == 0  # duplicates are not quarantined, just removed

    def test_different_types_not_deduplicated(self, tmp_path):
        normalizer = Normalizer(quarantine_dir=str(tmp_path))
        records = [
            self._make_raw_record(exception_type="OOS"),
            self._make_raw_record(exception_type="LOW_STOCK"),
        ]
        valid, _ = normalizer.normalize(records)
        assert len(valid) == 2

    def test_quarantines_missing_required_fields(self, tmp_path):
        normalizer = Normalizer(quarantine_dir=str(tmp_path))
        records = [
            self._make_raw_record(item_id=""),    # missing item_id
            self._make_raw_record(store_id=""),    # missing store_id
            self._make_raw_record(),               # valid
        ]
        valid, quarantined = normalizer.normalize(records)
        assert len(valid) == 1
        assert quarantined == 2

    def test_quarantine_file_written(self, tmp_path):
        normalizer = Normalizer(quarantine_dir=str(tmp_path))
        records = [self._make_raw_record(item_id="")]
        normalizer.normalize(records)
        quarantine_files = list(tmp_path.glob("quarantine_*.json"))
        assert len(quarantine_files) == 1
        with open(quarantine_files[0]) as f:
            data = json.load(f)
        assert len(data) == 1
        assert "missing_required_fields" in data[0]["reason"]

    def test_invalid_exception_type_quarantined(self, tmp_path):
        normalizer = Normalizer(quarantine_dir=str(tmp_path))
        records = [self._make_raw_record(exception_type="INVALID_TYPE")]
        valid, quarantined = normalizer.normalize(records)
        assert len(valid) == 0
        assert quarantined == 1

    def test_field_mapping(self, tmp_path):
        mapping = {
            "item_id": "sku_code",
            "store_id": "location_id",
            "exception_type": "alert_type",
            "exception_date": "alert_date",
        }
        normalizer = Normalizer(field_mapping=mapping, quarantine_dir=str(tmp_path))
        record = {
            "exception_id": "EXC-100",
            "sku_code": "ITM-1001",
            "item_name": "Test Item",
            "location_id": "STR-001",
            "store_name": "Test Store",
            "alert_type": "OOS",
            "alert_date": "2026-03-16",
            "units_on_hand": "0",
            "days_of_supply": "0.5",
            "variance_pct": "5.2",
            "source_system": "External",
        }
        valid, _ = normalizer.normalize([record])
        assert len(valid) == 1
        assert valid[0].item_id == "ITM-1001"
        assert valid[0].store_id == "STR-001"

    def test_date_format_mm_dd_yyyy(self, tmp_path):
        normalizer = Normalizer(quarantine_dir=str(tmp_path))
        records = [self._make_raw_record(exception_date="03/16/2026")]
        valid, _ = normalizer.normalize(records)
        assert valid[0].exception_date == date(2026, 3, 16)


# --- End-to-End Integration Test ---


class TestIngestionPipeline:
    def test_csv_to_canonical_full_pipeline(self, tmp_path):
        """End-to-end: CSV adapter → normalizer → 120 valid CanonicalException objects."""
        adapter = CsvIngestionAdapter(str(EXCEPTIONS_CSV))
        raw_records = adapter.fetch()
        assert len(raw_records) == 120

        normalizer = Normalizer(quarantine_dir=str(tmp_path))
        valid, quarantined = normalizer.normalize(raw_records)

        assert len(valid) == 120
        assert quarantined == 0

        # Verify all are CanonicalException instances
        for exc in valid:
            assert isinstance(exc, CanonicalException)
            assert exc.batch_id  # has a batch_id
            assert exc.ingested_at  # has a timestamp

        # Verify exception type distribution
        type_counts = {}
        for exc in valid:
            type_counts[exc.exception_type] = type_counts.get(exc.exception_type, 0) + 1
        assert ExceptionType.OOS in type_counts
        assert ExceptionType.LOW_STOCK in type_counts

    def test_pipeline_with_malformed_row(self, tmp_path):
        """Verify a malformed row is quarantined, not passed downstream."""
        # Create a CSV with one good and one bad row
        csv_path = tmp_path / "test_exceptions.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "exception_id", "item_id", "item_name", "store_id", "store_name",
                "exception_type", "exception_date", "units_on_hand",
                "days_of_supply", "variance_pct", "source_system",
            ])
            # Good row
            writer.writerow([
                "EXC-001", "ITM-1001", "Test Item", "STR-001", "Test Store",
                "OOS", "2026-03-16", "0", "0.5", "5.2", "TestSystem",
            ])
            # Bad row: missing item_id and store_id
            writer.writerow([
                "EXC-002", "", "Bad Item", "", "No Store",
                "OOS", "2026-03-16", "0", "0.0", "", "TestSystem",
            ])

        adapter = CsvIngestionAdapter(str(csv_path))
        raw = adapter.fetch()
        assert len(raw) == 2

        normalizer = Normalizer(quarantine_dir=str(tmp_path))
        valid, quarantined = normalizer.normalize(raw)
        assert len(valid) == 1
        assert quarantined == 1
        assert valid[0].exception_id == "EXC-001"
