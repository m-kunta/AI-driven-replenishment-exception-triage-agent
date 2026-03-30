## Triage Priority Framework

### CRITICAL

An exception is CRITICAL when immediate action is required within hours to prevent material financial harm or customer service failure.

**Criteria (any one is sufficient):**
- Item is OOS or <1.5 days of supply at a Tier 1 store with an active promo (TPR, FEATURE, BOTH)
- Item is perishable with <1.0 days of supply, regardless of store tier
- Item is OOS at a Tier 1 or Tier 2 store AND a competitor is within 2 miles AND a competitor event is active
- Item is part of a vendor pattern with 5+ exceptions from the same vendor with fill rate <80%
- ORDER_FAILURE for a Tier 1 store item with promo active and no inbound PO

**Compounding escalation to CRITICAL:**
- Any HIGH exception where ALL THREE are true: promo active + perishable + Tier 1 store

**Examples:**
1. OOS on Organic Whole Milk at a Flagship Tier 1 store with active 15% TPR and a competitor dairy promotion 0.3 miles away → CRITICAL
2. Perishable item at 0.5 days of supply at any store → CRITICAL
3. 7 vendor-late exceptions from the same distributor (fill rate 72%) → flag all CRITICAL

---

### HIGH

An exception is HIGH when same-day resolution is required to prevent significant but manageable risk.

**Criteria (any one is sufficient):**
- Item is <3.0 days of supply at a Tier 1 or Tier 2 store
- Item is OOS at a Tier 3 store with active TPR
- VENDOR_LATE exception for a Tier 1/2 store item with open promo and no alternative inbound
- Item is part of a confirmed VENDOR, DC_LANE, or CATEGORY pattern (even if individually MEDIUM)
- OOS with no inbound PO and lead time >7 days

**Examples:**
1. LOW_STOCK at 2.1 days of supply for a Tier 2 store item → HIGH
2. A MEDIUM exception joined by 4 others from the same vendor (pattern escalation) → HIGH

---

### MEDIUM

An exception is MEDIUM when same-week resolution is required. Significant but not urgent.

**Criteria:**
- OOS or LOW_STOCK at a Tier 3 store without active promo
- FORECAST_VARIANCE >25% at a Tier 1/2 store with no stock risk
- VENDOR_LATE at a Tier 3/4 store with adequate DC inventory
- Any exception with 3–7 days of supply and no compounding risk factors

**Examples:**
1. LOW_STOCK at a Tier 3 store ($280K/week), no promo, DC has 12 days supply → MEDIUM
2. FORECAST_VARIANCE of 35% at a Tier 2 store, 8 days on hand → MEDIUM

---

### LOW

An exception is LOW when it is informational only. No immediate action required.

**Criteria:**
- FORECAST_VARIANCE at a Tier 4 store, regardless of variance percentage
- OOS or LOW_STOCK at a Tier 4 store, non-perishable, no promo, DC has adequate inventory
- Any exception where enrichment_confidence is LOW and no CRITICAL signals are visible in the available data
- Exceptions representing normal replenishment cycle variation with no downstream risk

**Examples:**
1. FORECAST_VARIANCE of 45% at a Tier 4 store ($120K/week), non-perishable, 6 days on hand → LOW
2. LOW_STOCK at a Tier 4 store, vendor fill rate 95%, DC has 18 days supply → LOW

---

### Compound Risk Escalation Rules

Apply after initial priority assignment:

1. **MEDIUM → HIGH**: exception is part of a detected VENDOR, DC_LANE, CATEGORY, or REGION pattern (3+ exceptions in group)
2. **HIGH → CRITICAL**: exception is part of a pattern AND item is perishable AND promo is active
3. **Any priority → add "POTENTIAL_PHANTOM_INVENTORY" to compounding_risks** if: OOS or LOW_STOCK exception + vendor fill rate >90% + dc_inventory_days >14. Do not change priority based on phantom flag alone.
