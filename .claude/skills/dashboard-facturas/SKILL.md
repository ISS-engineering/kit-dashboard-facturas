---
name: dashboard-facturas
description: Use when the user asks to analyze invoice PDFs, build a billing/invoicing dashboard, see revenue or expense reports, review VAT/IRPF or quarterly tax summaries, identify top clients by revenue, or detect trends in their billing. Multilingual triggers — EN "analyze my invoices", "billing dashboard", "VAT summary", "quarterly report", "client revenue"; ES "analiza mis facturas", "dashboard facturación", "resumen IVA", "balance ingresos gastos"; DE "Rechnungen analysieren", "Umsatz Dashboard", "MwSt Übersicht"; FR "analyser les factures", "tableau de bord facturation", "résumé TVA"; IT "analizza fatture", "dashboard fatturazione", "riepilogo IVA".
license: MIT
compatibility: Requires Python 3.10+ and uv (https://docs.astral.sh/uv/). Scripts self-bootstrap their dependencies (pdfplumber, jinja2, babel, click) via PEP-723 inline metadata — no manual pip install needed.
user-invocable: true
metadata:
  author: ISS Engineering
  version: "0.1.1"
  source: https://github.com/ISS-engineering/kit-dashboard-facturas
allowed-tools: Bash(./.claude/skills/dashboard-facturas/scripts/parse-invoices.py:*) Bash(./.claude/skills/dashboard-facturas/scripts/calculate-metrics.py:*) Bash(./.claude/skills/dashboard-facturas/scripts/render-dashboard.py:*) Bash(${CLAUDE_PLUGIN_ROOT}/.claude/skills/dashboard-facturas/scripts/parse-invoices.py:*) Bash(${CLAUDE_PLUGIN_ROOT}/.claude/skills/dashboard-facturas/scripts/calculate-metrics.py:*) Bash(${CLAUDE_PLUGIN_ROOT}/.claude/skills/dashboard-facturas/scripts/render-dashboard.py:*) Bash(uv:*) Bash(open:*) Read Write
---

# Invoice Dashboard

Reads a folder of invoice PDFs and generates a financial dashboard. **The model orchestrates and explains; the scripts parse, calculate, and render.** Never invent numbers — every figure on the dashboard must trace back to a script output.

## When to use

- User wants to analyze a batch of invoices
- User asks for a billing/revenue/expense summary
- User asks for a VAT (IVA) or IRPF report
- User points to a folder of PDFs and asks for "the financial picture"

## When NOT to use

- Single-invoice questions ("what's the total on this PDF?") → use the Read tool directly
- Bank statements, payroll, or other non-invoice documents
- Anything requiring write-back to an accounting system (out of scope for v1)

## Language

Respond in the user's language. Detect from their first message; default to English. Supported codes: `en`, `es`, `de`, `fr`, `it`. Whichever language you detect, **pass the matching `--lang` code to every script call** — the dashboard's labels, alerts, and number formatting all depend on it.

## Workflow

**Where the scripts live**: this skill ships in two modes, so use the shell expansion `${CLAUDE_PLUGIN_ROOT:-.}` as the base for every script and asset path in your commands. It does the right thing automatically:

- **Plugin install** — `CLAUDE_PLUGIN_ROOT` is set by Claude Code to the plugin's install directory, so the shell expands to the absolute path of the installed plugin.
- **Kit / project mode** — the variable is unset, so `${CLAUDE_PLUGIN_ROOT:-.}` falls back to `.` and the relative paths resolve against the current project (which must contain `CLAUDE.md` at its root).

The user's `cwd` should be the folder containing their `facturas/` directory and where the output dashboard will be written. The scripts are reached via the `${CLAUDE_PLUGIN_ROOT:-.}` prefix; user-supplied inputs (`facturas/ingresos`, etc.) are reached via plain relative paths from `cwd`.

**Reproducibility flag**: every script accepts `--frozen-date YYYY-MM-DD`. Pass it when you want byte-identical outputs across runs (e.g. test scenarios). Omit it for normal use — the scripts default to today's date.

### Step 1 — Locate the invoices

Ask in the user's language: *"Are your invoices already in `facturas/ingresos/` and `facturas/gastos/`, or somewhere else?"*

If they're in a different folder, accept any absolute or relative path. If only one type exists (only income, or only expenses), proceed with what's there.

### Step 2 — Parse the PDFs

Run the parser. It produces a single JSON with one entry per PDF:

```bash
"${CLAUDE_PLUGIN_ROOT:-.}/.claude/skills/dashboard-facturas/scripts/parse-invoices.py" \
  --ingresos facturas/ingresos \
  --gastos facturas/gastos \
  --lang <lang> \
  --out facturas_datos.json
```

The script writes `facturas_datos.json` (the structured extraction) and prints a brief stdout summary: `N parsed, M with warnings`. If any PDF couldn't be parsed cleanly, the script lists which fields are missing — surface those to the user in their language and ask whether to proceed, retry, or fix manually.

See [references/invoice-fields.md](references/invoice-fields.md) for the JSON schema and field semantics.

### Step 3 — Calculate metrics

Run the metrics calculator. It consumes `facturas_datos.json` and produces a metrics JSON:

```bash
"${CLAUDE_PLUGIN_ROOT:-.}/.claude/skills/dashboard-facturas/scripts/calculate-metrics.py" \
  --in facturas_datos.json \
  --lang <lang> \
  --out metrics.json
```

All math (totals, quarterly VAT, top clients, trends, monthly evolution) is computed here — never by you. See [references/iva-rules.md](references/iva-rules.md) for the VAT/IRPF rules the script implements.

### Step 4 — Render the dashboard

```bash
"${CLAUDE_PLUGIN_ROOT:-.}/.claude/skills/dashboard-facturas/scripts/render-dashboard.py" \
  --metrics metrics.json \
  --invoices facturas_datos.json \
  --lang <lang> \
  --template "${CLAUDE_PLUGIN_ROOT:-.}/.claude/skills/dashboard-facturas/assets/dashboard-template.html" \
  --locales "${CLAUDE_PLUGIN_ROOT:-.}/.claude/skills/dashboard-facturas/assets/locales" \
  --out dashboard-facturacion.html
```

Open the result for the user: `open dashboard-facturacion.html`.

### Step 5 — Summarize

In the user's language, present:

1. How many invoices were parsed cleanly vs. with warnings
2. The top 3 metrics in one sentence each (e.g. "Total revenue: 26 750 €", "Q1 VAT to settle: 1 234 €", "Top client represents 38 % of revenue")
3. Any alerts the metrics script flagged (client dependency, missing months, trend changes)
4. Offer next steps: re-render in a different language, correct an invoice manually, drill into a specific quarter

## Output contract

Every run produces three artifacts in the project root:

| File | Producer | What it is |
|---|---|---|
| `facturas_datos.json` | `parse-invoices.py` | Structured extraction, one entry per PDF |
| `metrics.json` | `calculate-metrics.py` | All computed metrics (totals, quarters, top clients, alerts) |
| `dashboard-facturacion.html` | `render-dashboard.py` | The self-contained HTML report |

Each script is **idempotent**: running it again with the same inputs produces byte-identical output. This is what makes the kit testable.

## Common mistakes

- **Doing math yourself** → forbidden. Even simple sums. Call the script.
- **Skipping `--lang`** → the dashboard will render in English regardless of the conversation language.
- **Re-parsing PDFs on every render** → if `facturas_datos.json` already exists and the user wants to tweak language only, skip Step 2 and re-run Steps 3–4 with the new `--lang`.
- **Inventing fields** → if the script reports a missing field on an invoice, surface that to the user. Don't fill it in to make the JSON look complete.
