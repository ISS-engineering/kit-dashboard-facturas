# Phase 1 Baseline — Original kit-dashboard-facturas

Captured: 2026-05-12. Source: `manual-collection/.claude/skills/10-SKILLS-ADRI-Y-JUANPE/kit-dashboard-facturas/`

## What the original kit ships with

| Artifact | Location in original | Size | Role |
|---|---|---|---|
| Skill | `.claude/skills/04-dashboard-facturas.md` | ~290 lines | Single-file skill |
| Project intro for Claude | `CLAUDE.md` | ~50 lines | Welcome + auto-skill-trigger |
| Buyer setup guide | `INSTRUCCIONES.md` | ~70 lines | Install VS Code, open folder, ask |
| Fixture PDFs (ingresos) | `facturas/ingresos/*.pdf` | 10 files | Test inputs |
| Fixture PDFs (gastos) | `facturas/gastos/*.pdf` | 6 files | Test inputs |
| Reference JSON | `facturas_datos.json` | 266 lines | Author's expected extraction |
| Reference HTML | `dashboard-facturacion.html` | 545 lines | Author's rendered dashboard |

All 16 PDF fixtures + the JSON + the HTML are now copied to `tests/fixtures/` here as ground truth.

## Audit of the bundled `facturas_datos.json`

- 16 invoices total: 10 ingresos + 6 gastos
- All EUR
- Date range: 2025-10-01 to 2026-03-20 (≈ 6 months)
- Totals from his data:
  - Ingresos net: **26,750.00 €** · gross: **28,355.00 €**
  - Gastos net: **588.63 €** · gross: **712.24 €**
- **Per-invoice math is internally consistent.** For every entry, `base_imponible + iva_cantidad + irpf_cantidad == total` (zero diff). The author's example output is clean — usable as ground truth for our reimplementation.

## Audit of the bundled `dashboard-facturacion.html`

- 545 lines, fully autocontained (1 inline `<style>`, **0** `<script>` blocks — pure HTML/CSS)
- Sections: `Dashboard de Facturación` (h1), `Facturación mes a mes (base imponible)`, `Liquidación de IVA por trimestre`, `Top clientes por facturación`
- Title hardcodes the example business: `Dashboard Facturación · Estudio Creativo Vega SL`
- `<html lang>` present but content is Spanish-only
- No interactivity, no sortable tables, no filters (the skill body promises these but the reference HTML doesn't deliver)

## Technical debts to address (the upgrade targets)

| # | Problem | Cost to buyer | Our fix |
|---|---|---|---|
| 1 | LLM does all PDF parsing | Inconsistent extraction on edge cases | `scripts/parse-invoice.py` (pdfplumber) |
| 2 | LLM does all the math | Hallucination risk on a *financial* dashboard | `scripts/calculate-metrics.py` (deterministic) |
| 3 | LLM does all HTML rendering ("libertad creativa total") | Output varies run-to-run, no brand consistency | `assets/dashboard-template.html` + script |
| 4 | Skill body claims sortable/filterable tables; reference HTML has none | Buyer disappointment | Template delivers what's promised |
| 5 | Spanish-only | Limits market to Spanish-speaking buyers | `assets/locales/{en,es,de,fr,it}.json` + auto-detect |
| 6 | Single-file skill | Less portable, no room to grow | Directory + SKILL.md + references/scripts/assets |
| 7 | No tests | Author can't verify a change didn't break extraction or math | pytest for scripts + subagent integration test |
| 8 | No declared dependencies | `compatibility` field empty; buyer doesn't know what's needed | `compatibility: Requires Python 3.10+ and uv` |
| 9 | No allowed-tools | Buyer prompted on every script invocation | Narrow allowlist for the three scripts |
| 10 | No plugin packaging | Folder-copy distribution only | `.claude-plugin/plugin.json`, versioned, installable |

## What stays from the original

These patterns are good — keep them:

- `CLAUDE.md` welcome-on-open behavior (great UX for non-technical buyers)
- `INSTRUCCIONES.md` separate from CLAUDE.md (human docs vs. AI docs)
- Asking up front whether they have ingresos, gastos, or both
- Inferring `ingreso`/`gasto` from folder structure (`facturas/ingresos/`, `facturas/gastos/`)
- Intermediate JSON the user can review/correct before HTML render
- Privacy claim: everything stays local

## Division of labor — LLM vs scripts (the architectural decision)

| Job | Original | Upgraded |
|---|---|---|
| Greet, ask for folder, detect language | LLM | LLM |
| Parse each PDF → JSON | LLM (Read tool) | **Script** (pdfplumber) |
| Reconcile inconsistencies, ask user about ambiguous PDFs | LLM | LLM |
| Calculate totals, quarterly IVA, top clients, trends | LLM | **Script** (pure Python) |
| Render HTML dashboard | LLM (freeform) | **Script** (template + locale) |
| Localize labels and number formats | n/a | **Script** (locale JSON + babel) |
| Summarize results, suggest follow-ups, flag anomalies | LLM | LLM |

**Principle**: the LLM stops being the calculator and becomes the conductor. Scripts handle anything where reviewability, reproducibility, or correctness matters.
