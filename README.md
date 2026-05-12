# dashboard-facturas

Multilingual invoice dashboard for Claude Code. Drop a folder of invoice PDFs, get back a self-contained HTML dashboard with revenue, expenses, VAT/IRPF settlement, top clients, monthly trends, and quarterly summaries — in English, Spanish, German, French, or Italian.

## Two ways to use it

### A) As a plugin (technical users)

Install once, use from any project.

```bash
# Add this folder as a one-plugin marketplace
/plugin marketplace add /path/to/kit-dashboard-facturas

# Install the plugin
/plugin install dashboard-facturas@iss-engineering-kits
```

Once installed, drop your PDFs anywhere and say *"analyze my invoices"* in any language. The skill auto-detects the language and produces `dashboard-facturacion.html` in the current folder.

### B) As a kit / project (non-technical users)

Open the folder directly — no install step.

1. Open `kit-dashboard-facturas/` in VS Code with the Claude Code extension.
2. Drop your PDFs into `facturas/ingresos/` (income) and/or `facturas/gastos/` (expenses).
3. Tell Claude: *"Analyse my invoices and build the dashboard."*

See `INSTRUCCIONES.md` for the same steps in 5 languages.

## What you get

| File | Producer | Description |
|---|---|---|
| `facturas_datos.json` | parse-invoices.py | Structured invoice data extracted from every PDF |
| `metrics.json` | calculate-metrics.py | All computed financial metrics |
| `dashboard-facturacion.html` | render-dashboard.py | Self-contained HTML dashboard in your language |

## Requirements

- **Claude Code** (CLI or VS Code extension)
- **Python 3.10+**
- **`uv`** — the scripts self-bootstrap their Python dependencies on first run
- **PDF invoices** that follow common patterns (Spanish / EU / generic Western layouts)

## Languages supported

English (default) · Español · Deutsch · Français · Italiano

Add a sixth language by dropping a new JSON into `.claude/skills/dashboard-facturas/assets/locales/` — see `references/locales-schema.md` for the schema.

## Architecture

The skill is intentionally split across **three deterministic Python scripts** with the LLM only orchestrating:

```
PDFs  →  parse-invoices.py  →  facturas_datos.json
                                     │
                                     ▼
                          calculate-metrics.py  →  metrics.json
                                                       │
                                                       ▼
                                        render-dashboard.py  →  dashboard.html
                                          (template + locale)
```

The model **does not compute any numbers**. Every figure on the dashboard traces back to a script output, which makes the kit verifiable: a passing test suite proves the numbers are correct, not that the LLM happened to be right today.

## Development

```bash
# Run the test suite (offline, no API tokens needed)
uv run --with pytest --with pdfplumber --with jinja2 --with babel --with click \
    pytest tests/

# Run the subagent integration test (uses real Claude API tokens)
RUN_SUBAGENT_TESTS=1 uv run --with pytest pytest tests/test_subagent_integration.py
```

See `tests/SUBAGENT_TESTING.md` for the manual subagent procedure and pressure scenarios.

## License

MIT — see [LICENSE](LICENSE).

## Roadmap

- **v0.2**: bank-statement reconciliation, CSV export
- **v0.3**: extract the three scripts into a standalone MCP server (for non-Claude clients)
- **v0.4**: more locales (PT, CA, NL) — community contributions welcome
