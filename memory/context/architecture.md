# Architecture Deep Reference

## Data Flow (end to end)

```
CSV / API / SQL
      ↓
[Layer 1] CSVAdapter / APIAdapter / SQLAdapter
          → Normalizer (dedup, quarantine, type coerce)
          → List[CanonicalException]
      ↓
[Layer 2] DataLoader (loads 6 reference CSVs + regional_signals.json)
          → EnrichmentEngine.enrich()
          → List[EnrichedExceptionSchema]
      ↓
[Layer 3] TriageAgent.run()
          → BatchProcessor (chunks of 30 → LLM → List[TriageResult])
          → PhantomWebhook (fires on POTENTIAL_PHANTOM_INVENTORY)
          → PatternAnalyzer (aggregates vendor/region/category → LLM → escalations)
          → TriageRunResult
      ↓
[Layer 4] COMPLETE
          → Router → alert_dispatcher + briefing_generator + exception_logger
```

## Key Design Decisions

### Consequence-First Triage
The fundamental shift: exceptions are sorted by **business consequence**, not by variance magnitude. A 5% stock shortfall at a Tier 1 store during a TPR promo outranks a 45% forecast variance at a Tier 4 store.

### TriageResult is Mutable by Design
After the LLM assigns initial priority, two post-processing passes mutate the same `TriageResult` objects in place:
1. **Phantom webhook**: may change `exception_type` → `DATA_INTEGRITY`, set `phantom_flag=True`, override `priority` to MEDIUM
2. **Pattern analyzer**: may set `pattern_id`, change `priority` MEDIUM→HIGH, set `escalated_from`

### DC_LANE Pattern — Known Gap
`PatternType.DC_LANE` exists in the enum but is NOT functional. The enrichment layer does not provide a DC identifier field on `EnrichedExceptionSchema`. LLM-hallucinated DC_LANE patterns are silently dropped (0 affected exceptions guard). Fix requires adding a `dc_id` field to the enrichment layer.

### Enrichment Confidence Scoring
15 tracked fields are null-counted after all 6 reference joins:
- 0 nulls → HIGH
- 1–2 nulls → MEDIUM  
- ≥3 nulls → LOW
`"enrichment_failed"` sentinel indicates the enrichment engine itself crashed for that record.

### Financial Impact Computation (Layer 2)
- **No promo**: `retail_price × max(0, min(7, 7 - days_of_supply))`
- **On promo**: `retail_price × (1 - tpr_depth_pct) × days_exposure × 1.4` (promo lift factor)
- `promo_margin_at_risk = est_lost_sales_value × margin_pct` (only if promo_active)

### Prompt Assembly Order
`PromptComposer.compose_system_prompt()` joins 7 blocks with `\n\n---\n\n`:
1. `system_prompt.md` (persona)
2. `triage_framework.md` (priority rules)
3. `few_shot_library.json` (5 annotated examples)
4. `output_contract.md` (JSON schema)
5. `pattern_detection.md`
6. `epistemic_honesty.md`
7. `phantom_inventory.md`

### Batch Response Parsing
The LLM returns a JSON array where the LAST element has `_type: "pattern_analysis"`. The `BatchProcessor._parse_response()` separates this element from `TriageResult` objects. If the LLM wraps in ``` fences, they are stripped.

### Provider Abstraction
`get_provider(config.agent)` returns one of: `ClaudeProvider`, `OpenAIProvider`, `GeminiProvider`, `OllamaProvider`. All share the `LLMProvider.complete(system, user) → LLMResponse` interface. Switch via `config.yaml agent.provider`.

## Dedup Key (Normalizer)
`(item_id, store_id, exception_type, exception_date)` — duplicates within a batch are quarantined.

## Quarantine
Invalid records written to: `output/logs/quarantine_{date}_{batch_id}.json`

## Day-of-Week Demand Index
Hard-coded multipliers in `enrichment/engine.py`:
Mon=0.93, Tue=0.98, Wed=1.05, Thu=1.08, Fri=1.15, Sat=1.22, Sun=1.10
