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
"""

from __future__ import annotations

# TODO: implement DataLoader
# See implementation_plan.md for full spec.
#
# Implementation checklist:
#   [ ] Define `LoadedData` dataclass with 6 dict/list fields
#   [ ] DataLoader.__init__(self, store_master_path, item_master_path,
#                           promo_calendar_path, vendor_performance_path,
#                           dc_inventory_path, regional_signals_path)
#         → default paths read from config/config.yaml enrichment section
#   [ ] DataLoader.load() -> LoadedData
#         → _load_store_master()       : CSV → dict[store_id, dict]
#         → _load_item_master()        : CSV → dict[item_id, dict]
#         → _load_promo_calendar()     : CSV → dict[(item_id, store_id), list[dict]]
#         → _load_vendor_performance() : CSV → dict[vendor_id, dict]
#         → _load_dc_inventory()       : CSV → dict[item_id, dict]
#         → _load_regional_signals()   : JSON → dict[region, list[dict]]
#   [ ] Raise EnrichmentError (src/utils/exceptions.py) on missing/malformed file
#   [ ] Log counts after each source loads (loguru)
