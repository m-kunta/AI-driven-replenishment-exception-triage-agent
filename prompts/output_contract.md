## Output Contract

Return the full batch as a JSON array. Do not wrap your response in ``` code fences or any markdown formatting. Do not include any text before or after the JSON array.

Each element of the array must be a JSON object with exactly these fields:

  {
    "exception_id": "string — copy exactly from input",
    "priority": "CRITICAL | HIGH | MEDIUM | LOW",
    "confidence": "HIGH | MEDIUM | LOW — inherit from enrichment_confidence unless you have strong reason to downgrade",
    "root_cause": "string — max 30 words, specific and factual",
    "recommended_action": "string — max 25 words, one concrete action the planner can take now",
    "financial_impact_statement": "string — max 20 words, dollar amounts if available",
    "planner_brief": "string — max 75 words, context paragraph for the planner",
    "compounding_risks": ["use only: POTENTIAL_PHANTOM_INVENTORY, PROMO_COMMITMENT, COMPETITOR_EXPOSURE, VENDOR_RELIABILITY, PERISHABLE_URGENCY, DATA_INTEGRITY_RISK"],
    "missing_data_flags": ["list of field names that were UNKNOWN in input and affected your assessment"],
    "pattern_id": null,
    "escalated_from": null,
    "phantom_flag": false,
    "reasoning_trace": null
  }

After the array of exception objects, include ONE additional JSON object as the last array element:

  {
    "_type": "pattern_analysis",
    "vendor_summary": {
      "VND-XXX": {"count": 0, "critical_count": 0, "high_count": 0}
    },
    "dc_summary": {
      "DC-XXX": {"count": 0}
    },
    "category_summary": {
      "CategoryName": {"count": 0}
    },
    "region_summary": {
      "RegionName": {"count": 0}
    },
    "preliminary_patterns": [
      {
        "pattern_type": "VENDOR | DC_LANE | CATEGORY | REGION | MACRO",
        "group_key": "identifier",
        "count": 0,
        "description": "one sentence describing the pattern"
      }
    ]
  }

Field constraints:
- priority: must be exactly one of CRITICAL, HIGH, MEDIUM, LOW
- confidence: must be exactly one of HIGH, MEDIUM, LOW
- root_cause: must not exceed 30 words
- recommended_action: must not exceed 25 words
- financial_impact_statement: must not exceed 20 words
- planner_brief: must not exceed 75 words
- compounding_risks: use only flags from the allowed list; empty array if none apply
- missing_data_flags: list only fields that were UNKNOWN in your input
- pattern_id: always null — the pattern analyzer populates this after your response
- escalated_from: always null — the pattern analyzer populates this after your response
- phantom_flag: always false — the phantom webhook sets this after confirmation
- reasoning_trace: always null unless instructed otherwise in the user prompt
- Do NOT invent numbers not given in the input
- Do NOT use markdown formatting inside string field values
