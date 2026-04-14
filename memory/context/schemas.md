# Schema Quick Reference

All schemas defined in `src/models.py`.

## CanonicalException (Layer 1 output)
Key fields: `exception_id`, `item_id`, `item_name`, `store_id`, `store_name`, `exception_type` (enum), `exception_date`, `units_on_hand`, `days_of_supply`, `variance_pct`, `source_system`, `batch_id`, `ingested_at`

## EnrichedExceptionSchema (Layer 2 output → Layer 3 input)
All canonical fields plus:
- Store: `store_tier`, `weekly_store_sales_k`, `region`, `competitor_proximity_miles`, `competitor_event`
- Item: `velocity_rank`, `category`, `subcategory`, `retail_price`, `margin_pct`, `perishable`, `vendor_id`
- Promo: `promo_active`, `promo_type`, `promo_end_date`, `tpr_depth_pct`
- Vendor: `vendor_fill_rate_90d`, `open_po_inbound`
- DC: `dc_inventory_days`, `next_delivery_date`, `lead_time_days`
- Regional: `regional_disruption_flag`, `regional_disruption_description`
- Computed: `est_lost_sales_value`, `promo_margin_at_risk`, `day_of_week_demand_index`
- Meta: `missing_data_fields: List[str]`, `enrichment_confidence: EnrichmentConfidence`
- Model config: `extra="forbid"`

## TriageResult (Layer 3 output)
Key fields: `exception_id`, `priority`, `confidence`, `root_cause` (≤30 words), `recommended_action` (≤25 words), `financial_impact_statement` (≤20 words), `planner_brief` (≤75 words), `compounding_risks: List[str]`, `missing_data_flags`, `pattern_id`, `escalated_from`, `phantom_flag`, `reasoning_trace`
Plus carried-forward fields: `item_id`, `item_name`, `store_id`, `store_name`, `exception_type`, `days_of_supply`, `store_tier`, `promo_active`, `est_lost_sales_value`, `promo_margin_at_risk`, `dc_inventory_days`, `vendor_fill_rate_90d`
- Model config: `extra="ignore"` (LLM may return extra fields)
- **Mutable by design**: phantom webhook and pattern analyzer mutate after initial AI assignment

## PatternDetail
Fields: `pattern_id`, `pattern_type` (enum), `group_key`, `affected_count`, `critical_count`, `high_count`, `description`, `escalation_count`, `affected_exception_ids: List[str]`

## MacroPatternReport
Fields: `patterns: List[PatternDetail]`, `total_patterns`, `total_escalations`

## RunStatistics
Fields: `total_exceptions`, `critical_count`, `high_count`, `medium_count`, `low_count`, `batches_completed`, `batches_failed`, `pattern_escalations`, `phantom_flags`, `total_input_tokens`, `total_output_tokens`, `pipeline_duration_seconds`

## TriageRunResult (Layer 3 final output, Layer 4 input)
Fields: `run_id` (RUN-{8hex}), `run_date`, `triage_results`, `pattern_report`, `statistics`, `run_timestamp`

## AppConfig (config_loader.py)
Sections: `ingestion`, `enrichment`, `agent`, `store_tiers`, `priority_rules`, `alerting`, `output`, `backtest`
- `AgentConfig`: provider, model, max_tokens (4000), batch_size (30), retry_attempts (3), reasoning_trace_enabled, phantom_webhook_enabled, pattern_threshold (3)
- All `${ENV_VAR}` references are resolved from environment at load time
