"""DataLoader for Layer 2: loads and indexes all 6 reference datasets at startup.

Each dataset is read once and stored as an in-memory lookup dict keyed for O(1)
access during per-exception enrichment in EnrichmentEngine.

Reference data sources (configured in config/config.yaml under `enrichment:`):
    - store_master:       keyed by store_id
    - item_master:        keyed by item_id
    - promo_calendar:     keyed by (item_id, store_id) → list of promo rows
    - vendor_performance: keyed by vendor_id
    - dc_inventory:       keyed by item_id
    - regional_signals:   keyed by region → list of disruption dicts

Usage:
    loader = DataLoader()
    data = loader.load()
    engine = EnrichmentEngine(data)

Author: Mohith Kunta <mohith.kunta@gmail.com>
GitHub: https://github.com/m-kunta
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

from loguru import logger

from src.utils.config_loader import EnrichmentConfig, load_config
from src.utils.exceptions import EnrichmentError


# ---------------------------------------------------------------------------
# LoadedData — container for all 6 indexed reference datasets
# ---------------------------------------------------------------------------


@dataclass
class LoadedData:
    """In-memory lookup tables for all 6 enrichment reference sources."""

    # store_id → {store_name, tier, weekly_sales_k, region,
    #              competitor_proximity_miles, competitor_event}
    store_master: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # item_id → {item_name, category, subcategory, velocity_rank,
    #             perishable, retail_price, margin_pct, vendor_id}
    item_master: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # (item_id, store_id) → list[{promo_type, promo_start_date, promo_end_date,
    #                               tpr_depth_pct, circular_feature}]
    promo_calendar: Dict[Tuple[str, str], List[Dict[str, Any]]] = field(
        default_factory=dict
    )

    # vendor_id → {vendor_name, fill_rate_90d, late_shipments_30d,
    #               open_pos_count, last_incident_date}
    vendor_performance: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # item_id → {dc_id, units_on_hand, days_of_supply, next_receipt_date}
    dc_inventory: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # region → list[{disruption_type, description, active_from, active_through}]
    regional_signals: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# DataLoader
# ---------------------------------------------------------------------------


class DataLoader:
    """Reads all 6 enrichment reference sources into O(1) lookup dicts.

    Paths default to the values in config/config.yaml (``enrichment:`` section).
    Pass explicit paths to override — useful in tests.

    Raises:
        EnrichmentError: If any source file is missing or cannot be parsed.
    """

    def __init__(
        self,
        store_master_path: str | None = None,
        item_master_path: str | None = None,
        promo_calendar_path: str | None = None,
        vendor_performance_path: str | None = None,
        dc_inventory_path: str | None = None,
        regional_signals_path: str | None = None,
        config: EnrichmentConfig | None = None,
    ) -> None:
        if config is None:
            config = load_config().enrichment

        self._store_master_path = Path(store_master_path or config.store_master_path)
        self._item_master_path = Path(item_master_path or config.item_master_path)
        self._promo_calendar_path = Path(
            promo_calendar_path or config.promo_calendar_path
        )
        self._vendor_performance_path = Path(
            vendor_performance_path or config.vendor_performance_path
        )
        self._dc_inventory_path = Path(dc_inventory_path or config.dc_inventory_path)
        self._regional_signals_path = Path(
            regional_signals_path or config.regional_signals_path
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> LoadedData:
        """Load all 6 reference sources and return a ``LoadedData`` instance.

        Raises:
            EnrichmentError: On any missing or malformed file.
        """
        data = LoadedData()
        data.store_master = self._load_store_master()
        data.item_master = self._load_item_master()
        data.promo_calendar = self._load_promo_calendar()
        data.vendor_performance = self._load_vendor_performance()
        data.dc_inventory = self._load_dc_inventory()
        data.regional_signals = self._load_regional_signals()
        return data

    # ------------------------------------------------------------------
    # Private loaders
    # ------------------------------------------------------------------

    def _load_store_master(self) -> Dict[str, Dict[str, Any]]:
        """CSV → dict keyed by store_id."""
        rows = self._read_csv(self._store_master_path)
        result: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            store_id = row["store_id"]
            result[store_id] = {
                "store_name": row.get("store_name", ""),
                "tier": _to_int(row.get("tier")),
                "weekly_sales_k": _to_float(row.get("weekly_sales_k")),
                "region": row.get("region", ""),
                "competitor_proximity_miles": _to_float(
                    row.get("competitor_proximity_miles")
                ),
                "competitor_event": row.get("competitor_event") or None,
            }
        logger.info(f"store_master loaded: {len(result)} stores")
        return result

    def _load_item_master(self) -> Dict[str, Dict[str, Any]]:
        """CSV → dict keyed by item_id."""
        rows = self._read_csv(self._item_master_path)
        result: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            item_id = row["item_id"]
            result[item_id] = {
                "item_name": row.get("item_name", ""),
                "category": row.get("category", ""),
                "subcategory": row.get("subcategory", ""),
                "velocity_rank": _to_int(row.get("velocity_rank")),
                "perishable": _to_bool(row.get("perishable")),
                "retail_price": _to_float(row.get("retail_price")),
                "margin_pct": _to_float(row.get("margin_pct")),
                "vendor_id": row.get("vendor_id") or None,
            }
        logger.info(f"item_master loaded: {len(result)} items")
        return result

    def _load_promo_calendar(
        self,
    ) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
        """CSV → dict of (item_id, store_id) → list[promo row dicts]."""
        rows = self._read_csv(self._promo_calendar_path)
        result: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        for row in rows:
            key = (row["item_id"], row["store_id"])
            promo_row = {
                "promo_type": row.get("promo_type", ""),
                "promo_start_date": row.get("promo_start_date", ""),
                "promo_end_date": row.get("promo_end_date", ""),
                "tpr_depth_pct": _to_float(row.get("tpr_depth_pct")),
                "circular_feature": _to_bool(row.get("circular_feature")),
            }
            result.setdefault(key, []).append(promo_row)
        total_rows = sum(len(v) for v in result.values())
        logger.info(
            f"promo_calendar loaded: {total_rows} promos across {len(result)} (item, store) pairs"
        )
        return result

    def _load_vendor_performance(self) -> Dict[str, Dict[str, Any]]:
        """CSV → dict keyed by vendor_id."""
        rows = self._read_csv(self._vendor_performance_path)
        result: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            vendor_id = row["vendor_id"]
            result[vendor_id] = {
                "vendor_name": row.get("vendor_name", ""),
                "fill_rate_90d": _to_float(row.get("fill_rate_90d")),
                "late_shipments_30d": _to_int(row.get("late_shipments_30d")),
                "open_pos_count": _to_int(row.get("open_pos_count")),
                "last_incident_date": row.get("last_incident_date") or None,
            }
        logger.info(f"vendor_performance loaded: {len(result)} vendors")
        return result

    def _load_dc_inventory(self) -> Dict[str, Dict[str, Any]]:
        """CSV → dict keyed by item_id."""
        rows = self._read_csv(self._dc_inventory_path)
        result: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            item_id = row["item_id"]
            result[item_id] = {
                "dc_id": row.get("dc_id", ""),
                "units_on_hand": _to_int(row.get("units_on_hand")),
                "days_of_supply": _to_float(row.get("days_of_supply")),
                "next_receipt_date": row.get("next_receipt_date") or None,
            }
        logger.info(f"dc_inventory loaded: {len(result)} items")
        return result

    def _load_regional_signals(self) -> Dict[str, List[Dict[str, Any]]]:
        """JSON → dict keyed by region → list[disruption dicts]."""
        path = self._regional_signals_path
        if not path.exists():
            raise EnrichmentError(
                f"Regional signals file not found: {path}"
            )
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw: List[Dict[str, Any]] = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            raise EnrichmentError(
                f"Failed to parse regional signals JSON '{path}': {exc}"
            ) from exc

        result: Dict[str, List[Dict[str, Any]]] = {}
        for item in raw:
            region = item.get("region", "")
            disruption = {
                "disruption_type": item.get("disruption_type", ""),
                "description": item.get("description", ""),
                "active_from": item.get("active_from", ""),
                "active_through": item.get("active_through", ""),
            }
            result.setdefault(region, []).append(disruption)
        logger.info(
            f"regional_signals loaded: {len(raw)} disruptions across {len(result)} regions"
        )
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_csv(path: Path) -> List[Dict[str, str]]:
        """Read a CSV file and return list of row dicts (all values as strings).

        Raises:
            EnrichmentError: If the file is missing or cannot be parsed.
        """
        if not path.exists():
            raise EnrichmentError(f"Enrichment data file not found: {path}")
        try:
            with open(path, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                rows = [row for row in reader]
        except OSError as exc:
            raise EnrichmentError(
                f"Failed to read enrichment file '{path}': {exc}"
            ) from exc
        return rows


# ---------------------------------------------------------------------------
# Type coercion helpers
# ---------------------------------------------------------------------------


def _to_float(value: str | None) -> float | None:
    """Convert a string to float, returning None on empty or invalid input."""
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _to_int(value: str | None) -> int | None:
    """Convert a string to int, returning None on empty or invalid input."""
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(float(value))  # handle "1.0" → 1
    except (ValueError, TypeError):
        return None


def _to_bool(value: str | None) -> bool | None:
    """Convert a string to bool. Handles 'True'/'False'/'1'/'0'/''."""
    if value is None or str(value).strip() == "":
        return None
    return str(value).strip().lower() in ("true", "1", "yes")
