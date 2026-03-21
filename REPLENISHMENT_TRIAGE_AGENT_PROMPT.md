# Replenishment Exception Triage Agent
### Claude Code / Antigravity Project Prompt
**Author:** Mohith Kunta | [github.com/m-kunta](https://github.com/m-kunta)  
**Repo:** `replenishment-triage-ai`  
**License:** MIT  
**Version:** 1.0

---

## PROJECT OVERVIEW

Build a production-grade, AI-powered agentic system that ingests replenishment exceptions from any retail planning system, enriches each exception with contextual business signals, and uses Claude (Anthropic LLM) to triage exceptions by business consequence — not magnitude. The output is a prioritized exception list with plain-English action briefs, financial impact statements, cross-exception pattern flags, and a morning briefing document that planners can act on immediately.

**The core shift:** Move planning teams from magnitude-sorted exception queues (which bury the most critical items) to consequence-sorted queues (which surface what actually matters to the business today).

**Target users:** Supply planners, inventory analysts, replenishment managers, category managers at retail organizations.

**Build environment:** Claude Code or Antigravity agentic workflow engine.

**Important:** This document is a forward-looking implementation specification across all phases.
Some commands and files in later phases (for example `scripts/run_triage.py`) are targets and
may not exist in the current repository state until those phases are implemented.

---

## ARCHITECTURE — FOUR LAYERS

```
Layer 1: Ingestion & Normalization
  → Accepts CSV, REST API, SQL query output
  → Normalizes to canonical exception schema
  → Validates, deduplicates, quarantines invalid records

Layer 2: Context Enrichment
  → Parallel joins across 10 data sources
  → Computes financial value fields deterministically
  → Null-safe; missing fields flagged, not dropped

Layer 3: Claude Reasoning Engine (AI Core)
  → Batches of 25–50 enriched exceptions per API call
  → Two-pass: per-exception triage + macro pattern detection
  → Structured JSON output per exception
  → Agent mesh: Phantom Inventory webhook integration

Layer 4: Routing, Alerting & Output
  → Priority queue routing (CRITICAL / HIGH / MEDIUM / LOW)
  → CRITICAL alert dispatch with SLA escalation
  → Morning briefing document generation
  → Exception log for backtesting pipeline
```

---

## COMPLETE TASK LIST

Work through these tasks in order. Each task produces a discrete, testable deliverable. Do not proceed to the next task until the current one passes its acceptance criteria.

---

### PHASE 1 — PROJECT SCAFFOLD & DATA FOUNDATION

#### Task 1.1 — Initialize Repository Structure

Create the following directory and file structure:

```
replenishment-triage-ai/
├── README.md
├── LICENSE
├── .env.example
├── .gitignore
├── requirements.txt
├── config/
│   └── config.yaml
├── data/
│   ├── sample/
│   │   ├── exceptions_sample.csv
│   │   ├── store_master_sample.csv
│   │   ├── item_master_sample.csv
│   │   ├── promo_calendar_sample.csv
│   │   └── vendor_performance_sample.csv
│   └── schema/
│       └── canonical_exception_schema.json
├── prompts/
│   ├── system_prompt.md
│   ├── triage_framework.md
│   ├── output_contract.md
│   ├── pattern_detection.md
│   ├── epistemic_honesty.md
│   ├── phantom_inventory.md
│   └── few_shot_library.json
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── base_adapter.py
│   │   ├── csv_adapter.py
│   │   ├── api_adapter.py
│   │   ├── sql_adapter.py
│   │   └── normalizer.py
│   ├── enrichment/
│   │   ├── __init__.py
│   │   ├── enrichment_pipeline.py
│   │   ├── store_enricher.py
│   │   ├── item_enricher.py
│   │   ├── promo_enricher.py
│   │   ├── vendor_enricher.py
│   │   ├── dc_inventory_enricher.py
│   │   ├── financial_calculator.py
│   │   └── regional_signal_enricher.py
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── triage_agent.py
│   │   ├── batch_processor.py
│   │   ├── pattern_analyzer.py
│   │   ├── prompt_composer.py
│   │   └── phantom_webhook.py
│   ├── output/
│   │   ├── __init__.py
│   │   ├── router.py
│   │   ├── alert_dispatcher.py
│   │   ├── briefing_generator.py
│   │   └── exception_logger.py
│   └── utils/
│       ├── __init__.py
│       ├── config_loader.py
│       ├── logger.py
│       └── validators.py
├── tests/
│   ├── __init__.py
│   ├── fixtures/
│   │   └── enriched_exceptions_fixture.json
│   ├── test_ingestion.py
│   ├── test_enrichment.py
│   ├── test_agent.py
│   ├── test_output.py
│   └── test_prompt_output.py
├── scripts/
│   ├── run_triage.py
│   ├── run_backtest.py
│   └── generate_sample_data.py
└── output/
    ├── briefings/
    ├── logs/
    └── backtest/
```

**Acceptance criteria:** All directories and placeholder files created. `README.md` contains project description, architecture diagram (ASCII), setup instructions, and usage examples.

---

#### Task 1.2 — Define Canonical Exception Schema

Create `data/schema/canonical_exception_schema.json` with the following fields. This is the contract between Layer 1 and all downstream layers:

```json
{
  "exception_id": "string — unique identifier for this exception instance",
  "item_id": "string — internal SKU identifier",
  "item_name": "string — human-readable item description",
  "store_id": "string — store identifier",
  "store_name": "string — human-readable store name",
  "exception_type": "enum: OOS | LOW_STOCK | FORECAST_VARIANCE | ORDER_FAILURE | VENDOR_LATE | DATA_INTEGRITY",
  "exception_date": "ISO date string YYYY-MM-DD",
  "units_on_hand": "integer",
  "days_of_supply": "float — calculated at current velocity",
  "variance_pct": "float | null — forecast vs actual, null if not applicable",
  "source_system": "string — name of originating planning system",
  "batch_id": "string — UUID for the ingestion batch this exception belongs to",
  "ingested_at": "ISO datetime string"
}
```

**Enriched exception schema** (output of Layer 2, input to Layer 3):

All canonical fields, plus:

```json
{
  "velocity_rank": "integer | null — item rank within category by weekly units",
  "store_tier": "integer | null — 1 (highest volume) to 4 (lowest volume)",
  "weekly_store_sales_k": "float | null — store weekly revenue in thousands USD",
  "promo_active": "boolean | null",
  "promo_type": "enum: TPR | FEATURE | DISPLAY | BOTH | NONE | null",
  "promo_end_date": "ISO date string | null",
  "dc_inventory_days": "float | null — days of supply at DC for this item",
  "vendor_fill_rate_90d": "float | null — vendor fill rate % last 90 days",
  "open_po_inbound": "boolean | null",
  "next_delivery_date": "ISO date string | null",
  "lead_time_days": "integer | null",
  "competitor_proximity_miles": "float | null",
  "competitor_event": "string | null — description of any competitor activity",
  "perishable": "boolean | null",
  "day_of_week_demand_index": "float | null — 1.0 = average, >1.0 = above average",
  "est_lost_sales_value": "float | null — USD, computed in financial_calculator.py",
  "promo_margin_at_risk": "float | null — USD, computed in financial_calculator.py",
  "regional_disruption_flag": "boolean | null",
  "regional_disruption_description": "string | null",
  "missing_data_fields": "array of strings — field names that are null",
  "enrichment_confidence": "enum: HIGH | MEDIUM | LOW — based on missing_data_fields count"
}
```

**Acceptance criteria:** Schema file exists and is valid JSON. Write a schema validator in `src/utils/validators.py` that checks both schemas and raises typed exceptions on violation.

---

#### Task 1.3 — Generate Realistic Sample Data

Create `scripts/generate_sample_data.py` that generates the following sample files in `data/sample/`. All data must be realistic enough to produce meaningful AI triage output.

**`exceptions_sample.csv`** — 120 rows:
- Mix of exception types: 40% OOS, 30% LOW_STOCK, 15% FORECAST_VARIANCE, 10% ORDER_FAILURE, 5% VENDOR_LATE
- Include at least 12 exceptions from the same vendor (to trigger pattern detection)
- Include at least 1 CRITICAL scenario: OOS + Tier 1 store + active TPR + competitor nearby
- Include at least 1 phantom inventory scenario: OOS at store but vendor fill rate > 97% and DC has 30+ days supply
- Include at least 5 LOW priority exceptions with high variance but zero business risk

**`store_master_sample.csv`** — columns: store_id, store_name, tier, weekly_sales_k, region, competitor_proximity_miles, competitor_event

**`item_master_sample.csv`** — columns: item_id, item_name, category, subcategory, velocity_rank, perishable, retail_price, margin_pct

**`promo_calendar_sample.csv`** — columns: item_id, store_id, promo_type, promo_start_date, promo_end_date, tpr_depth_pct, circular_feature

**`vendor_performance_sample.csv`** — columns: vendor_id, vendor_name, fill_rate_90d, late_shipments_30d, open_pos_count, last_incident_date

**`dc_inventory_sample.csv`** — columns: item_id, dc_id, units_on_hand, days_of_supply, next_receipt_date

**Acceptance criteria:** All CSVs generate successfully. Running the script twice produces identical output (set a fixed random seed). Data passes canonical schema validation.

---

#### Task 1.4 — Build Configuration System

Create `config/config.yaml` with the following structure. All environment-specific values reference environment variables using `${VAR_NAME}` syntax:

```yaml
ingestion:
  adapter: csv                          # csv | api | sql
  csv:
    path: data/sample/exceptions_sample.csv
    delimiter: ","
    date_format: "%Y-%m-%d"
  api:
    endpoint: ${EXCEPTION_API_ENDPOINT}
    api_key: ${EXCEPTION_API_KEY}
    method: GET
    response_path: data.exceptions     # JSONPath to exception array
  sql:
    connection_string: ${DB_CONNECTION_STRING}
    query_file: config/exception_query.sql
    
enrichment:
  store_master_path: data/sample/store_master_sample.csv
  item_master_path: data/sample/item_master_sample.csv
  promo_calendar_path: data/sample/promo_calendar_sample.csv
  vendor_performance_path: data/sample/vendor_performance_sample.csv
  dc_inventory_path: data/sample/dc_inventory_sample.csv
  parallel_workers: 4
  null_threshold_low_confidence: 3     # exceptions with >= 3 null enrichment fields = LOW confidence
  null_threshold_medium_confidence: 1  # 1-2 null fields = MEDIUM confidence

agent:
  anthropic_api_key: ${ANTHROPIC_API_KEY}
  model: claude-sonnet-4-20250514
  max_tokens: 4000
  batch_size: 30
  retry_attempts: 3
  retry_backoff_seconds: 5
  reasoning_trace_enabled: false       # set true to include chain-of-thought in output
  phantom_webhook_enabled: true
  phantom_webhook_url: ${PHANTOM_WEBHOOK_URL}  # optional; leave blank to disable

store_tiers:
  tier_1_min_weekly_sales_k: 1500
  tier_2_min_weekly_sales_k: 800
  tier_3_min_weekly_sales_k: 300
  tier_4_min_weekly_sales_k: 0

priority_rules:
  critical_max_days_supply_tier_1_on_promo: 1.5
  critical_max_days_supply_perishable: 1.0
  critical_min_vendor_pattern_count: 5
  high_max_days_supply_tier_1_2: 3.0

alerting:
  channels:
    - type: email
      enabled: false
      smtp_host: ${SMTP_HOST}
      smtp_port: 587
      from_address: ${ALERT_FROM_EMAIL}
      to_addresses:
        - ${PLANNER_EMAIL}
    - type: slack
      enabled: false
      webhook_url: ${SLACK_WEBHOOK_URL}
    - type: teams
      enabled: false
      webhook_url: ${TEAMS_WEBHOOK_URL}
  critical_sla_minutes: 60
  secondary_escalation_contact: ${CATEGORY_MANAGER_EMAIL}

output:
  briefing_dir: output/briefings
  log_dir: output/logs
  format: markdown                     # markdown | json | both
  include_low_priority: true
  max_exceptions_in_briefing: 10       # top N shown in morning briefing

backtest:
  log_dir: output/backtest
  outcome_check_weeks: [4, 8]
```

Create `src/utils/config_loader.py` that loads this YAML, resolves `${VAR_NAME}` references from environment variables, and raises a typed `ConfigurationError` if required variables are missing. Provide a `.env.example` with all required variables listed.

**Acceptance criteria:** Config loads successfully with sample env vars. Missing required env var raises `ConfigurationError` with a clear message naming the missing variable.

---

### PHASE 2 — INGESTION LAYER

#### Task 2.1 — Build Base Adapter Interface

Create `src/ingestion/base_adapter.py`:

```python
from abc import ABC, abstractmethod
from typing import List, Dict

class BaseIngestionAdapter(ABC):
    """
    Abstract base class for all ingestion adapters.
    All adapters return a list of raw exception dicts.
    Downstream normalizer converts these to canonical schema.
    """
    
    @abstractmethod
    def fetch(self) -> List[Dict]:
        """Fetch raw exception records from the source system."""
        pass
    
    @abstractmethod
    def validate_connection(self) -> bool:
        """Validate that the source system is reachable before fetching."""
        pass
```

**Acceptance criteria:** Abstract class defined. Any attempt to instantiate it directly raises `TypeError`.

---

#### Task 2.2 — Build CSV Adapter

Create `src/ingestion/csv_adapter.py`. Requirements:
- Reads CSV from configured path
- Handles UTF-8 and UTF-8-BOM encodings
- Supports configurable delimiter (default comma)
- Returns list of raw dicts (all values as strings — normalizer handles type coercion)
- Raises `IngestionError` with path and row number on parse failure
- Logs: total rows read, any rows skipped with reason

**Acceptance criteria:** Reads `exceptions_sample.csv`. Returns 120 raw dicts. Test with a malformed row to confirm graceful error handling.

---

#### Task 2.3 — Build API Adapter

Create `src/ingestion/api_adapter.py`. Requirements:
- HTTP GET or POST to configured endpoint
- Bearer token auth via `api_key` config
- JSONPath extraction of exception array from response
- Handles pagination if `next_page` field present in response
- Retry logic: 3 attempts with exponential backoff on HTTP 5xx
- Raises `IngestionError` on HTTP 4xx (no retry)
- Connection timeout: 30 seconds

**Acceptance criteria:** Passes unit test using `responses` library mock. Correctly handles paginated mock response. Raises `IngestionError` on 401.

---

#### Task 2.4 — Build SQL Adapter

Create `src/ingestion/sql_adapter.py`. Requirements:
- Supports PostgreSQL, Snowflake, BigQuery, SQL Server via SQLAlchemy
- Reads SQL query from configured query file path
- Parameterized query support: substitutes `{run_date}` with today's date
- Streams results in chunks of 500 rows to avoid memory issues on large sets
- Raises `IngestionError` on connection failure with sanitized error message (no credentials in logs)

**Acceptance criteria:** Passes unit test with SQLite in-memory DB as a stand-in.

---

#### Task 2.5 — Build Normalizer

Create `src/ingestion/normalizer.py`. Requirements:

- Accepts raw dict from any adapter
- Maps source field names to canonical schema field names (mapping defined in `config.yaml` under `ingestion.field_mapping`)
- Type coercion: integers, floats, ISO dates, booleans
- Deduplication: within a batch, if the same `(item_id, store_id, exception_type, exception_date)` appears twice, keep the first and log the duplicate
- Generates `exception_id` as `UUID4` if not present in source
- Generates `batch_id` as a single `UUID4` for the full ingestion run
- Quarantine: records missing required fields (`item_id`, `store_id`, `exception_type`, `exception_date`) are written to `output/logs/quarantine_{date}.json` with a reason code, not passed downstream
- Returns: `(valid_records: List[CanonicalException], quarantined_count: int)`

**Acceptance criteria:** Normalizes 120 sample rows. Zero valid records lost to quarantine on clean data. One intentionally malformed row is quarantined correctly with reason code.

---

### PHASE 3 — ENRICHMENT LAYER

#### Task 3.1 — Build Enrichment Pipeline Orchestrator

Create `src/enrichment/enrichment_pipeline.py`. This is the orchestrator that:

- Accepts a list of `CanonicalException` objects
- Runs all enrichers in parallel using `concurrent.futures.ThreadPoolExecutor` with configurable `parallel_workers`
- Each enricher is called with the full batch (not one at a time) to allow bulk lookups
- Assembles enriched exception objects by joining results from all enrichers on `(item_id, store_id)`
- After all enrichers complete: counts null enrichment fields per exception, sets `missing_data_fields` list and `enrichment_confidence` (HIGH / MEDIUM / LOW) based on config thresholds
- Returns: `List[EnrichedExceptionSchema]`

**Acceptance criteria:** Pipeline completes for all 120 sample records. Parallel execution confirmed by timing (faster than sequential). Enrichment confidence levels distributed across HIGH/MEDIUM/LOW in sample output.

---

#### Task 3.2 — Build Store Enricher

Create `src/enrichment/store_enricher.py`. Reads from store master (CSV or DB). For each exception, joins on `store_id` and populates:
- `store_name`, `store_tier`, `weekly_store_sales_k`, `region`
- `competitor_proximity_miles`, `competitor_event`

Bulk lookup: load full store master into memory as a dict keyed by `store_id` for O(1) lookup per exception.

**Acceptance criteria:** All 120 records enriched with store fields. Zero failures on valid store IDs. Unknown store ID sets fields to null with `store_id` added to `missing_data_fields`.

---

#### Task 3.3 — Build Item Enricher

Create `src/enrichment/item_enricher.py`. Reads from item master. For each exception, joins on `item_id` and populates:
- `velocity_rank`, `perishable`, `retail_price`, `margin_pct`

Bulk lookup pattern (same as store enricher).

**Acceptance criteria:** Same pattern as Task 3.2.

---

#### Task 3.4 — Build Promo Enricher

Create `src/enrichment/promo_enricher.py`. Reads from promo calendar. For each exception, checks if `exception_date` falls within an active promo window for that `(item_id, store_id)` combination. Populates:
- `promo_active`, `promo_type`, `promo_end_date`, `tpr_depth_pct`

Important: an item may have multiple promo records. If multiple active promos exist, select the one with the highest `tpr_depth_pct` and concatenate types.

**Acceptance criteria:** All sample exceptions with active promos are correctly flagged. Exception date outside promo window correctly sets `promo_active = false`.

---

#### Task 3.5 — Build Vendor Enricher

Create `src/enrichment/vendor_enricher.py`. Reads vendor performance data. Joins via item master's `vendor_id` field. Populates:
- `vendor_fill_rate_90d`, `open_po_inbound`, `next_delivery_date`, `lead_time_days`

**Acceptance criteria:** Vendor fields populated for all items with known vendor_id. Unknown vendor sets to null with flag.

---

#### Task 3.6 — Build DC Inventory Enricher

Create `src/enrichment/dc_inventory_enricher.py`. Reads DC inventory snapshot. Populates:
- `dc_inventory_days`, `next_delivery_date` (if not already set by vendor enricher)

**Acceptance criteria:** DC inventory days populated. Where both vendor and DC provide `next_delivery_date`, use the earlier date.

---

#### Task 3.7 — Build Financial Calculator

Create `src/enrichment/financial_calculator.py`. All calculations are deterministic — no AI involved. Compute:

```python
def calculate_est_lost_sales_value(
    units_on_hand: int,
    days_of_supply: float,
    retail_price: float,
    velocity_rank: int,
    total_sku_count: int
) -> float:
    """
    Estimate daily velocity from velocity rank using a power-law distribution.
    Units short = max(0, (lead_time_days - days_of_supply)) * daily_velocity
    Lost sales value = units_short * retail_price
    """

def calculate_promo_margin_at_risk(
    promo_active: bool,
    tpr_depth_pct: float,
    promo_end_date: str,
    exception_date: str,
    daily_velocity: float,
    retail_price: float,
    margin_pct: float
) -> float:
    """
    Remaining promo days = promo_end_date - exception_date
    Projected promo units = remaining_days * daily_velocity * 1.4 (promo lift factor, configurable)
    Margin at risk = projected_promo_units * retail_price * margin_pct * tpr_depth_pct
    Returns 0.0 if promo_active is False.
    """
```

**Acceptance criteria:** Unit tests for both functions with known inputs and expected outputs. Zero division handling for edge cases. Negative results floored at 0.0.

---

#### Task 3.8 — Build Regional Signal Enricher

Create `src/enrichment/regional_signal_enricher.py`. Checks for active regional disruption signals. Accepts two input modes:
- **File mode (default):** Reads `data/regional_signals.json` — a manually maintained file with region codes and active disruptions
- **API mode (optional):** Calls a configured weather or logistics API endpoint

Populates:
- `regional_disruption_flag`, `regional_disruption_description`

The `regional_signals.json` format:
```json
[
  {
    "region": "MIDWEST",
    "disruption_type": "WEATHER",
    "description": "Winter storm warning active through March 15",
    "active_from": "2026-03-13",
    "active_through": "2026-03-15"
  }
]
```

**Acceptance criteria:** Exceptions in affected regions correctly flagged. Exceptions in unaffected regions correctly unflagged.

---

### PHASE 4 — AI PROMPT SYSTEM

#### Task 4.1 — Build System Prompt Files

Create all prompt files in `prompts/`. These are loaded and composed at runtime by `prompt_composer.py`. Each file contains the text of one prompt block:

**`prompts/system_prompt.md`** — Persona block:
```
You are a senior supply chain planner with 15 years of retail replenishment experience. You understand that the most dangerous exceptions are rarely the ones with the highest variance numbers. You think in terms of business consequence — revenue at risk, promotional commitments, vendor reliability, competitive exposure, and customer service impact. You do not sort by magnitude. You sort by consequence.

You reason carefully and systematically. You explain your thinking clearly. You flag when you are uncertain and when data is missing. You never invent data you were not given.
```

**`prompts/triage_framework.md`** — Priority tier definitions (write in full):
- CRITICAL: criteria, indicators, examples
- HIGH: criteria, indicators, examples  
- MEDIUM: criteria, indicators, examples
- LOW: criteria, indicators, examples
- Include: compound risk escalation rules (e.g., MEDIUM exception becomes HIGH if part of a vendor pattern)

**`prompts/output_contract.md`** — Full JSON output schema that Claude must follow:
- Specify every field name, type, constraints (max word counts, enum values)
- State: "Return the full batch as a JSON array. Do not include markdown code fences. Do not include any text before or after the JSON array."
- Include: `pattern_analysis` object structure at the end of the batch

**`prompts/pattern_detection.md`** — Pattern detection directive:
- When to flag a pattern (threshold: 3+ exceptions, configurable)
- Pattern types: VENDOR, DC_LANE, CATEGORY, REGION, MACRO
- Pattern escalation rule: MEDIUM exceptions in a pattern → upgrade to HIGH
- pattern_analysis object schema

**`prompts/epistemic_honesty.md`** — Epistemic honesty rules:
- How to handle null enrichment fields
- Confidence level impact on priority
- How to communicate uncertainty in `planner_brief`
- What to put in `missing_data_flags`

**`prompts/phantom_inventory.md`** — Phantom inventory detection:
- Signals that suggest a phantom inventory scenario vs. true replenishment failure
- How to flag in `compounding_risks`
- Recommended action language for phantom scenarios

**`prompts/few_shot_library.json`** — 5 annotated examples:

```json
[
  {
    "id": "fs_001",
    "description": "High variance, zero business risk — should be LOW",
    "exception": { ... enriched exception object ... },
    "correct_output": { ... expected triage output ... },
    "reasoning": "Why this is LOW despite high variance percentage"
  },
  {
    "id": "fs_002", 
    "description": "Low variance, maximum risk — should be CRITICAL",
    "exception": { ... },
    "correct_output": { ... },
    "reasoning": "OOS + Tier 1 + active promo + competitor nearby"
  },
  {
    "id": "fs_003",
    "description": "Vendor pattern — MEDIUM upgraded to HIGH",
    "exception": { ... },
    "correct_output": { ... },
    "reasoning": "Individual exception is MEDIUM but shares vendor with 7 others"
  },
  {
    "id": "fs_004",
    "description": "Phantom inventory signal — DATA_INTEGRITY reclassification",
    "exception": { ... },
    "correct_output": { ... },
    "reasoning": "OOS but vendor fill rate 98%, DC has 45 days supply"
  },
  {
    "id": "fs_005",
    "description": "Low confidence output — missing critical enrichment data",
    "exception": { ... },
    "correct_output": { ... },
    "reasoning": "Correct CRITICAL flag with LOW confidence and missing_data_flags populated"
  }
]
```

**Acceptance criteria:** All 6 prompt files exist and contain well-structured, comprehensive content. Few-shot library contains 5 valid examples with complete enriched exception objects drawn from the sample data.

---

#### Task 4.2 — Build Prompt Composer

Create `src/agent/prompt_composer.py`. This module:

- Loads all prompt files at startup (cached in memory)
- Assembles the system prompt by concatenating blocks in order: persona → triage_framework → output_contract → pattern_detection → epistemic_honesty → phantom_inventory
- Inserts few-shot examples between triage_framework and output_contract
- Generates the user prompt for each batch: formats each enriched exception using the standardized per-exception template
- Provides a `compose_system_prompt() -> str` method and a `compose_user_prompt(batch: List[EnrichedExceptionSchema]) -> str` method

Per-exception template in user prompt (implement this exactly):
```
[EXCEPTION {n} of {total}]
exception_id: {exception_id}
item: {item_name} ({item_id}) — velocity rank {velocity_rank} in {category}
store: {store_id} ({store_name}) — Tier {store_tier}, ${weekly_store_sales_k}K/week
exception_type: {exception_type}
units_on_hand: {units_on_hand} | days_of_supply: {days_of_supply:.1f}
promo_active: {promo_active} | promo_type: {promo_type} | promo_end: {promo_end_date}
dc_inventory_days: {dc_inventory_days}
vendor_fill_rate_90d: {vendor_fill_rate_90d}% | open_po_inbound: {open_po_inbound} | next_delivery: {next_delivery_date}
lead_time_days: {lead_time_days}
competitor_proximity_miles: {competitor_proximity_miles} | competitor_event: {competitor_event}
perishable: {perishable}
day_of_week_demand_index: {day_of_week_demand_index}
est_lost_sales_value: ${est_lost_sales_value:.2f}
promo_margin_at_risk: ${promo_margin_at_risk:.2f}
regional_disruption: {regional_disruption_description}
enrichment_confidence: {enrichment_confidence}
missing_data_fields: {missing_data_fields}
---
```

All null values should render as `UNKNOWN` in the template, not `None` or `null`.

**Acceptance criteria:** Composed system prompt is valid text under 8000 tokens. User prompt for 30-record batch is valid text under 6000 tokens. Spot check: all 17 fields present in formatted exception block.

---

### PHASE 5 — CLAUDE REASONING ENGINE

#### Task 5.1 — Build Batch Processor

Create `src/agent/batch_processor.py`. This module:

- Accepts the full list of enriched exceptions
- Splits into batches of configured `batch_size` (default 30)
- For each batch:
  - Calls `prompt_composer.compose_user_prompt(batch)` 
  - Calls Anthropic Messages API with composed system + user prompts
  - Handles API response: extracts text, strips any markdown fences, parses JSON
  - Validates each exception result object against output schema
  - On JSON parse failure: logs the raw response, retries once with a clarification prompt ("Your previous response was not valid JSON. Return only the JSON array, no other text.")
  - On API failure: exponential backoff with 3 retries, then marks batch as FAILED and continues
  - Writes batch results to output store after each batch (partial results preserved)
- Returns: `List[TriageResult]` — one per input exception

API call pattern:
```python
response = anthropic_client.messages.create(
    model=config.agent.model,
    max_tokens=config.agent.max_tokens,
    system=system_prompt,
    messages=[{"role": "user", "content": user_prompt}]
)
```

If `reasoning_trace_enabled` is True in config, add to user prompt: "For each exception, include a 'reasoning_trace' field in your JSON output with your full chain of thought before reaching the priority decision. Maximum 150 words."

**Acceptance criteria:** Processes all 120 sample records across 4 batches. JSON parsing succeeds on all batches. Simulated API failure correctly triggers retry. Partial results are written even if one batch fails.

---

#### Task 5.2 — Build Pattern Analyzer (Two-Pass)

Create `src/agent/pattern_analyzer.py`. This runs as Pass 2 after all individual batches complete.

**Pass 2 — Macro Pattern Analysis:**

- Aggregates all triage results by: vendor_id, dc_id, category, region
- Identifies groups with 3+ exceptions (configurable threshold)
- Constructs a macro summary prompt:
  ```
  Here is a summary of today's exception run across all batches.
  Identify any systemic patterns that represent a single root cause 
  affecting multiple locations or items.
  
  BY VENDOR:
  {vendor_id}: {count} exceptions, {critical_count} CRITICAL, {high_count} HIGH
  ...
  
  BY REGION:
  {region}: {count} exceptions, {critical_count} CRITICAL
  ...
  
  BY CATEGORY:
  {category}: {count} exceptions
  ...
  ```
- Calls Claude API once with this summary
- Returns: `MacroPatternReport` with list of identified patterns

**Pattern escalation:** For each identified pattern, find all exceptions in that pattern group and upgrade any MEDIUM exceptions to HIGH. Log all escalations.

**Acceptance criteria:** Sample data's 12-exception vendor cluster is identified as a VENDOR pattern. At least one MEDIUM exception is escalated to HIGH due to pattern membership.

---

#### Task 5.3 — Build Phantom Inventory Webhook

Create `src/agent/phantom_webhook.py`. Requirements:

- Triggered when `compounding_risks` contains "POTENTIAL_PHANTOM_INVENTORY" in any triage result
- Makes HTTP POST to configured `phantom_webhook_url` with:
  ```json
  {
    "exception_id": "...",
    "item_id": "...",
    "store_id": "...",
    "trigger": "TRIAGE_AGENT_FLAG",
    "dc_inventory_days": ...,
    "vendor_fill_rate_90d": ...,
    "enrichment_confidence": "..."
  }
  ```
- If webhook is not configured or returns non-200, logs warning and continues (does not block triage output)
- If webhook returns a response body with field `phantom_confirmed: true`, updates the exception's `exception_type` to `DATA_INTEGRITY` and `priority` to appropriate level
- Timeout: 5 seconds maximum (must not block pipeline)

**Acceptance criteria:** Webhook fires for phantom inventory flagged exceptions. Non-configured webhook does not break pipeline. 5-second timeout enforced.

---

#### Task 5.4 — Build Triage Agent Orchestrator

Create `src/agent/triage_agent.py`. This is the main agentic loop that coordinates all agent components:

```python
class TriageAgent:
    def run(self, enriched_exceptions: List[EnrichedExceptionSchema]) -> TriageRunResult:
        # 1. Initialize run: generate run_id, log start time, record input count
        # 2. Pass 1: Batch processing via batch_processor.py
        #    - Process all batches
        #    - Collect all TriageResult objects
        # 3. Phantom webhook: fire for any phantom-flagged exceptions
        #    - Update exception types if phantom confirmed
        # 4. Pass 2: Macro pattern analysis via pattern_analyzer.py
        #    - Identify systemic patterns
        #    - Apply pattern escalations
        # 5. Assemble TriageRunResult:
        #    - All triage results (with escalations applied)
        #    - Pattern report
        #    - Run statistics (counts by priority tier, batch success rate, escalation count)
        # 6. Log run completion with summary statistics
        # Return TriageRunResult
```

**Acceptance criteria:** Full run on 120 sample records completes without errors. Run statistics accurately reflect counts by priority tier. Pattern escalations are reflected in final results.

---

### PHASE 6 — OUTPUT LAYER

#### Task 6.1 — Build Priority Router

Create `src/output/router.py`. Routes each triage result to the appropriate priority queue. In the file-based implementation, this means writing to four JSON files:

- `output/logs/CRITICAL_{run_date}.json`
- `output/logs/HIGH_{run_date}.json`
- `output/logs/MEDIUM_{run_date}.json`
- `output/logs/LOW_{run_date}.json`

Each file contains an array of full triage result objects, sorted by `est_lost_sales_value` descending within tier.

**Acceptance criteria:** Four queue files generated. Total records across all files equals input count. Records within each file sorted by financial value.

---

#### Task 6.2 — Build Alert Dispatcher

Create `src/output/alert_dispatcher.py`. Dispatches alerts for CRITICAL and HIGH exceptions. Requirements:

**Alert content** (same structure for all channels):
```
🚨 REPLENISHMENT TRIAGE ALERT — {priority}

Item: {item_name} | Store: {store_name} (Tier {store_tier})
Exception: {exception_type} | Days of Supply: {days_of_supply:.1f}
Financial Exposure: ${est_lost_sales_value:,.0f} lost sales | ${promo_margin_at_risk:,.0f} promo margin at risk

ACTION REQUIRED: {recommended_action}

{planner_brief}

Root Cause: {root_cause}
Confidence: {confidence}
{missing_data_note}

Run ID: {run_id} | Generated: {timestamp}
```

If `confidence == LOW`: append "⚠️ LOW CONFIDENCE — verify {missing_data_fields} before acting."

**SLA escalation:** Start a background timer (configurable, default 60 minutes). If no acknowledgment is received (webhook acknowledgment endpoint, configurable), dispatch a secondary alert to `secondary_escalation_contact` with the same content plus "ESCALATION: Unacknowledged after {n} minutes."

**Supported channels:** Email (SMTP), Slack webhook, Teams webhook, generic HTTP webhook. All channels are independently toggled in config.

**Acceptance criteria:** Alert fires for all CRITICAL results. Alert content matches template. Low confidence caveat appended for low-confidence results. Channel-disabled config correctly suppresses alerts.

---

#### Task 6.3 — Build Morning Briefing Generator

Create `src/output/briefing_generator.py`. Generates a markdown briefing document. Claude is called once to generate the narrative summary section — all other content is templated from structured data.

**Briefing structure:**

```markdown
# Replenishment Exception Triage — Morning Briefing
**Date:** {date} | **Run ID:** {run_id} | **Generated:** {timestamp}

---

## Today at a Glance
| Priority | Count | Total Financial Exposure |
|---|---|---|
| 🔴 CRITICAL | {n} | ${total_critical_value:,.0f} |
| 🟠 HIGH | {n} | ${total_high_value:,.0f} |
| 🟡 MEDIUM | {n} | ${total_medium_value:,.0f} |
| 🟢 LOW | {n} | ${total_low_value:,.0f} |
| **TOTAL** | **{n}** | **${total_value:,.0f}** |

---

## Systemic Patterns Detected
{for each pattern in pattern_report: pattern type, affected count, description, escalation count}

---

## Executive Summary
{CLAUDE-GENERATED: 3-4 sentence narrative summarizing the most important supply chain situation today. 
Input: top 5 CRITICAL exceptions + pattern report. 
Prompt: "Write a 3-4 sentence executive summary of today's most critical supply chain situation 
for a supply chain director. Mention the highest-risk exception by name, the financial exposure, 
and the most important systemic pattern if one exists. Be direct and specific. No jargon."}

---

## Top {n} Critical Exceptions

### 1. {item_name} — {store_name}
**Priority:** 🔴 CRITICAL | **Confidence:** {confidence}  
**Exception:** {exception_type} | **Days of Supply:** {days_of_supply:.1f}  
**Financial Exposure:** ${est_lost_sales_value:,.0f} lost sales | ${promo_margin_at_risk:,.0f} promo margin  
**Root Cause:** {root_cause}  
**Action Required:** {recommended_action}  

> {planner_brief}

{if missing_data_flags}: ⚠️ Missing data: {missing_data_fields}  
{if compounding_risks}: ⚠️ Compounding risks: {compounding_risks}

---

## Full Exception Queue
{summary table of all exceptions: rank, priority icon, item, store, exception type, days supply, financial exposure, action}

---

## Run Statistics
- Total exceptions processed: {n}
- Batches: {n} completed, {n} failed
- Pattern escalations applied: {n}
- Phantom inventory flags: {n}
- Pipeline completion time: {duration}
```

Save briefing to `output/briefings/briefing_{run_date}.md`.

**Acceptance criteria:** Briefing generated for sample run. Executive summary is Claude-generated (not templated). Financial totals match sum of individual exception values. All {n} critical exceptions appear in the top section.

---

#### Task 6.4 — Build Exception Logger

Create `src/output/exception_logger.py`. Writes a complete structured log of every exception and its triage result to a persistent store for backtesting.

Log record schema (one row per exception):
```
run_id, run_date, exception_id, item_id, store_id, exception_type,
exception_date, days_of_supply, promo_active, store_tier,
vendor_fill_rate_90d, dc_inventory_days, est_lost_sales_value,
promo_margin_at_risk, enrichment_confidence, missing_data_count,
ai_priority, ai_confidence, ai_root_cause, ai_recommended_action,
ai_financial_impact, ai_planner_brief, pattern_id, escalated_from,
phantom_flag, run_timestamp
```

Write to: `output/logs/exception_log.csv` (append mode, with header on first write).

**Acceptance criteria:** All 120 sample exceptions logged with full fields. Re-running does not duplicate records (idempotent on `run_id + exception_id`). CSV is valid and readable by pandas.

---

### PHASE 7 — MAIN ENTRY POINT & CLI

#### Task 7.1 — Build Main Orchestrator

Create `src/main.py`. This is the top-level orchestrator called by `scripts/run_triage.py`:

```python
def run_triage_pipeline(config_path: str = "config/config.yaml", run_date: str = None) -> TriageRunResult:
    """
    Full pipeline orchestration:
    1. Load config
    2. Layer 1: Ingest exceptions
    3. Layer 2: Enrich exceptions
    4. Layer 3: AI triage (agent loop, pattern analysis, phantom webhook)
    5. Layer 4: Route, alert, generate briefing, log
    6. Return TriageRunResult with summary statistics
    """
```

**Create `scripts/run_triage.py` CLI:**

Future-state CLI usage after Task 7.1 is implemented:

```bash
# python scripts/run_triage.py [OPTIONS]  # available after Task 7.1

Options:
  --config PATH          Path to config YAML (default: config/config.yaml)
  --date DATE            Run date YYYY-MM-DD (default: today)
  --dry-run              Run ingestion and enrichment but skip AI layer and alerts
  --no-alerts            Skip alert dispatch (useful for testing)
  --sample               Use sample data regardless of config adapter setting
  --verbose              Detailed logging to console
  --output-format FORMAT markdown | json | both (overrides config)
```

**Acceptance criteria:** `python scripts/run_triage.py --sample --dry-run` completes successfully and prints enrichment summary. `python scripts/run_triage.py --sample --no-alerts` completes full pipeline and generates briefing.

---

### PHASE 8 — BACKTESTING PIPELINE

#### Task 8.1 — Build Backtesting Script

Create `scripts/run_backtest.py`. At Week 4 and Week 8 after an exception date, this script:

1. Reads `exception_log.csv` for exceptions from the target date
2. For each logged exception, looks up actual outcome: did an OOS occur? Was stock restored?
3. Outcome source: a configured `outcome_query.sql` against your inventory/POS system, or a manually maintained `data/backtest_outcomes.csv`
4. Classifies each exception outcome as: RESOLVED | MISS | FALSE_ALARM
5. Calculates:
   - CRITICAL precision: CRITICAL exceptions that were RESOLVED or MISS (not FALSE_ALARM) / total CRITICAL
   - CRITICAL recall: CRITICAL exceptions that were RESOLVED / (RESOLVED + MISS)
   - False urgency rate: FALSE_ALARM / total CRITICAL + HIGH
   - Priority accuracy by tier
6. Generates backtesting report: `output/backtest/backtest_{original_date}_W{n}.md`

**Acceptance criteria:** Backtest runs against sample exception log with a manually provided outcomes CSV. Report generates with all five metrics calculated.

---

### PHASE 9 — TESTING

#### Task 9.1 — Unit Tests

Write unit tests in `tests/`. Minimum test coverage requirements:

**`tests/test_ingestion.py`:**
- CSV adapter reads sample file correctly
- Normalizer deduplicates correctly
- Quarantine fires for records missing required fields
- `batch_id` is consistent across all records in one run

**`tests/test_enrichment.py`:**
- Financial calculator: known inputs produce expected outputs for both functions
- Promo enricher: exception within promo window flagged correctly
- Promo enricher: exception outside promo window not flagged
- Enrichment confidence: HIGH when 0 nulls, MEDIUM when 1-2 nulls, LOW when 3+
- Regional signal enricher: active signal in matching region flags correctly

**`tests/test_agent.py`:**
- Prompt composer: composed system prompt under 8000 tokens
- Prompt composer: user prompt for 30-record batch under 6000 tokens
- Prompt composer: all 17 enrichment fields present in formatted exception
- Batch processor: JSON parse failure triggers one retry
- Pattern analyzer: 12-exception vendor group identified as pattern

**`tests/test_output.py`:**
- Router: total records across 4 queue files equals input count
- Exception logger: idempotent — re-running does not duplicate records
- Alert dispatcher: Low confidence caveat appended when confidence == LOW

**`tests/test_prompt_output.py`:**
- Load `tests/fixtures/enriched_exceptions_fixture.json` (5 curated exceptions including 1 CRITICAL, 1 phantom scenario, 1 vendor pattern member)
- Call Claude API (requires `ANTHROPIC_API_KEY` in env)
- Assert: CRITICAL exception receives CRITICAL priority
- Assert: Phantom scenario has "POTENTIAL_PHANTOM_INVENTORY" in compounding_risks
- Assert: All 5 outputs have `exception_id`, `priority`, `recommended_action`, `planner_brief`
- Assert: Pattern member from same vendor is identified in `pattern_analysis`

**Acceptance criteria:** All unit tests pass. `test_prompt_output.py` passes with a valid `ANTHROPIC_API_KEY`. Test run completes in under 60 seconds (excluding API calls).

---

### PHASE 10 — DOCUMENTATION

#### Task 10.1 — Write README.md

Comprehensive README with:
- Project description (3 paragraphs)
- ASCII architecture diagram
- Quick start (5 commands from clone to first triage run)
- Detailed setup: environment variables, config YAML walkthrough, sample data
- How to connect your real planning system (adapter configuration)
- How to run a triage: CLI options with examples
- How to read the morning briefing
- How to run backtesting
- How to add a new enrichment source (step-by-step)
- Prompt customization guide (how to edit prompt files for your organization)
- Troubleshooting: top 5 common issues with solutions
- Contributing guidelines
- License

**Acceptance criteria:** README renders cleanly on GitHub. All code snippets are tested and functional. Setup instructions work on a fresh clone with valid env vars.

---

## CODING STANDARDS

Apply these standards throughout the project:

**Python:**
- Python 3.9+ (3.11+ recommended)
- Type hints on all function signatures
- Dataclasses for all schema objects (`CanonicalException`, `EnrichedExceptionSchema`, `TriageResult`, `TriageRunResult`, `MacroPatternReport`)
- `loguru` for structured logging (log level, timestamp, module, message)
- `pydantic` for schema validation (both canonical and enriched schemas)
- `pytest` for all tests
- Docstrings on all public classes and methods (Google style)
- No bare `except:` clauses — all exceptions are typed

**Configuration:**
- Zero hardcoded values — all configurable via YAML or env vars
- All secrets via environment variables only — never in code or YAML committed to git
- `.env.example` documents every required env var with a description

**Error handling:**
- Custom exception hierarchy: `TriageAgentError` → `IngestionError`, `EnrichmentError`, `AgentError`, `OutputError`
- All errors logged at appropriate level before re-raising
- Pipeline continues on non-fatal errors (bad batch, failed webhook) — only halts on fatal errors (config missing, API key invalid)

**Claude API:**
- Always use the configured model string from config — never hardcode a model name
- Log token usage per API call (input tokens, output tokens)
- Log total token usage in run statistics

---

## REQUIREMENTS.TXT

```
anthropic>=0.40.0
pydantic>=2.0.0
pyyaml>=6.0
pandas>=2.0.0
loguru>=0.7.0
httpx>=0.27.0
SQLAlchemy>=2.0.0
python-dotenv>=1.0.0
pytest>=8.0.0
responses>=0.25.0
click>=8.0.0
jsonpath-ng>=1.6.0
```

---

## ENVIRONMENT VARIABLES (.env.example)

```bash
# Required
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Required for API adapter mode (optional if using CSV or SQL)
EXCEPTION_API_ENDPOINT=https://your-planning-system.com/api/exceptions
EXCEPTION_API_KEY=your_api_key

# Required for SQL adapter mode (optional if using CSV or API)
DB_CONNECTION_STRING=postgresql://user:password@host:5432/dbname

# Required for email alerts (optional if alerts disabled)
SMTP_HOST=smtp.yourdomain.com
ALERT_FROM_EMAIL=triage-agent@yourdomain.com
PLANNER_EMAIL=planner@yourdomain.com
CATEGORY_MANAGER_EMAIL=category.manager@yourdomain.com

# Optional: Slack/Teams alerting
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
TEAMS_WEBHOOK_URL=https://outlook.office.com/webhook/...

# Optional: Phantom Inventory Agent integration
PHANTOM_WEBHOOK_URL=http://localhost:8001/api/verify
```

---

## DEMO SCRIPT (Week 5 Milestone)

The following demo can be run before any production pipeline is connected. It uses sample data to produce a compelling AI triage output for leadership review:

```bash
# 1. Clone and setup
git clone https://github.com/m-kunta/replenishment-triage-ai
cd replenishment-triage-ai
pip install -r requirements.txt
cp .env.example .env
# Edit .env: add ANTHROPIC_API_KEY

# 2. Generate sample data
python scripts/generate_sample_data.py

# 3. Run full triage on sample data (no alerts) — after Task 7.1 implementation
# python scripts/run_triage.py --sample --no-alerts --verbose

# 4. View morning briefing
cat output/briefings/briefing_$(date +%Y-%m-%d).md

# 5. View CRITICAL queue
cat output/logs/CRITICAL_$(date +%Y-%m-%d).json | python -m json.tool
```

**Expected demo output:** 
- 3–5 CRITICAL exceptions (including the Pepsi-promo-Tier1-competitor scenario)
- 1 vendor pattern flag covering 12 banana exceptions  
- 1 phantom inventory flag
- Morning briefing with Claude-generated executive summary
- Total financial exposure exceeding $50,000 in the sample dataset

---

## FUTURE PHASES (Out of Scope for Initial Build)

- Real-time webhook trigger mode (replace daily batch)
- Web UI dashboard with exception queue visualization
- Planner feedback capture form (override reason collection)
- Active learning pipeline (promote override reasons to few-shot library)
- New Item Ramp Forecaster agent integration
- Demand Signal Fusion Engine agent integration
- Multi-tenant / SaaS deployment mode
- Mobile push notifications

---

*Project Scope Document: `Replenishment_Exception_Triage_Agent_Scope.docx`*  
*Repository: `https://github.com/m-kunta/replenishment-triage-ai`*  
*License: MIT © 2026 Mohith Kunta*
