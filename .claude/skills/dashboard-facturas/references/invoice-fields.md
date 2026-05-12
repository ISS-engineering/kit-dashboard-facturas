# Invoice extraction — field schema

This is the JSON contract produced by `parse-invoices.py`. Each PDF becomes one object in `facturas[]`.

## Top-level shape

```json
{
  "fecha_generacion": "2026-05-12",
  "rango": "2025-10-01 a 2026-03-20",
  "emisor_propio": {
    "nombre": "Estudio Creativo Vega SL",
    "cif": "B-12345678"
  },
  "facturas": [ { /* per-invoice object — see below */ } ],
  "warnings": [
    { "archivo": "ingresos/F-2025-018.pdf", "field": "irpf_porcentaje", "reason": "not found" }
  ]
}
```

- `emisor_propio` is detected by finding the issuer that appears in the majority of ingresos PDFs (this is "you", the business owner).
- `warnings` lists every field the parser couldn't extract cleanly. Empty array means all PDFs parsed without issues.

## Per-invoice object

| Field | Type | Required | Notes |
|---|---|---|---|
| `archivo` | string | yes | Relative path from project root (e.g. `ingresos/F-2025-018.pdf`) |
| `tipo` | `"ingreso"` \| `"gasto"` | yes | Inferred from folder: `ingresos/` → `ingreso`, `gastos/` → `gasto` |
| `numero` | string | yes | Invoice number as printed |
| `fecha` | string (ISO 8601: `YYYY-MM-DD`) | yes | Issue date; parser normalizes from any input format |
| `emisor` | string | yes | Issuer business name |
| `receptor` | string | yes | Recipient business name |
| `concepto` | string | yes | Concatenated line-item descriptions |
| `base_imponible` | number | yes | Net amount, pre-tax. Always positive. |
| `iva_porcentaje` | number | no | VAT rate as integer percent (e.g. `21`). Null if invoice has no VAT (e.g. EU intra-community). |
| `iva_cantidad` | number | no | VAT amount in currency units. Always positive (or null if `iva_porcentaje` is null). |
| `irpf_porcentaje` | number | no | IRPF rate as **negative** integer percent (e.g. `-15`). Spanish withholding only. |
| `irpf_cantidad` | number | no | IRPF amount as **negative** number. |
| `total` | number | yes | Final amount payable. Must satisfy: `total = base_imponible + (iva_cantidad or 0) + (irpf_cantidad or 0)` within ±0.01 € rounding. |
| `moneda` | string (ISO 4217: `EUR`, `USD`, …) | yes | Detected from currency symbol or explicit code |

## Validation rules the parser enforces

1. `total == base_imponible + (iva_cantidad or 0) + (irpf_cantidad or 0)` within ±0.01 currency-unit rounding. If not, a warning is emitted.
2. `fecha` parses to a valid ISO date. Free-form dates ("12/03/2026", "12 de marzo de 2026", etc.) are normalized.
3. `tipo` is set deterministically from folder location — the parser never guesses.
4. If `iva_porcentaje` is present, `iva_cantidad ≈ base_imponible × iva_porcentaje / 100` within ±0.01.
5. If `irpf_porcentaje` is present, it must be negative, and `irpf_cantidad ≈ base_imponible × irpf_porcentaje / 100` within ±0.01.

## Field-extraction heuristics

The parser scans the PDF text with regular expressions tuned to the most common Spanish invoice formats. It also handles English variants.

| Field | Patterns tried (in order) |
|---|---|
| Invoice number | `Factura nº:`, `Nº:`, `Invoice #`, `Invoice no.`, then any `F-\d+`, `INV-\d+` |
| Date | `\d{1,2}[/-]\d{1,2}[/-]\d{2,4}`, `\d{1,2} de \w+ de \d{4}`, ISO `\d{4}-\d{2}-\d{2}` |
| Base imponible | `Base imponible`, `Subtotal`, `Net amount`, `Importe sin IVA` |
| IVA | `IVA \d+%`, `I.V.A.`, `VAT \d+%`, `Tax \d+%` |
| IRPF | `IRPF`, `Retención`, `-\d+%` near "IRPF" or "retención" |
| Total | `Total factura`, `Importe total`, `Total a pagar`, `Amount due`, `TOTAL` |
| Issuer / recipient | Top block typically contains issuer; "Cliente:" / "Bill to:" precedes recipient |
| Currency | `€` / `EUR` / `$` / `USD` symbol or code near the totals |

When multiple patterns match, the parser prefers the one closest to the end of the document (final totals override interim sums).

## When the parser can't extract a field

The parser sets the field to `null` and adds an entry to top-level `warnings`. The skill then surfaces these to the user — never silently fills them in.
