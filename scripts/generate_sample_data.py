"""Generate realistic sample data for the Replenishment Exception Triage Agent.

Produces 6 CSV files in data/sample/ with internally consistent, realistic
retail supply chain data. Uses a fixed random seed for reproducibility.

Usage:
    python scripts/generate_sample_data.py

Author: Mohith Kunta <mohith.kunta@gmail.com>
GitHub: https://github.com/m-kunta
"""

from __future__ import annotations

import csv
import json
import os
import random
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
from uuid import uuid4

# Fixed seed for reproducibility
SEED = 42
random.seed(SEED)

BASE_DIR = Path(__file__).parent.parent
SAMPLE_DIR = BASE_DIR / "data" / "sample"
REGIONAL_SIGNALS_PATH = BASE_DIR / "data" / "regional_signals.json"

# --- Store Master ---

REGIONS = ["NORTHEAST", "SOUTHEAST", "MIDWEST", "WEST", "SOUTHWEST"]

STORE_DATA = [
    # Tier 1 stores (weekly_sales_k >= 1500)
    ("STR-001", "Flagship Manhattan", 1, 2800.0, "NORTHEAST", 0.3, "Competitor grand opening sale"),
    ("STR-002", "Chicago Loop", 1, 2200.0, "MIDWEST", 0.5, None),
    ("STR-003", "LA Century City", 1, 1900.0, "WEST", 0.8, "Competitor clearance event"),
    ("STR-004", "Houston Galleria", 1, 1650.0, "SOUTHWEST", 1.2, None),
    # Tier 2 stores (800-1499)
    ("STR-005", "Atlanta Midtown", 2, 1200.0, "SOUTHEAST", 2.0, None),
    ("STR-006", "Denver Tech Center", 2, 1050.0, "WEST", 3.5, None),
    ("STR-007", "Phoenix Scottsdale", 2, 980.0, "SOUTHWEST", 1.5, "Competitor BOGO week"),
    ("STR-008", "Boston Back Bay", 2, 890.0, "NORTHEAST", 0.7, None),
    ("STR-009", "Minneapolis Uptown", 2, 850.0, "MIDWEST", 4.0, None),
    # Tier 3 stores (300-799)
    ("STR-010", "Nashville Green Hills", 3, 650.0, "SOUTHEAST", 5.0, None),
    ("STR-011", "Portland Pearl", 3, 580.0, "WEST", 2.5, None),
    ("STR-012", "Columbus Easton", 3, 420.0, "MIDWEST", 6.0, None),
    ("STR-013", "Charlotte SouthPark", 3, 390.0, "SOUTHEAST", 3.0, None),
    # Tier 4 stores (< 300)
    ("STR-014", "Rural Topeka", 4, 180.0, "MIDWEST", 15.0, None),
    ("STR-015", "Small Town Boise", 4, 120.0, "WEST", 20.0, None),
]

# --- Item Master ---

VENDOR_IDS = ["VND-100", "VND-200", "VND-300", "VND-400", "VND-500"]

ITEM_DATA = [
    # (item_id, item_name, category, subcategory, velocity_rank, perishable, retail_price, margin_pct, vendor_id)
    ("ITM-1001", "Organic Whole Milk 1gal", "Dairy", "Milk", 1, True, 5.99, 0.28, "VND-100"),
    ("ITM-1002", "Large Eggs 12ct", "Dairy", "Eggs", 2, True, 4.49, 0.32, "VND-100"),
    ("ITM-1003", "Sliced White Bread", "Bakery", "Bread", 3, True, 3.99, 0.35, "VND-200"),
    ("ITM-1004", "Banana Bundle 1lb", "Produce", "Fruit", 4, True, 0.69, 0.40, "VND-300"),
    ("ITM-1005", "Chicken Breast 2lb", "Meat", "Poultry", 5, True, 9.99, 0.22, "VND-300"),
    ("ITM-1006", "Cheddar Cheese Block 8oz", "Dairy", "Cheese", 8, False, 4.99, 0.30, "VND-100"),
    ("ITM-1007", "Paper Towels 6-roll", "Household", "Paper", 10, False, 8.99, 0.25, "VND-400"),
    ("ITM-1008", "Laundry Detergent 64oz", "Household", "Cleaning", 12, False, 11.99, 0.20, "VND-400"),
    ("ITM-1009", "Peanut Butter 16oz", "Grocery", "Spreads", 15, False, 3.49, 0.38, "VND-200"),
    ("ITM-1010", "Pasta Sauce 24oz", "Grocery", "Sauces", 18, False, 4.29, 0.35, "VND-200"),
    ("ITM-1011", "Greek Yogurt 32oz", "Dairy", "Yogurt", 6, True, 6.49, 0.30, "VND-100"),
    ("ITM-1012", "Baby Formula 12.5oz", "Baby", "Formula", 20, False, 24.99, 0.15, "VND-500"),
    ("ITM-1013", "Diapers Size 3 28ct", "Baby", "Diapers", 22, False, 12.99, 0.18, "VND-500"),
    ("ITM-1014", "Coffee Ground 12oz", "Grocery", "Beverages", 7, False, 8.99, 0.33, "VND-200"),
    ("ITM-1015", "Orange Juice 52oz", "Dairy", "Juice", 9, True, 4.99, 0.28, "VND-100"),
    ("ITM-1016", "Frozen Pizza 12in", "Frozen", "Pizza", 11, False, 6.99, 0.30, "VND-300"),
    ("ITM-1017", "Ice Cream 1.5qt", "Frozen", "Dessert", 13, False, 5.99, 0.32, "VND-300"),
    ("ITM-1018", "Toilet Paper 12-roll", "Household", "Paper", 14, False, 9.99, 0.22, "VND-400"),
    ("ITM-1019", "Dish Soap 22oz", "Household", "Cleaning", 16, False, 3.99, 0.28, "VND-400"),
    ("ITM-1020", "Cereal Box 18oz", "Grocery", "Breakfast", 17, False, 4.49, 0.35, "VND-200"),
]

# --- Vendor Performance ---

VENDOR_DATA = [
    # (vendor_id, vendor_name, fill_rate_90d, late_shipments_30d, open_pos_count, last_incident_date)
    ("VND-100", "National Dairy Co-op", 0.94, 3, 12, "2026-03-01"),
    ("VND-200", "Heartland Foods Inc", 0.88, 7, 8, "2026-03-10"),
    ("VND-300", "Pacific Fresh Suppliers", 0.97, 1, 15, "2026-01-15"),
    ("VND-400", "CleanHome Distributors", 0.72, 12, 5, "2026-03-14"),  # Problematic vendor
    ("VND-500", "BabyCare National", 0.96, 2, 10, "2026-02-20"),
]

# --- DC Inventory ---

DC_INVENTORY_DATA = []
for item in ITEM_DATA:
    item_id = item[0]
    # Vary DC inventory by item
    if item_id in ("ITM-1007", "ITM-1008", "ITM-1018", "ITM-1019"):
        # VND-400 items: low DC inventory
        dc_days = round(random.uniform(2.0, 8.0), 1)
    elif item_id == "ITM-1001":
        # For phantom inventory scenario: high DC supply
        dc_days = 35.0
    else:
        dc_days = round(random.uniform(10.0, 45.0), 1)
    units = int(dc_days * random.randint(50, 200))
    next_receipt = (date(2026, 3, 16) + timedelta(days=random.randint(1, 14))).isoformat()
    DC_INVENTORY_DATA.append((item_id, "DC-EAST", units, dc_days, next_receipt))

# --- Promo Calendar ---

EXCEPTION_DATE = date(2026, 3, 16)

PROMO_ENTRIES = [
    # Active promos (exception_date falls within window)
    ("ITM-1001", "STR-001", "TPR", "2026-03-10", "2026-03-20", 0.25, True),   # CRITICAL scenario: OOS + Tier1 + promo + competitor
    ("ITM-1001", "STR-002", "TPR", "2026-03-10", "2026-03-20", 0.20, False),
    ("ITM-1002", "STR-001", "FEATURE", "2026-03-14", "2026-03-21", 0.0, True),
    ("ITM-1005", "STR-003", "TPR", "2026-03-12", "2026-03-19", 0.30, True),
    ("ITM-1014", "STR-005", "DISPLAY", "2026-03-15", "2026-03-22", 0.0, True),
    ("ITM-1007", "STR-001", "TPR", "2026-03-10", "2026-03-18", 0.15, False),
    ("ITM-1012", "STR-007", "TPR", "2026-03-13", "2026-03-25", 0.10, True),
    ("ITM-1016", "STR-006", "BOTH", "2026-03-14", "2026-03-21", 0.20, True),
    # Expired promos (should not flag as active)
    ("ITM-1009", "STR-010", "TPR", "2026-03-01", "2026-03-10", 0.15, False),
    ("ITM-1010", "STR-011", "FEATURE", "2026-02-20", "2026-03-05", 0.0, True),
]

# --- Exception Generation ---

EXCEPTION_TYPES = ["OOS", "LOW_STOCK", "FORECAST_VARIANCE", "ORDER_FAILURE", "VENDOR_LATE"]
EXCEPTION_WEIGHTS = [0.40, 0.30, 0.15, 0.10, 0.05]


def _pick_exception_type() -> str:
    return random.choices(EXCEPTION_TYPES, weights=EXCEPTION_WEIGHTS, k=1)[0]


def _gen_days_of_supply(exc_type: str) -> float:
    if exc_type == "OOS":
        return round(random.uniform(0.0, 0.5), 1)
    elif exc_type == "LOW_STOCK":
        return round(random.uniform(0.5, 3.0), 1)
    elif exc_type == "FORECAST_VARIANCE":
        return round(random.uniform(2.0, 10.0), 1)
    elif exc_type == "ORDER_FAILURE":
        return round(random.uniform(1.0, 5.0), 1)
    else:  # VENDOR_LATE
        return round(random.uniform(1.0, 4.0), 1)


def _gen_units_on_hand(exc_type: str) -> int:
    if exc_type == "OOS":
        return 0
    elif exc_type == "LOW_STOCK":
        return random.randint(1, 15)
    else:
        return random.randint(5, 50)


def _gen_variance_pct(exc_type: str) -> float | None:
    if exc_type == "FORECAST_VARIANCE":
        return round(random.uniform(20.0, 85.0), 1)
    elif exc_type in ("OOS", "LOW_STOCK"):
        return round(random.uniform(-10.0, 15.0), 1)
    return None


def generate_exceptions() -> list[dict]:
    exceptions = []
    used_combos = set()

    # --- Scenario 1: CRITICAL — OOS + Tier 1 + active TPR + competitor nearby ---
    exceptions.append({
        "exception_id": str(uuid4()),
        "item_id": "ITM-1001",
        "item_name": "Organic Whole Milk 1gal",
        "store_id": "STR-001",
        "store_name": "Flagship Manhattan",
        "exception_type": "OOS",
        "exception_date": EXCEPTION_DATE.isoformat(),
        "units_on_hand": 0,
        "days_of_supply": 0.0,
        "variance_pct": 5.2,
        "source_system": "BlueYonder",
    })
    used_combos.add(("ITM-1001", "STR-001", "OOS", EXCEPTION_DATE.isoformat()))

    # --- Scenario 2: Phantom inventory — OOS but vendor fill rate > 97%, DC 30+ days ---
    exceptions.append({
        "exception_id": str(uuid4()),
        "item_id": "ITM-1001",
        "item_name": "Organic Whole Milk 1gal",
        "store_id": "STR-005",
        "store_name": "Atlanta Midtown",
        "exception_type": "OOS",
        "exception_date": EXCEPTION_DATE.isoformat(),
        "units_on_hand": 0,
        "days_of_supply": 0.0,
        "variance_pct": 2.1,
        "source_system": "BlueYonder",
    })
    used_combos.add(("ITM-1001", "STR-005", "OOS", EXCEPTION_DATE.isoformat()))

    # --- Scenario 3: 12+ exceptions from VND-400 (CleanHome) to trigger vendor pattern ---
    vnd400_items = ["ITM-1007", "ITM-1008", "ITM-1018", "ITM-1019"]
    vnd400_stores = ["STR-001", "STR-002", "STR-003", "STR-005", "STR-006",
                     "STR-007", "STR-008", "STR-010", "STR-011", "STR-012",
                     "STR-013", "STR-014"]
    vnd400_count = 0
    for item_id in vnd400_items:
        item_row = next(i for i in ITEM_DATA if i[0] == item_id)
        for store_id in random.sample(vnd400_stores, min(4, len(vnd400_stores))):
            if vnd400_count >= 14:
                break
            combo = (item_id, store_id, "LOW_STOCK", EXCEPTION_DATE.isoformat())
            if combo in used_combos:
                continue
            store_row = next(s for s in STORE_DATA if s[0] == store_id)
            exceptions.append({
                "exception_id": str(uuid4()),
                "item_id": item_id,
                "item_name": item_row[1],
                "store_id": store_id,
                "store_name": store_row[1],
                "exception_type": "LOW_STOCK",
                "exception_date": EXCEPTION_DATE.isoformat(),
                "units_on_hand": random.randint(1, 5),
                "days_of_supply": round(random.uniform(0.5, 2.0), 1),
                "variance_pct": round(random.uniform(-5.0, 10.0), 1),
                "source_system": "BlueYonder",
            })
            used_combos.add(combo)
            vnd400_count += 1
        if vnd400_count >= 14:
            break

    # --- Scenario 4: 5 LOW priority — high variance but zero business risk ---
    low_priority_configs = [
        ("ITM-1020", "STR-014", "FORECAST_VARIANCE"),  # Low-tier store, non-perishable
        ("ITM-1010", "STR-015", "FORECAST_VARIANCE"),
        ("ITM-1009", "STR-014", "FORECAST_VARIANCE"),
        ("ITM-1020", "STR-015", "FORECAST_VARIANCE"),
        ("ITM-1010", "STR-012", "FORECAST_VARIANCE"),
    ]
    for item_id, store_id, exc_type in low_priority_configs:
        combo = (item_id, store_id, exc_type, EXCEPTION_DATE.isoformat())
        if combo in used_combos:
            continue
        item_row = next(i for i in ITEM_DATA if i[0] == item_id)
        store_row = next(s for s in STORE_DATA if s[0] == store_id)
        exceptions.append({
            "exception_id": str(uuid4()),
            "item_id": item_id,
            "item_name": item_row[1],
            "store_id": store_id,
            "store_name": store_row[1],
            "exception_type": exc_type,
            "exception_date": EXCEPTION_DATE.isoformat(),
            "units_on_hand": random.randint(20, 50),
            "days_of_supply": round(random.uniform(5.0, 10.0), 1),
            "variance_pct": round(random.uniform(40.0, 85.0), 1),
            "source_system": "BlueYonder",
        })
        used_combos.add(combo)

    # --- Fill remaining to reach 120 exceptions ---
    all_items = [i for i in ITEM_DATA]
    all_stores = [s for s in STORE_DATA]

    while len(exceptions) < 120:
        item_row = random.choice(all_items)
        store_row = random.choice(all_stores)
        exc_type = _pick_exception_type()
        combo = (item_row[0], store_row[0], exc_type, EXCEPTION_DATE.isoformat())
        if combo in used_combos:
            continue
        used_combos.add(combo)
        exceptions.append({
            "exception_id": str(uuid4()),
            "item_id": item_row[0],
            "item_name": item_row[1],
            "store_id": store_row[0],
            "store_name": store_row[1],
            "exception_type": exc_type,
            "exception_date": EXCEPTION_DATE.isoformat(),
            "units_on_hand": _gen_units_on_hand(exc_type),
            "days_of_supply": _gen_days_of_supply(exc_type),
            "variance_pct": _gen_variance_pct(exc_type),
            "source_system": "BlueYonder",
        })

    return exceptions[:120]


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Written: {path} ({len(rows)} rows)")


def write_store_master():
    rows = [
        {
            "store_id": s[0], "store_name": s[1], "tier": s[2],
            "weekly_sales_k": s[3], "region": s[4],
            "competitor_proximity_miles": s[5],
            "competitor_event": s[6] or "",
        }
        for s in STORE_DATA
    ]
    write_csv(
        SAMPLE_DIR / "store_master_sample.csv", rows,
        ["store_id", "store_name", "tier", "weekly_sales_k", "region",
         "competitor_proximity_miles", "competitor_event"],
    )


def write_item_master():
    rows = [
        {
            "item_id": i[0], "item_name": i[1], "category": i[2],
            "subcategory": i[3], "velocity_rank": i[4],
            "perishable": i[5], "retail_price": i[6],
            "margin_pct": i[7], "vendor_id": i[8],
        }
        for i in ITEM_DATA
    ]
    write_csv(
        SAMPLE_DIR / "item_master_sample.csv", rows,
        ["item_id", "item_name", "category", "subcategory", "velocity_rank",
         "perishable", "retail_price", "margin_pct", "vendor_id"],
    )


def write_promo_calendar():
    rows = [
        {
            "item_id": p[0], "store_id": p[1], "promo_type": p[2],
            "promo_start_date": p[3], "promo_end_date": p[4],
            "tpr_depth_pct": p[5], "circular_feature": p[6],
        }
        for p in PROMO_ENTRIES
    ]
    write_csv(
        SAMPLE_DIR / "promo_calendar_sample.csv", rows,
        ["item_id", "store_id", "promo_type", "promo_start_date",
         "promo_end_date", "tpr_depth_pct", "circular_feature"],
    )


def write_vendor_performance():
    rows = [
        {
            "vendor_id": v[0], "vendor_name": v[1], "fill_rate_90d": v[2],
            "late_shipments_30d": v[3], "open_pos_count": v[4],
            "last_incident_date": v[5],
        }
        for v in VENDOR_DATA
    ]
    write_csv(
        SAMPLE_DIR / "vendor_performance_sample.csv", rows,
        ["vendor_id", "vendor_name", "fill_rate_90d", "late_shipments_30d",
         "open_pos_count", "last_incident_date"],
    )


def write_dc_inventory():
    rows = [
        {
            "item_id": d[0], "dc_id": d[1], "units_on_hand": d[2],
            "days_of_supply": d[3], "next_receipt_date": d[4],
        }
        for d in DC_INVENTORY_DATA
    ]
    write_csv(
        SAMPLE_DIR / "dc_inventory_sample.csv", rows,
        ["item_id", "dc_id", "units_on_hand", "days_of_supply", "next_receipt_date"],
    )


def write_exceptions():
    exceptions = generate_exceptions()
    write_csv(
        SAMPLE_DIR / "exceptions_sample.csv", exceptions,
        ["exception_id", "item_id", "item_name", "store_id", "store_name",
         "exception_type", "exception_date", "units_on_hand", "days_of_supply",
         "variance_pct", "source_system"],
    )


def write_regional_signals():
    signals = [
        {
            "region": "MIDWEST",
            "disruption_type": "WEATHER",
            "description": "Winter storm warning active through March 18",
            "active_from": "2026-03-15",
            "active_through": "2026-03-18",
        },
        {
            "region": "NORTHEAST",
            "disruption_type": "TRANSPORT",
            "description": "Port congestion at Newark — expect 2-day delays on inbound freight",
            "active_from": "2026-03-14",
            "active_through": "2026-03-20",
        },
    ]
    REGIONAL_SIGNALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REGIONAL_SIGNALS_PATH, "w", encoding="utf-8") as f:
        json.dump(signals, f, indent=2)
    print(f"  Written: {REGIONAL_SIGNALS_PATH} ({len(signals)} signals)")


def main():
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    print("Generating sample data...")
    write_store_master()
    write_item_master()
    write_promo_calendar()
    write_vendor_performance()
    write_dc_inventory()
    write_exceptions()
    write_regional_signals()
    print("Done. All sample data generated.")


if __name__ == "__main__":
    main()
