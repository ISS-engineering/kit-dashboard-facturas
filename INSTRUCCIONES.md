# Invoice Dashboard Kit — Setup Guide

> *Available in: English (below) · [Español](#español) · [Deutsch](#deutsch) · [Français](#français) · [Italiano](#italiano)*

## Requirements

1. **Visual Studio Code** — https://code.visualstudio.com
2. **Claude Code extension** for VS Code (search "Claude Code" in the Extensions panel)
3. **Python 3.10+** with `uv` installed (https://docs.astral.sh/uv/ — `curl -LsSf https://astral.sh/uv/install.sh | sh`)

`uv` is used to run the scripts in an isolated environment. You don't need to install any Python libraries yourself — they're declared inside each script and `uv` fetches them on first run.

## Steps

1. **Open this folder in VS Code**: File → Open Folder → select `kit-dashboard-facturas`.
2. **Open Claude Code** in the side panel.
3. **Drop your PDFs** into:
   - `facturas/ingresos/` for invoices you've issued (income)
   - `facturas/gastos/` for invoices you've received (expenses)
4. **Type a request in your preferred language**, for example:
   - 🇬🇧 *"Analyse my invoices and build the dashboard."*
   - 🇪🇸 *"Analiza mis facturas y genera el dashboard."*
   - 🇩🇪 *"Analysiere meine Rechnungen und erstelle das Dashboard."*
   - 🇫🇷 *"Analyse mes factures et génère le tableau de bord."*
   - 🇮🇹 *"Analizza le mie fatture e genera la dashboard."*

Claude will detect the language, run the extraction, calculate the metrics, and produce `dashboard-facturacion.html` in this folder.

## What you get

- `dashboard-facturacion.html` — printable, self-contained dashboard in your language
- `facturas_datos.json` — the structured extraction (review before rendering if you want)
- Per-invoice math is verifiable: scripts do the arithmetic, not the language model

## Folder structure

```
kit-dashboard-facturas/
├── CLAUDE.md                                ← Instructions for Claude (don't edit)
├── INSTRUCCIONES.md                         ← This file
├── facturas/
│   ├── ingresos/                            ← Your income PDFs
│   └── gastos/                              ← Your expense PDFs
└── .claude/skills/dashboard-facturas/       ← The skill itself
    ├── SKILL.md
    ├── references/                          ← Detailed reference for Claude
    ├── scripts/                             ← The Python pipeline
    └── assets/
        ├── dashboard-template.html
        └── locales/                         ← One JSON per supported language
```

---

## Español

### Requisitos
1. Visual Studio Code · 2. Extensión Claude Code · 3. Python 3.10+ con `uv`

### Pasos
1. Abre esta carpeta en VS Code
2. Abre Claude Code en el panel lateral
3. Mete tus PDFs en `facturas/ingresos/` (ingresos) y/o `facturas/gastos/` (gastos)
4. Escríbele a Claude *"Analiza mis facturas y genera el dashboard"*

---

## Deutsch

### Voraussetzungen
1. Visual Studio Code · 2. Claude Code Erweiterung · 3. Python 3.10+ mit `uv`

### Schritte
1. Öffne diesen Ordner in VS Code
2. Öffne Claude Code in der Seitenleiste
3. Lege deine PDFs in `facturas/ingresos/` (Einnahmen) und/oder `facturas/gastos/` (Ausgaben)
4. Schreibe an Claude: *"Analysiere meine Rechnungen und erstelle das Dashboard"*

---

## Français

### Prérequis
1. Visual Studio Code · 2. Extension Claude Code · 3. Python 3.10+ avec `uv`

### Étapes
1. Ouvrir ce dossier dans VS Code
2. Ouvrir Claude Code dans le panneau latéral
3. Placer vos PDFs dans `facturas/ingresos/` (revenus) et/ou `facturas/gastos/` (dépenses)
4. Écrire à Claude : *"Analyse mes factures et génère le tableau de bord"*

---

## Italiano

### Requisiti
1. Visual Studio Code · 2. Estensione Claude Code · 3. Python 3.10+ con `uv`

### Passi
1. Apri questa cartella in VS Code
2. Apri Claude Code nel pannello laterale
3. Metti i tuoi PDF in `facturas/ingresos/` (entrate) e/o `facturas/gastos/` (uscite)
4. Scrivi a Claude: *"Analizza le mie fatture e genera la dashboard"*
