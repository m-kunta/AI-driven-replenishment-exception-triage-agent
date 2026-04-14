# Glossary

Domain terminology, acronyms, and internal shorthand for the Replenishment Exception Triage Agent.

## Exception Types
| Term | Meaning |
|------|---------|
| OOS | Out Of Stock — on-hand units are zero |
| LOW_STOCK | On-hand above zero but below safety-stock threshold |
| FORECAST_VARIANCE | Actual sales deviate materially from forecast |
| ORDER_FAILURE | Replenishment order failed to generate or transmit |
| VENDOR_LATE | Expected vendor shipment has not arrived by due date |
| DATA_INTEGRITY | Record-level data quality issue (phantom inventory, etc.) |

## Priority Levels
| Term | Meaning |
|------|---------|
| CRITICAL | Immediate action within hours; high financial impact or customer service failure |
| HIGH | Same-day resolution required; significant but manageable risk |
| MEDIUM | Same-week resolution; important but not urgent |
| LOW | Informational only; no immediate action needed |

## Promo Types
| Term | Meaning |
|------|---------|
| TPR | Temporary Price Reduction — shelf price is discounted |
| FEATURE | Item featured in weekly circular or end-cap display |
| DISPLAY | Secondary off-shelf placement (aisle cap, etc.) |
| BOTH | TPR combined with a circular feature in same week |

## Enrichment & Confidence
| Term | Meaning |
|------|---------|
| enrichment_confidence | HIGH/MEDIUM/LOW — how complete the enriched record is |
| missing_data_fields | List of tracked enrichment fields that resolved to None |
| enrichment_failed | Sentinel value — the entire enrichment pipeline crashed for that record |
| null_threshold_low | ≥3 null tracked fields → LOW confidence (configurable) |
| null_threshold_medium | 1–2 null tracked fields → MEDIUM confidence |

## Pattern Types
| Term | Meaning |
|------|---------|
| VENDOR | Multiple exceptions from same underperforming vendor |
| DC_LANE | Multiple exceptions from same DC-to-store lane (not yet supported — no DC ID field) |
| CATEGORY | Multiple exceptions clustered in a single product category |
| REGION | Multiple exceptions concentrated in a geographic region |
| MACRO | Broad cross-cutting pattern spanning multiple dimensions |
| pattern_threshold | Minimum exceptions needed to flag a pattern (default: 3) |

## Compounding Risk Flags
| Term | Meaning |
|------|---------|
| POTENTIAL_PHANTOM_INVENTORY | OOS/LOW_STOCK + vendor fill rate >90% + DC inventory >14 days |
| PROMO_COMMITMENT | Active promotional obligation at risk |
| COMPETITOR_EXPOSURE | Competitor within 2 miles with active competitor event |
| VENDOR_RELIABILITY | Vendor fill rate signals systemic reliability problem |
| PERISHABLE_URGENCY | Perishable item with critically low supply |
| DATA_INTEGRITY_RISK | Data quality issue affecting triage confidence |

## Architecture Shorthand
| Term | Meaning |
|------|---------|
| Layer 1 | Ingestion & Normalization (CSV adapter + normalizer) |
| Layer 2 | Context Enrichment (DataLoader + EnrichmentEngine) |
| Layer 3 | Claude Reasoning Engine (batch_processor, pattern_analyzer, phantom_webhook, triage_agent) |
| Layer 4 | Routing, Alerting & Output — COMPLETE |
| canonical | Normalized exception record output from Layer 1 (CanonicalException) |
| enriched | Enriched exception record from Layer 2 (EnrichedExceptionSchema) |
| triage result | AI output per exception from Layer 3 (TriageResult) |
| run result | Top-level output of one full pipeline run (TriageRunResult) |
| phantom webhook | HTTP POST fired when POTENTIAL_PHANTOM_INVENTORY is flagged |
| the pipeline | The full 4-layer triage system |
| briefing | Morning briefing document for planners (Layer 4 output) |
| backtest | Outcome-check pipeline to validate triage quality retrospectively |

## Store Tiers
| Term | Meaning |
|------|---------|
| Tier 1 | Highest-volume stores (≥$1.5M/week) |
| Tier 2 | High-volume stores ($800K–$1.5M/week) |
| Tier 3 | Mid-volume stores ($300K–$800K/week) |
| Tier 4 | Lower-volume stores (<$300K/week) |

## Key IDs in Sample Data
| ID | What |
|----|------|
| STR-001 | Tier 1 flagship store — used in CRITICAL scenario |
| STR-005 | Store with phantom inventory scenario |
| VND-400 | CleanHome Distributors — vendor with pattern (fill rate 72%, 14 exceptions) |
