## Phantom Inventory Detection

### What is Phantom Inventory?

Phantom inventory occurs when the system shows zero units on hand but physical stock is present — miscounted or mislocated. It is NOT a true replenishment failure. The item is physically available; the record is wrong.

### Signals That Suggest Phantom Inventory

A phantom inventory scenario is likely when the majority of these signals are present:

1. exception_type is OOS or LOW_STOCK (system shows zero or near-zero on hand)
2. vendor_fill_rate_90d is high (>90%) — the vendor reliably ships
3. dc_inventory_days is high (>14 days) — the DC has ample stock
4. open_po_inbound is true or lead time is short — replenishment is not blocked upstream
5. No competing explanation (regional disruption, promo surge) for the stock-out

When 3 or more of these signals are present, add "POTENTIAL_PHANTOM_INVENTORY" to compounding_risks.

### How to Flag

Add "POTENTIAL_PHANTOM_INVENTORY" to the compounding_risks array. This triggers the phantom webhook module.

Do NOT:
- Change exception_type yourself — leave it as OOS or LOW_STOCK
- Set phantom_flag to true — the webhook module sets this after confirmation
- Change priority solely because of phantom suspicion — the OOS or LOW_STOCK risk stands until confirmed

### Recommended Action Language for Phantom Scenarios

recommended_action: "Conduct physical count before placing emergency order — possible phantom inventory."

planner_brief addition: "Vendor fill rate of [N]% and [N] days DC inventory suggest stock may be present but miscounted. Physical count recommended before emergency replenishment."
