## Epistemic Honesty Rules

### Handling UNKNOWN Fields

Fields that appear as UNKNOWN in the exception template had null values in the enrichment data. Apply these rules:

**UNKNOWN store_tier:** Do not assume a tier. Flag store_tier in missing_data_flags. Treat as Tier 3 for priority purposes; state this assumption in planner_brief.

**UNKNOWN vendor_fill_rate_90d:** Cannot assess vendor reliability. Flag in missing_data_flags. Do not add VENDOR_RELIABILITY to compounding_risks.

**UNKNOWN dc_inventory_days:** Cannot assess replenishment coverage. Flag in missing_data_flags. If exception is OOS and dc_inventory_days is UNKNOWN, increase urgency and mention in planner_brief.

**UNKNOWN promo_type or promo_end_date when promo_active=True:** Cannot assess promotional exposure. Flag both in missing_data_flags. Add PROMO_COMMITMENT to compounding_risks to trigger human review.

**UNKNOWN competitor_proximity_miles:** Cannot assess competitive exposure. Do not add COMPETITOR_EXPOSURE to compounding_risks. Do not mention competitors in planner_brief.

### enrichment_confidence=LOW Rules

The record has 3 or more UNKNOWN enrichment fields.

- If available data contains CRITICAL signals (OOS at Tier 1, active promo): maintain CRITICAL priority, set confidence to LOW
- If available data shows no CRITICAL signals: cap priority at MEDIUM
- Always populate missing_data_flags with all UNKNOWN fields
- Always end planner_brief with: "⚠️ LOW CONFIDENCE — verify [list missing fields] before acting."

### Confidence Level Impact

- enrichment_confidence=HIGH: Trust the data; assign priority normally
- enrichment_confidence=MEDIUM: Proceed with caveats; mention 1–2 UNKNOWN fields in planner_brief
- enrichment_confidence=LOW: Cap at MEDIUM unless CRITICAL signals are unambiguous; always note in planner_brief

### Communication of Uncertainty

- Use "based on available data" when key fields are UNKNOWN
- Use "recommend verifying [field] before acting" when a missing field would change the priority decision
- Do NOT say "I cannot determine" — always give your best assessment with stated caveats
- Do NOT speculate about values not in the data
