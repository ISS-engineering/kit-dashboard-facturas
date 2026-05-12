#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pdfplumber>=0.11", "click>=8.1"]
# ///
"""
Extract structured invoice data from a folder of PDFs.

Inputs:
  --ingresos PATH   directory of income PDFs (tipo=ingreso)
  --gastos   PATH   directory of expense PDFs (tipo=gasto)
  --lang     CODE   ISO 639-1 (en/es/de/fr/it) — affects warning messages only
  --out      PATH   output JSON file

Output: JSON conforming to references/invoice-fields.md.
Exit 0 even with warnings; non-zero only on hard I/O failure.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import click
import pdfplumber

# ---------------------------------------------------------------------------
# Number / date parsing helpers
# ---------------------------------------------------------------------------

# Spanish-style numbers use '.' as thousands sep and ',' as decimal sep.
# US/UK style is the opposite. We auto-detect by looking at the last separator:
# if the substring after the last separator has length 2 -> it's the decimal.
def parse_amount(s: str) -> float:
    s = s.strip().replace(" ", "").replace(" ", "")
    if not s:
        raise ValueError("empty amount")
    sign = 1
    if s.startswith("-"):
        sign = -1
        s = s[1:]
    # find candidate separators
    last_dot = s.rfind(".")
    last_comma = s.rfind(",")
    last_sep = max(last_dot, last_comma)
    if last_sep == -1:
        return sign * float(s)
    decimal_sep = s[last_sep]
    thousand_sep = "," if decimal_sep == "." else "."
    cleaned = s.replace(thousand_sep, "").replace(decimal_sep, ".")
    return sign * float(cleaned)


_MONTHS_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9,
    "octubre": 10, "noviembre": 11, "diciembre": 12,
}
_MONTHS_EN = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
_MONTHS = {**_MONTHS_ES, **_MONTHS_EN}


def parse_date(s: str) -> date:
    s = s.strip()

    # ISO YYYY-MM-DD
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))

    # DD/MM/YYYY or DD-MM-YYYY  (Spanish/European default)
    m = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", s)
    if m:
        d, mo, y = int(m[1]), int(m[2]), int(m[3])
        if y < 100:
            y += 2000
        return date(y, mo, d)

    # "12 de octubre de 2025" or "october 12, 2025"
    m = re.fullmatch(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", s, re.I)
    if m:
        return date(int(m[3]), _MONTHS[m[2].lower()], int(m[1]))
    m = re.fullmatch(r"(\w+)\s+(\d{1,2}),\s+(\d{4})", s, re.I)
    if m:
        return date(int(m[3]), _MONTHS[m[1].lower()], int(m[2]))

    raise ValueError(f"unrecognized date format: {s!r}")


# ---------------------------------------------------------------------------
# Currency detection
# ---------------------------------------------------------------------------

_CURRENCY_BY_SYMBOL = {"€": "EUR", "$": "USD", "£": "GBP", "¥": "JPY"}
_CURRENCY_CODES = {"EUR", "USD", "GBP", "JPY", "CHF", "CAD", "AUD", "MXN"}


def detect_currency(text: str) -> Optional[str]:
    for code in _CURRENCY_CODES:
        if re.search(rf"\b{code}\b", text):
            return code
    for sym, code in _CURRENCY_BY_SYMBOL.items():
        if sym in text:
            return code
    return None


# ---------------------------------------------------------------------------
# Field extraction patterns (multilingual-tolerant)
# ---------------------------------------------------------------------------

# Each pattern returns the first capture group. Tried in order; first hit wins.
PATTERNS = {
    "numero": [
        r"Factura\s+N[ºo°]?\s*[:.]?\s*(\S+)",
        r"FACTURA\s+N[ºo°]?\s*[:.]?\s*(\S+)",
        r"N[uú]mero\s+de\s+factura\s*[:.]?\s*(\S+)",
        r"Invoice\s+(?:no\.?|#|number)\s*[:.]?\s*(\S+)",
    ],
    "fecha": [
        r"Fecha\s+de\s+emisi[oó]n\s*[:.]?\s*(\S+)",
        r"Fecha\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"Issue\s+date\s*[:.]?\s*(\S+)",
        r"Date\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
    ],
}

# Money lines come at the end and must be anchored by their keyword.
MONEY_LINE = {
    "base_imponible": re.compile(
        r"(?:Base\s+imponible|Subtotal|Net(?:\s+amount)?|Importe\s+sin\s+IVA)"
        r"\s+(-?[\d.,\s]+)",
        re.I,
    ),
    "iva": re.compile(
        r"(?:IVA|I\.V\.A\.|VAT|Tax)\s*(\d+)\s*%\s+(-?[\d.,\s]+)",
        re.I,
    ),
    "irpf": re.compile(
        r"(?:Retenci[oó]n\s+IRPF|IRPF|Retention|Withholding)\s*(-?\d+)\s*%\s+(-?[\d.,\s]+)",
        re.I,
    ),
    "total": re.compile(
        r"(?:TOTAL\s+FACTURA|Total\s+factura|Importe\s+total|Total\s+a\s+pagar|"
        r"Total(?!\s+factura)|Amount\s+due)\s+(-?[\d.,\s]+)",
        re.I,
    ),
}

# Issuer/recipient blocks — the parser reads the lines that *follow* these
# headers, until a blank line or another header is hit.
ISSUER_HEADERS = [
    re.compile(r"^EMISOR\s*(?:\(proveedor\))?\s*:", re.I),
    re.compile(r"^Issuer\s*:", re.I),
    re.compile(r"^From\s*:", re.I),
]
RECIPIENT_HEADERS = [
    re.compile(r"^FACTURAR\s+A\s*:", re.I),
    re.compile(r"^Cliente\s*:", re.I),
    re.compile(r"^Bill\s+to\s*:", re.I),
]


def first_match(text: str, patterns: list[str]) -> Optional[str]:
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            return m.group(1).strip()
    return None


def block_after(lines: list[str], headers: list[re.Pattern]) -> Optional[str]:
    """Return the first non-empty line following any of the header patterns."""
    for i, raw in enumerate(lines):
        line = raw.strip()
        if any(h.search(line) for h in headers):
            for j in range(i + 1, len(lines)):
                candidate = lines[j].strip()
                if not candidate:
                    return None
                # First subsequent non-empty line is the business name
                return candidate
            return None
    return None


def extract_concept(lines: list[str]) -> Optional[str]:
    """Capture text between the CONCEPTO/IMPORTE header and the totals block."""
    started = False
    captured: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not started:
            if re.match(r"^CONCEPTO\b", line, re.I) or re.match(r"^Description\b", line, re.I):
                started = True
            continue
        # Stop at the totals row or the separator preceding it
        if MONEY_LINE["base_imponible"].search(line):
            break
        if re.match(r"^[-=_]+$", line):  # separator line
            continue
        if line:
            # Strip trailing amount on the same line ("Concept... 1.234,56 EUR")
            cleaned = re.sub(r"\s+-?[\d.,]+\s*\w*\s*$", "", line).strip()
            if cleaned:
                captured.append(cleaned)
    return " ".join(captured) if captured else None


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Warning:
    archivo: str
    field: str
    reason: str


@dataclass
class Invoice:
    archivo: str
    tipo: str
    numero: Optional[str] = None
    fecha: Optional[str] = None
    emisor: Optional[str] = None
    receptor: Optional[str] = None
    concepto: Optional[str] = None
    base_imponible: Optional[float] = None
    iva_porcentaje: Optional[int] = None
    iva_cantidad: Optional[float] = None
    irpf_porcentaje: Optional[int] = None
    irpf_cantidad: Optional[float] = None
    total: Optional[float] = None
    moneda: Optional[str] = None


# ---------------------------------------------------------------------------
# Per-PDF parsing
# ---------------------------------------------------------------------------

def parse_one(pdf_path: Path, tipo: str, project_root: Path) -> tuple[Invoice, list[Warning]]:
    abs_pdf = pdf_path.resolve()
    try:
        rel = str(abs_pdf.relative_to(project_root))
    except ValueError:
        rel = str(abs_pdf)
    invoice = Invoice(archivo=rel, tipo=tipo)
    warns: list[Warning] = []

    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)

    lines = text.splitlines()

    # --- text-field extractions ---
    invoice.numero = first_match(text, PATTERNS["numero"])
    if not invoice.numero:
        warns.append(Warning(rel, "numero", "not found"))

    fecha_raw = first_match(text, PATTERNS["fecha"])
    if fecha_raw:
        try:
            invoice.fecha = parse_date(fecha_raw).isoformat()
        except ValueError as e:
            warns.append(Warning(rel, "fecha", str(e)))
    else:
        warns.append(Warning(rel, "fecha", "not found"))

    invoice.emisor = block_after(lines, ISSUER_HEADERS)
    if not invoice.emisor:
        warns.append(Warning(rel, "emisor", "not found"))
    invoice.receptor = block_after(lines, RECIPIENT_HEADERS)
    if not invoice.receptor:
        warns.append(Warning(rel, "receptor", "not found"))

    invoice.concepto = extract_concept(lines)
    if not invoice.concepto:
        warns.append(Warning(rel, "concepto", "not found"))

    # --- money fields (find LAST occurrence — totals come after line items) ---
    def last_match(pattern: re.Pattern, target: str) -> Optional[re.Match]:
        m = None
        for hit in pattern.finditer(target):
            m = hit
        return m

    base_m = last_match(MONEY_LINE["base_imponible"], text)
    if base_m:
        try:
            invoice.base_imponible = parse_amount(base_m.group(1))
        except ValueError as e:
            warns.append(Warning(rel, "base_imponible", str(e)))
    else:
        warns.append(Warning(rel, "base_imponible", "not found"))

    iva_m = last_match(MONEY_LINE["iva"], text)
    if iva_m:
        try:
            invoice.iva_porcentaje = int(iva_m.group(1))
            invoice.iva_cantidad = parse_amount(iva_m.group(2))
        except ValueError as e:
            warns.append(Warning(rel, "iva", str(e)))

    irpf_m = last_match(MONEY_LINE["irpf"], text)
    if irpf_m:
        try:
            pct = int(irpf_m.group(1))
            invoice.irpf_porcentaje = pct if pct < 0 else -pct
            amount = parse_amount(irpf_m.group(2))
            invoice.irpf_cantidad = amount if amount <= 0 else -amount
        except ValueError as e:
            warns.append(Warning(rel, "irpf", str(e)))

    total_m = last_match(MONEY_LINE["total"], text)
    if total_m:
        try:
            invoice.total = parse_amount(total_m.group(1))
        except ValueError as e:
            warns.append(Warning(rel, "total", str(e)))
    else:
        warns.append(Warning(rel, "total", "not found"))

    invoice.moneda = detect_currency(text)
    if not invoice.moneda:
        warns.append(Warning(rel, "moneda", "not detected"))

    # --- validation: base + iva + irpf == total ---
    if invoice.base_imponible is not None and invoice.total is not None:
        computed = (
            invoice.base_imponible
            + (invoice.iva_cantidad or 0.0)
            + (invoice.irpf_cantidad or 0.0)
        )
        if abs(computed - invoice.total) > 0.01:
            warns.append(
                Warning(
                    rel,
                    "math",
                    f"base+iva+irpf={computed:.2f} != total={invoice.total:.2f}",
                )
            )

    return invoice, warns


# ---------------------------------------------------------------------------
# Issuer-of-self detection
# ---------------------------------------------------------------------------

def detect_emisor_propio(invoices: list[Invoice]) -> dict:
    """The business that appears as `emisor` in most ingreso invoices is us."""
    counts: dict[str, int] = {}
    for inv in invoices:
        if inv.tipo == "ingreso" and inv.emisor:
            counts[inv.emisor] = counts.get(inv.emisor, 0) + 1
    if not counts:
        return {"nombre": None, "cif": None}
    name = max(counts.items(), key=lambda kv: kv[1])[0]
    return {"nombre": name, "cif": None}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.option("--ingresos", type=click.Path(), help="Directory of income PDFs")
@click.option("--gastos", type=click.Path(), help="Directory of expense PDFs")
@click.option("--lang", default="en", show_default=True, help="ISO 639-1 language code")
@click.option("--out", required=True, type=click.Path(), help="Output JSON path")
@click.option("--frozen-date", default=None, help="ISO date to use for fecha_generacion (test reproducibility)")
def main(ingresos: Optional[str], gastos: Optional[str], lang: str, out: str,
          frozen_date: Optional[str]) -> None:
    # lang is accepted for forward-compatibility (future localized warnings)
    # but the parser itself is language-agnostic by design.
    del lang
    project_root = Path.cwd().resolve()
    out_path = Path(out)

    all_invoices: list[Invoice] = []
    all_warnings: list[Warning] = []

    for src, tipo in [(ingresos, "ingreso"), (gastos, "gasto")]:
        if not src:
            continue
        src_path = Path(src)
        if not src_path.exists():
            click.echo(f"skip: {src_path} does not exist", err=True)
            continue
        for pdf in sorted(src_path.glob("*.pdf")):
            inv, ws = parse_one(pdf, tipo, project_root)
            all_invoices.append(inv)
            all_warnings.extend(ws)

    if not all_invoices:
        click.echo("error: no PDFs found in --ingresos or --gastos", err=True)
        sys.exit(1)

    # Date range
    dates = sorted(inv.fecha for inv in all_invoices if inv.fecha)
    rango = f"{dates[0]} a {dates[-1]}" if dates else None

    fecha_gen = frozen_date or datetime.now().date().isoformat()
    result = {
        "fecha_generacion": fecha_gen,
        "rango": rango,
        "emisor_propio": detect_emisor_propio(all_invoices),
        "facturas": [asdict(inv) for inv in all_invoices],
        "warnings": [asdict(w) for w in all_warnings],
    }

    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    ok = len(all_invoices) - len({w.archivo for w in all_warnings})
    click.echo(f"{len(all_invoices)} invoices parsed, {ok} clean, "
               f"{len(all_warnings)} field warning(s) across "
               f"{len({w.archivo for w in all_warnings})} file(s)")


if __name__ == "__main__":
    main()
