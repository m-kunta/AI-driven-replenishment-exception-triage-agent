## Pattern Detection Directive

### When to Flag a Pattern

Flag a preliminary pattern when 3 or more exceptions in the current batch share the same value for any of these dimensions:

- vendor_id → VENDOR pattern
- region (same region, different vendors/categories) → REGION pattern
- category → CATEGORY pattern
- Multiple dimensions simultaneously → MACRO pattern

The default threshold is 3. Report what you observe in this batch in the pattern_analysis object.

### Pattern Types

**VENDOR:** Multiple exceptions trace to the same supplier. Signals: shared vendor_id, vendor_fill_rate_90d below 85%, correlated VENDOR_LATE exception types. Root cause: vendor capacity issue, raw material shortage, or logistics disruption.

**DC_LANE:** Multiple exceptions from stores in the same region without a vendor root cause. Root cause: DC out-of-stock, lane scheduling delay, or DC operational issue.

**CATEGORY:** Multiple exceptions clustered in a single product category across different stores and vendors. Root cause: demand spike, seasonal shift, forecast model failure, or category-wide supplier disruption.

**REGION:** Multiple exceptions concentrated in a geographic region cutting across vendors and categories. Root cause: regional demand event, weather, or competitive disruption.

**MACRO:** Exceptions spanning multiple vendors, categories, and regions simultaneously. Root cause: systemic forecasting or ordering system failure.

### Important: Do Not Apply Escalations Yourself

Report patterns in preliminary_patterns. The pattern analyzer module will:
- Confirm patterns with 3+ exceptions across all batches (not just this batch)
- Escalate MEDIUM exceptions to HIGH for confirmed pattern members
- Populate pattern_id and escalated_from in each TriageResult

### Pattern Analysis Object

Always include the _type: pattern_analysis object as the last element of your JSON array, even if no patterns are detected. If no patterns are detected, set preliminary_patterns to an empty array [].
