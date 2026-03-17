"""Normalizer for converting raw ingestion records to canonical exception schema.

Handles field mapping, type coercion, deduplication, quarantine of invalid
records, and batch ID assignment.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from loguru import logger

from src.models import CanonicalException, ExceptionType
from src.utils.exceptions import IngestionError


# Fields required for a record to be valid (not quarantined)
REQUIRED_FIELDS = {"item_id", "store_id", "exception_type", "exception_date"}

# Dedup key: same item+store+type+date = duplicate
DEDUP_KEY_FIELDS = ("item_id", "store_id", "exception_type", "exception_date")


class Normalizer:
    """Converts raw adapter output to validated CanonicalException objects.

    Args:
        field_mapping: Dict mapping canonical field names to source field names.
            If empty, assumes source fields match canonical names.
        quarantine_dir: Directory to write quarantined records. Defaults to output/logs.
    """

    def __init__(
        self,
        field_mapping: Optional[Dict[str, str]] = None,
        quarantine_dir: str = "output/logs",
    ) -> None:
        self.field_mapping = field_mapping or {}
        self.quarantine_dir = Path(quarantine_dir)
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)

    def normalize(
        self, raw_records: List[Dict[str, Any]]
    ) -> Tuple[List[CanonicalException], int]:
        """Normalize a batch of raw records into canonical exceptions.

        Args:
            raw_records: List of raw dicts from an ingestion adapter.

        Returns:
            Tuple of (valid CanonicalException list, quarantined record count).
        """
        batch_id = str(uuid4())
        ingested_at = datetime.utcnow()
        logger.info(f"Normalizing batch {batch_id}: {len(raw_records)} raw records")

        mapped_records = [self._apply_field_mapping(r) for r in raw_records]

        valid_records: List[CanonicalException] = []
        quarantined: List[Dict[str, Any]] = []
        seen_keys: set = set()
        duplicates = 0

        for i, record in enumerate(mapped_records):
            # Check required fields
            missing = self._check_required_fields(record)
            if missing:
                quarantined.append({
                    "row_index": i,
                    "record": record,
                    "reason": f"missing_required_fields: {', '.join(sorted(missing))}",
                })
                continue

            # Deduplication
            dedup_key = tuple(str(record.get(f, "")).strip() for f in DEDUP_KEY_FIELDS)
            if dedup_key in seen_keys:
                logger.debug(f"Duplicate at row {i}: {dedup_key}")
                duplicates += 1
                continue
            seen_keys.add(dedup_key)

            # Type coercion and validation
            try:
                canonical = self._coerce_and_validate(record, batch_id, ingested_at)
                valid_records.append(canonical)
            except (ValueError, KeyError) as e:
                quarantined.append({
                    "row_index": i,
                    "record": record,
                    "reason": f"coercion_error: {e}",
                })

        # Write quarantined records
        if quarantined:
            self._write_quarantine(quarantined, batch_id)

        logger.info(
            f"Normalization complete: {len(valid_records)} valid, "
            f"{len(quarantined)} quarantined, {duplicates} duplicates removed"
        )
        return valid_records, len(quarantined)

    def _apply_field_mapping(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Map source field names to canonical field names."""
        if not self.field_mapping:
            return record

        mapped = {}
        for canonical_name, source_name in self.field_mapping.items():
            if source_name in record:
                mapped[canonical_name] = record[source_name]
        # Also keep any fields not in the mapping (pass-through)
        mapped_source_names = set(self.field_mapping.values())
        for key, value in record.items():
            if key not in mapped_source_names and key not in mapped:
                mapped[key] = value
        return mapped

    def _check_required_fields(self, record: Dict[str, Any]) -> set:
        """Return set of missing required fields."""
        missing = set()
        for field in REQUIRED_FIELDS:
            value = record.get(field)
            if value is None or (isinstance(value, str) and value.strip() == ""):
                missing.add(field)
        return missing

    def _coerce_and_validate(
        self,
        record: Dict[str, Any],
        batch_id: str,
        ingested_at: datetime,
    ) -> CanonicalException:
        """Coerce types and create a validated CanonicalException."""
        # Generate exception_id if not present
        exception_id = record.get("exception_id")
        if not exception_id or (isinstance(exception_id, str) and exception_id.strip() == ""):
            exception_id = str(uuid4())

        # Parse exception_date
        exception_date = self._parse_date(record["exception_date"])

        # Coerce numeric fields
        units_on_hand = int(record["units_on_hand"])
        days_of_supply = float(record["days_of_supply"])

        # Optional variance_pct
        variance_raw = record.get("variance_pct")
        variance_pct = None
        if variance_raw is not None and str(variance_raw).strip() not in ("", "None", "null"):
            variance_pct = float(variance_raw)

        # Validate exception_type
        exc_type_raw = str(record["exception_type"]).strip().upper()
        try:
            exception_type = ExceptionType(exc_type_raw)
        except ValueError:
            raise ValueError(
                f"Invalid exception_type '{exc_type_raw}'. "
                f"Must be one of: {[e.value for e in ExceptionType]}"
            )

        return CanonicalException(
            exception_id=str(exception_id).strip(),
            item_id=str(record["item_id"]).strip(),
            item_name=str(record.get("item_name", "")).strip(),
            store_id=str(record["store_id"]).strip(),
            store_name=str(record.get("store_name", "")).strip(),
            exception_type=exception_type,
            exception_date=exception_date,
            units_on_hand=units_on_hand,
            days_of_supply=days_of_supply,
            variance_pct=variance_pct,
            source_system=str(record.get("source_system", "unknown")).strip(),
            batch_id=batch_id,
            ingested_at=ingested_at,
        )

    def _parse_date(self, value: Any) -> date:
        """Parse a date from string or date object."""
        if isinstance(value, date):
            return value
        date_str = str(value).strip()
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        raise ValueError(f"Cannot parse date: '{date_str}'")

    def _write_quarantine(
        self, quarantined: List[Dict[str, Any]], batch_id: str
    ) -> None:
        """Write quarantined records to a JSON file."""
        today = date.today().isoformat()
        quarantine_path = self.quarantine_dir / f"quarantine_{today}_{batch_id[:8]}.json"

        # Convert non-serializable values to strings
        serializable = []
        for q in quarantined:
            entry = {
                "row_index": q["row_index"],
                "reason": q["reason"],
                "record": {k: str(v) for k, v in q["record"].items()},
            }
            serializable.append(entry)

        with open(quarantine_path, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2)
        logger.warning(
            f"Quarantined {len(quarantined)} records to {quarantine_path}"
        )
