# VAT / IRPF rules implemented by `calculate-metrics.py`

This reference documents the deterministic logic. Anyone (developer or buyer's accountant) should be able to audit it.

## Quarterly VAT settlement (Spanish model)

Spanish autónomos and SLs file VAT quarterly. The script bucketizes invoices into Q1–Q4 by issue date:

| Quarter | Months |
|---|---|
| Q1 | January – March |
| Q2 | April – June |
| Q3 | July – September |
| Q4 | October – December |

For each quarter:

- **VAT collected** (IVA repercutido) = sum of `iva_cantidad` across `tipo == "ingreso"` invoices in that quarter
- **VAT paid** (IVA soportado) = sum of `iva_cantidad` across `tipo == "gasto"` invoices in that quarter
- **Net VAT to settle** = VAT collected − VAT paid
  - Positive → owe to the tax authority
  - Negative → credit / refund

The dashboard reports each quarter's three numbers. It does **not** add up across calendar years — Q4-2025 and Q1-2026 are separate buckets.

## IRPF withholding

IRPF rates appear as a **negative percentage** (`-15`, `-7`, etc.) because the client withholds that amount from the gross. The parser stores both the rate and the absolute amount as negative numbers, so the per-invoice math is simply additive:

```
total = base_imponible + iva_cantidad + irpf_cantidad
```

The metrics script sums `irpf_cantidad` across all `ingreso` invoices in a year. This is the number the autónomo plugs into their annual income-tax declaration.

## Top-clients calculation

- Group `ingreso` invoices by `receptor` (the client)
- For each group: count of invoices, sum of `base_imponible`, percentage of total net revenue
- Sort descending by net revenue
- **Dependency alert**: if any single client represents ≥ 40% of net revenue, emit an alert in the metrics JSON

## Monthly evolution

- Bucketize invoices by `(YYYY, MM)`
- For each month: sum net revenue and sum net expenses separately
- Output as an ordered list of months — the script never skips a month, even if zero (so the dashboard chart shows the gap)

## Trend detection

- Take the last 3 months of net revenue
- Compare to the 3 months before that
- If +10% or more → trend up
- If −10% or more → trend down
- Otherwise → flat

These thresholds are constants in the script; they can be tuned per buyer if needed (future config option).

## Currency

All sums are per-currency. If invoices use mixed currencies (EUR + USD), the script keeps separate totals per currency and emits a warning — it does **not** convert.

## What the script does NOT do

- Currency conversion
- Inferring the fiscal year if invoices span calendar boundaries (it reports per-quarter as-is)
- Modelo 130/303/390 declarations (that's an accountant's job, not the dashboard's)
- Bank reconciliation
- Detecting duplicates beyond identical `numero` + `emisor` + `fecha`

These are all candidate features for v2 but are deliberately out of scope for v1.
