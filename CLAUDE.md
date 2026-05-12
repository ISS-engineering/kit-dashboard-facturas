# Invoice Dashboard Kit

This project reads a folder of invoice PDFs and generates a visual financial dashboard. It is designed to be opened by a non-technical user who then has a natural-language conversation with Claude.

## When the user opens this folder

Greet them with this welcome, then auto-trigger the `dashboard-facturas` skill:

> **Welcome to the Invoice Dashboard kit.**
>
> I'll read your invoice PDFs and generate a complete financial dashboard: revenue, expenses, VAT, monthly trends, top clients, and quarterly summaries.
>
> Put your invoice PDFs into the `facturas/` folder:
> - `facturas/ingresos/` — invoices you've **issued** (income)
> - `facturas/gastos/` — invoices you've **received** (expenses)
>
> If you only have one type, that's fine — put them in the matching folder.
>
> *Tip: I can work in **English, Spanish, German, French, or Italian** — just talk to me in your preferred language and I'll switch.*
>
> Ready when you are.

## Language handling

- **Default**: English.
- **Auto-detect**: if the user's first message is in Spanish/German/French/Italian, switch to that language for the entire conversation **and** pass the matching `--lang` code to all scripts.
- **Explicit override**: if the user says "let's switch to X" (in any language), honor it.
- Supported codes (ISO 639-1): `en`, `es`, `de`, `fr`, `it`.

## Currency vs language — separate concerns

- **Language** controls UI labels in the dashboard (passed via `--lang`).
- **Currency symbol** is read from each invoice (`moneda` field) — never assumed from language.
- **Number/date formatting** follows the language locale by default (e.g. `1.234,56 €` for `es-ES`, `1,234.56 €` for `en-US`). The scripts use `babel` for this.

## Tooling

The skill uses three Python scripts in `.claude/skills/dashboard-facturas/scripts/`:
- `parse-invoices.py` — extracts structured data from each PDF
- `calculate-metrics.py` — computes totals, quarterly VAT, top clients, trends
- `render-dashboard.py` — renders the HTML dashboard from a template + locale file

The scripts are self-bootstrapping via `uv` — no global Python installation steps required from the buyer.

## Privacy

All processing is local. Invoice data never leaves the user's machine.
