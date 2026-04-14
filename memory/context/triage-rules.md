# Triage Priority Rules

Quick reference for CRITICAL/HIGH/MEDIUM/LOW assignment logic from `prompts/triage_framework.md`.

## CRITICAL (any one sufficient)
- OOS or <1.5 days of supply at Tier 1 store + active promo (TPR, FEATURE, BOTH)
- Perishable item with <1.0 days of supply (any store tier)
- OOS at Tier 1 or Tier 2 store + competitor within 2 miles + competitor event active
- Vendor pattern with 5+ exceptions from same vendor, fill rate <80%
- ORDER_FAILURE at Tier 1 store + promo active + no inbound PO
- **Compound escalation**: HIGH exception where ALL THREE true → perishable + promo active + Tier 1 store

## HIGH (any one sufficient)
- <3.0 days of supply at Tier 1 or Tier 2 store
- OOS at Tier 3 store + active TPR
- VENDOR_LATE at Tier 1/2 store + open promo + no alternative inbound
- Part of confirmed VENDOR, DC_LANE, or CATEGORY pattern (even if individually MEDIUM)
- OOS + no inbound PO + lead time >7 days

## MEDIUM
- OOS or LOW_STOCK at Tier 3 store, no active promo
- FORECAST_VARIANCE >25% at Tier 1/2 store, no stock risk
- VENDOR_LATE at Tier 3/4 store with adequate DC inventory
- 3–7 days of supply + no compounding risk factors

## LOW
- FORECAST_VARIANCE at Tier 4 store (any %)
- OOS or LOW_STOCK at Tier 4 store + non-perishable + no promo + DC has adequate inventory
- enrichment_confidence = LOW + no CRITICAL signals visible
- Normal replenishment cycle variation, no downstream risk

## Phantom Inventory Flag (doesn't change priority alone)
Add `POTENTIAL_PHANTOM_INVENTORY` to `compounding_risks` when ALL three:
1. Exception type is OOS or LOW_STOCK
2. `vendor_fill_rate_90d` > 90%
3. `dc_inventory_days` > 14

## Post-Processing Escalation (Layer 3 pipeline)
- MEDIUM → HIGH if part of a VENDOR, DC_LANE, CATEGORY, or REGION pattern (3+ exceptions)
- HIGH → CRITICAL if part of a pattern AND perishable AND promo active
