# Layer 2 AI Handoff Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish Layer 2 so it hands a stable, validated, spec-aligned `EnrichedExceptionSchema` contract to the future AI layer.

**Architecture:** Keep the current Layer 2 shape intact: `DataLoader` loads reference data, `EnrichmentEngine` assembles enriched records, and Pydantic models remain the runtime contract. Close the remaining gap by adding the missing spec field (`day_of_week_demand_index`), creating a JSON schema artifact for enriched records, tightening validation rules so downstream code gets a stricter contract, and then updating the README to describe the real project state without contradictions.

**Tech Stack:** Python 3.9+, Pydantic v2, pytest, JSON Schema artifacts, Markdown docs

---

## File Map

**Create**
- `data/schema/enriched_exception_schema.json`
- `docs/superpowers/plans/2026-03-29-layer-2-ai-handoff-contract.md`

**Modify**
- `src/models.py`
- `src/enrichment/engine.py`
- `src/utils/validators.py`
- `tests/test_enrichment.py`
- `tests/test_validators.py`
- `README.md`

**Why these files**
- `src/models.py`: tighten the runtime Layer 2 contract so unexpected fields are rejected and enumerated fields use stronger types.
- `src/enrichment/engine.py`: populate `day_of_week_demand_index` deterministically and include it in missing-field/confidence handling.
- `src/utils/validators.py`: expose enriched-schema JSON loading and validation at parity with canonical validation.
- `data/schema/enriched_exception_schema.json`: provide an explicit handoff artifact for Layer 2 → Layer 3.
- `tests/test_enrichment.py`: prove the engine emits the new field and still enriches the full sample set.
- `tests/test_validators.py`: prove the enriched contract is strict and the schema artifact is loadable.
- `README.md`: reflect actual status, test counts, and current implemented scope accurately.

---

### Task 1: Add the Missing Layer 2 Field to the Runtime Contract

**Files:**
- Modify: `src/models.py`
- Modify: `src/enrichment/engine.py`
- Test: `tests/test_enrichment.py`

- [ ] **Step 1: Write the failing engine tests for `day_of_week_demand_index`**

Add these tests to `tests/test_enrichment.py` inside `TestEnrichmentEngine`:

```python
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
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run:

```bash
./.venv/bin/pytest tests/test_enrichment.py::TestEnrichmentEngine::test_day_of_week_demand_index_populated_from_exception_date tests/test_enrichment.py::TestEnrichmentEngine::test_day_of_week_demand_index_included_in_full_sample_enrichment -v
```

Expected: FAIL because `day_of_week_demand_index` is currently unset by `EnrichmentEngine`.

- [ ] **Step 3: Write the minimal implementation in `src/enrichment/engine.py`**

Add a weekday mapping near the tracked field constants:

```python
_DAY_OF_WEEK_DEMAND_INDEX = {
    0: 0.93,  # Monday
    1: 0.98,  # Tuesday
    2: 1.05,  # Wednesday
    3: 1.08,  # Thursday
    4: 1.15,  # Friday
    5: 1.22,  # Saturday
    6: 1.10,  # Sunday
}
```

Update the tracked field list:

```python
_TRACKED_ENRICHMENT_FIELDS: List[str] = [
    "store_tier",
    "weekly_store_sales_k",
    "region",
    "velocity_rank",
    "category",
    "retail_price",
    "margin_pct",
    "perishable",
    "vendor_id",
    "vendor_fill_rate_90d",
    "open_po_inbound",
    "dc_inventory_days",
    "promo_active",
    "regional_disruption_flag",
    "lead_time_days",
    "day_of_week_demand_index",
]
```

Add a helper method:

```python
    def _compute_day_of_week_demand_index(self, exception_date: date) -> float:
        """Return a deterministic day-of-week demand index from the exception date."""
        return _DAY_OF_WEEK_DEMAND_INDEX[exception_date.weekday()]
```

Populate the field inside `_enrich_one`:

```python
        enriched_fields: Dict[str, Any] = {
            "store_tier": store.get("tier"),
            "weekly_store_sales_k": store.get("weekly_sales_k"),
            "region": store.get("region"),
            "competitor_proximity_miles": store.get("competitor_proximity_miles"),
            "competitor_event": store.get("competitor_event"),
            "velocity_rank": item.get("velocity_rank"),
            "category": item.get("category"),
            "subcategory": item.get("subcategory"),
            "retail_price": item.get("retail_price"),
            "margin_pct": item.get("margin_pct"),
            "perishable": item.get("perishable"),
            "vendor_id": vendor_id,
            "vendor_fill_rate_90d": vendor.get("vendor_fill_rate_90d"),
            "open_po_inbound": vendor.get("open_po_inbound"),
            "dc_inventory_days": dc.get("dc_inventory_days"),
            "next_delivery_date": dc.get("next_delivery_date"),
            "lead_time_days": dc.get("lead_time_days"),
            "promo_active": promo.get("promo_active", False),
            "promo_type": promo.get("promo_type"),
            "promo_end_date": promo.get("promo_end_date"),
            "tpr_depth_pct": promo.get("tpr_depth_pct"),
            "day_of_week_demand_index": self._compute_day_of_week_demand_index(
                exc.exception_date
            ),
            "regional_disruption_flag": regional.get("regional_disruption_flag"),
            "regional_disruption_description": regional.get("regional_disruption_description"),
            "est_lost_sales_value": est_lost_sales,
            "promo_margin_at_risk": promo_margin,
        }
```

- [ ] **Step 4: Tighten the model type in `src/models.py`**

Update `promo_type` to use the enum and disallow extra fields on the enriched model:

```python
from pydantic import BaseModel, Field, ConfigDict
```

```python
class EnrichedExceptionSchema(BaseModel):
    """Schema for enriched exception records, input to the AI triage layer."""

    model_config = ConfigDict(extra="forbid")
```

```python
    promo_type: Optional[PromoType] = Field(
        default=None,
        description="Promo type: TPR, FEATURE, DISPLAY, BOTH, NONE",
    )
```

Add the same `extra="forbid"` setting to `CanonicalException`:

```python
class CanonicalException(BaseModel):
    """Schema for normalized exception records output by the ingestion layer."""

    model_config = ConfigDict(extra="forbid")
```

- [ ] **Step 5: Run the focused tests to verify they pass**

Run:

```bash
./.venv/bin/pytest tests/test_enrichment.py::TestEnrichmentEngine::test_day_of_week_demand_index_populated_from_exception_date tests/test_enrichment.py::TestEnrichmentEngine::test_day_of_week_demand_index_included_in_full_sample_enrichment -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/models.py src/enrichment/engine.py tests/test_enrichment.py
git commit -m "feat: complete layer 2 handoff field coverage"
```

---

### Task 2: Add an Explicit Enriched JSON Schema and Tighten Validator Coverage

**Files:**
- Create: `data/schema/enriched_exception_schema.json`
- Modify: `src/utils/validators.py`
- Test: `tests/test_validators.py`

- [ ] **Step 1: Write the failing validator tests**

Add these tests to `tests/test_validators.py`:

```python
    def test_loads_enriched_exception_schema(self):
        schema = load_json_schema("enriched_exception_schema.json")
        assert isinstance(schema, dict)
        assert schema.get("title") == "EnrichedExceptionSchema"
        assert "properties" in schema

    def test_enriched_schema_requires_day_of_week_demand_index_property(self):
        schema = load_json_schema("enriched_exception_schema.json")
        assert "day_of_week_demand_index" in schema["properties"]

    def test_validate_enriched_exception_rejects_extra_fields(self):
        with pytest.raises(EnrichmentError, match="validation failed"):
            validate_enriched_exception(_enriched_dict(unexpected_field="boom"))

    def test_validate_enriched_exception_accepts_enum_promo_type(self):
        result = validate_enriched_exception(_enriched_dict(promo_type="TPR"))
        assert result.promo_type.value == "TPR"
```

- [ ] **Step 2: Run the validator tests to verify they fail**

Run:

```bash
./.venv/bin/pytest tests/test_validators.py::TestLoadJsonSchema::test_loads_enriched_exception_schema tests/test_validators.py::TestLoadJsonSchema::test_enriched_schema_requires_day_of_week_demand_index_property tests/test_validators.py::TestValidateEnrichedException::test_validate_enriched_exception_rejects_extra_fields tests/test_validators.py::TestValidateEnrichedException::test_validate_enriched_exception_accepts_enum_promo_type -v
```

Expected: FAIL because the enriched schema artifact does not exist yet and the current model allows extra fields.

- [ ] **Step 3: Create `data/schema/enriched_exception_schema.json`**

Create this file:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "EnrichedExceptionSchema",
  "description": "Schema for enriched exception records between Layer 2 (Enrichment) and Layer 3 (AI triage).",
  "type": "object",
  "required": [
    "exception_id",
    "item_id",
    "item_name",
    "store_id",
    "store_name",
    "exception_type",
    "exception_date",
    "units_on_hand",
    "days_of_supply",
    "source_system",
    "batch_id",
    "ingested_at",
    "missing_data_fields",
    "enrichment_confidence"
  ],
  "properties": {
    "exception_id": { "type": "string" },
    "item_id": { "type": "string" },
    "item_name": { "type": "string" },
    "store_id": { "type": "string" },
    "store_name": { "type": "string" },
    "exception_type": {
      "type": "string",
      "enum": ["OOS", "LOW_STOCK", "FORECAST_VARIANCE", "ORDER_FAILURE", "VENDOR_LATE", "DATA_INTEGRITY"]
    },
    "exception_date": { "type": "string", "format": "date" },
    "units_on_hand": { "type": "integer" },
    "days_of_supply": { "type": "number" },
    "variance_pct": { "type": ["number", "null"] },
    "source_system": { "type": "string" },
    "batch_id": { "type": "string" },
    "ingested_at": { "type": "string", "format": "date-time" },
    "velocity_rank": { "type": ["integer", "null"] },
    "category": { "type": ["string", "null"] },
    "subcategory": { "type": ["string", "null"] },
    "retail_price": { "type": ["number", "null"] },
    "margin_pct": { "type": ["number", "null"] },
    "store_tier": { "type": ["integer", "null"] },
    "weekly_store_sales_k": { "type": ["number", "null"] },
    "region": { "type": ["string", "null"] },
    "promo_active": { "type": ["boolean", "null"] },
    "promo_type": {
      "type": ["string", "null"],
      "enum": ["TPR", "FEATURE", "DISPLAY", "BOTH", "NONE", null]
    },
    "promo_end_date": { "type": ["string", "null"], "format": "date" },
    "tpr_depth_pct": { "type": ["number", "null"] },
    "dc_inventory_days": { "type": ["number", "null"] },
    "vendor_id": { "type": ["string", "null"] },
    "vendor_fill_rate_90d": { "type": ["number", "null"] },
    "open_po_inbound": { "type": ["boolean", "null"] },
    "next_delivery_date": { "type": ["string", "null"], "format": "date" },
    "lead_time_days": { "type": ["integer", "null"] },
    "competitor_proximity_miles": { "type": ["number", "null"] },
    "competitor_event": { "type": ["string", "null"] },
    "perishable": { "type": ["boolean", "null"] },
    "day_of_week_demand_index": { "type": ["number", "null"] },
    "est_lost_sales_value": { "type": ["number", "null"] },
    "promo_margin_at_risk": { "type": ["number", "null"] },
    "regional_disruption_flag": { "type": ["boolean", "null"] },
    "regional_disruption_description": { "type": ["string", "null"] },
    "missing_data_fields": {
      "type": "array",
      "items": { "type": "string" }
    },
    "enrichment_confidence": {
      "type": "string",
      "enum": ["HIGH", "MEDIUM", "LOW"]
    }
  },
  "additionalProperties": false
}
```

- [ ] **Step 4: Update `src/utils/validators.py` with parity helpers**

Keep the existing API and add an enriched batch validator:

```python
def validate_enriched_batch(
    records: List[Dict[str, Any]]
) -> tuple[List[EnrichedExceptionSchema], List[Dict[str, Any]]]:
    """Validate a batch of records against the EnrichedExceptionSchema."""
    valid = []
    invalid = []
    for i, record in enumerate(records):
        try:
            valid.append(EnrichedExceptionSchema.model_validate(record))
        except ValidationError as e:
            invalid.append(
                {
                    "row_index": i,
                    "record": record,
                    "errors": e.errors(),
                }
            )
    return valid, invalid
```

Update the imports accordingly:

```python
from src.models import CanonicalException, EnrichedExceptionSchema
```

```python
from typing import Any, Dict, List
```

- [ ] **Step 5: Add one batch-level validator test**

Add this test to `tests/test_validators.py`:

```python
class TestValidateEnrichedBatch:
    def test_mixed_valid_and_invalid_records(self):
        from src.utils.validators import validate_enriched_batch

        valid, invalid = validate_enriched_batch(
            [
                _enriched_dict(),
                _enriched_dict(unexpected_field="boom"),
            ]
        )

        assert len(valid) == 1
        assert len(invalid) == 1
        assert invalid[0]["row_index"] == 1
```

- [ ] **Step 6: Run the validator suite**

Run:

```bash
./.venv/bin/pytest tests/test_validators.py -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add data/schema/enriched_exception_schema.json src/utils/validators.py tests/test_validators.py src/models.py
git commit -m "feat: add explicit enriched schema contract"
```

---

### Task 3: Reconcile README With the Real Layer 2 Status

**Files:**
- Modify: `README.md`
- Test: `tests/test_enrichment.py`
- Test: `tests/test_validators.py`

- [ ] **Step 1: Write the documentation assertions as a checklist in the PR description or local notes**

Use this checklist while editing `README.md`:

```text
- Remove the contradiction that says Layer 2 is both complete and partial
- Update test counts from stale values to the actual suite count
- Describe Layer 2 as a stable handoff contract, not the full multi-phase project being complete
- Keep Layer 3 and Layer 4 marked as not started
- Update verification commands to use the repo virtualenv
```

- [ ] **Step 2: Update the README status sections**

Make these concrete edits:

Replace the opening status callout with:

```md
> This project is actively under development. Layer 1 is complete, and Layer 2 now provides a stable enriched-data handoff contract for the future AI layer. Layers 3-4 are not implemented yet.
```

Replace the “Run Tests” snippet with:

```bash
./.venv/bin/pytest tests/ -v
# current suite should pass locally
```

Replace the “Project Status” Layer 2 row with:

```md
| **Layer 2 — Enrichment** | ✅ Stable handoff contract | `DataLoader` + `EnrichmentEngine` emit validated enriched exceptions for Layer 3 |
```

Replace the contradictory “Current Capabilities vs Planned” row:

```md
| Full enrichment engine output | ✅ Stable Layer 2 contract | Current engine joins the implemented sources, computes financials, emits confidence/missing-field metadata, and includes `day_of_week_demand_index` for AI handoff |
```

Update the testing references so they do not claim “16 tests” or “31 tests” if the suite has moved on.

- [ ] **Step 3: Run the tests named in the README**

Run:

```bash
./.venv/bin/pytest tests/test_enrichment.py tests/test_validators.py -v
```

Expected: PASS

- [ ] **Step 4: Render-check the README locally**

Run:

```bash
sed -n '1,260p' README.md
```

Expected: the status messaging reads consistently from top to bottom, with no claim that Layer 2 is both complete and partial.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: align readme with layer 2 status"
```

---

### Task 4: Run Full Regression for the Layer 2 Handoff Milestone

**Files:**
- Modify: none
- Test: `tests/test_enrichment.py`
- Test: `tests/test_validators.py`
- Test: `tests/test_ingestion.py`

- [ ] **Step 1: Run the full test suite**

Run:

```bash
./.venv/bin/pytest tests/ -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 2: Spot-check the enriched contract from code**

Run:

```bash
./.venv/bin/pytest tests/test_enrichment.py::TestEnrichmentEngine::test_day_of_week_demand_index_populated_from_exception_date tests/test_validators.py::TestValidateEnrichedException::test_validate_enriched_exception_rejects_extra_fields -v
```

Expected: PASS

- [ ] **Step 3: Verify the schema artifacts exist**

Run:

```bash
ls data/schema
```

Expected:

```text
canonical_exception_schema.json
enriched_exception_schema.json
```

- [ ] **Step 4: Commit the verification checkpoint if needed**

```bash
git status --short
```

Expected: clean working tree, or only intentional uncommitted follow-up work.

---

## Self-Review

**Spec coverage**
- The missing spec field from the current implementation, `day_of_week_demand_index`, is covered in Task 1.
- The explicit enriched handoff artifact requested by “tighten the enriched schema contract” is covered in Task 2.
- README status reconciliation is covered in Task 3.
- Full regression and milestone verification are covered in Task 4.

**Placeholder scan**
- No `TODO`, `TBD`, or “implement later” placeholders remain.
- Every code-changing task includes concrete snippets and exact commands.

**Type consistency**
- The plan consistently uses `EnrichedExceptionSchema`, `PromoType`, `validate_enriched_exception`, and `validate_enriched_batch`.
- The new field name is consistently `day_of_week_demand_index` across model, engine, tests, schema artifact, and docs.

