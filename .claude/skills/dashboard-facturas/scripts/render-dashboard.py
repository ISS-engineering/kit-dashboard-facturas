#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["jinja2>=3.1", "babel>=2.14", "click>=8.1"]
# ///
"""
Render the HTML dashboard from metrics + invoices + locale + template.

Inputs:
  --metrics PATH    metrics.json (from calculate-metrics.py)
  --invoices PATH   facturas_datos.json (for the detail table)
  --lang CODE       ISO 639-1 (en/es/de/fr/it)
  --template PATH   assets/dashboard-template.html
  --locales PATH    assets/locales/ directory
  --out PATH        output HTML file

Idempotent: same inputs → byte-identical output.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import click
from babel.dates import format_date
from babel.numbers import format_currency
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape


# ---------------------------------------------------------------------------
# Locale loading and validation
# ---------------------------------------------------------------------------

def load_locale(locales_dir: Path, lang: str) -> dict[str, Any]:
    path = locales_dir / f"{lang}.json"
    if not path.exists():
        available = sorted(p.stem for p in locales_dir.glob("*.json"))
        click.echo(f"error: locale {lang!r} not found. Available: {available}", err=True)
        sys.exit(1)
    return json.loads(path.read_text(encoding="utf-8"))


def validate_locale(locale: dict[str, Any], canonical: dict[str, Any]) -> None:
    """Recursively ensure `locale` has every key `canonical` has."""
    def walk(a: Any, b: Any, path: str) -> list[str]:
        problems: list[str] = []
        if isinstance(b, dict):
            if not isinstance(a, dict):
                problems.append(f"{path}: expected object")
                return problems
            for k in b:
                if k not in a:
                    problems.append(f"{path}.{k}: missing")
                else:
                    problems.extend(walk(a[k], b[k], f"{path}.{k}"))
        return problems

    problems = walk(locale, canonical, "<root>")
    if problems:
        click.echo("locale validation failed:", err=True)
        for p in problems:
            click.echo(f"  {p}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Jinja env with babel-powered filters
# ---------------------------------------------------------------------------

def make_env(template_dir: Path, formatting_locale: str) -> Environment:
    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(["html"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    def money(amount: float | int | None, currency: str = "EUR") -> str:
        if amount is None:
            return ""
        return format_currency(amount, currency, locale=formatting_locale)

    def fdate(iso: str) -> str:
        if not iso:
            return ""
        try:
            return format_date(date.fromisoformat(iso), format="medium",
                                locale=formatting_locale)
        except ValueError:
            return iso

    def fmonth(yyyy_mm: str) -> str:
        try:
            y, m = yyyy_mm.split("-")
            return format_date(date(int(y), int(m), 1), format="MMM yyyy",
                                locale=formatting_locale)
        except (ValueError, TypeError):
            return yyyy_mm

    def fpct(value: float | int | None) -> str:
        if value is None:
            return ""
        return f"{value:.1f}%"

    env.filters["money"] = money
    env.filters["fdate"] = fdate
    env.filters["fmonth"] = fmonth
    env.filters["fpct"] = fpct
    return env


# ---------------------------------------------------------------------------
# Alert rendering
# ---------------------------------------------------------------------------

def render_alerts(alerts: list[dict], t_alerts: dict[str, str]) -> list[str]:
    rendered: list[str] = []
    for a in alerts:
        template = t_alerts.get(a["key"])
        if not template:
            continue
        try:
            rendered.append(template.format(**a["params"]))
        except (KeyError, IndexError):
            rendered.append(template)
    return rendered


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.option("--metrics", required=True, type=click.Path(exists=True))
@click.option("--invoices", required=True, type=click.Path(exists=True))
@click.option("--lang", default="en", show_default=True)
@click.option("--template", required=True, type=click.Path(exists=True))
@click.option("--locales", required=True, type=click.Path(exists=True, file_okay=False))
@click.option("--out", required=True, type=click.Path())
@click.option("--frozen-date", default=None, help="ISO date for generated_at (test reproducibility)")
def main(metrics: str, invoices: str, lang: str,
         template: str, locales: str, out: str, frozen_date: str | None) -> None:
    metrics_data = json.loads(Path(metrics).read_text(encoding="utf-8"))
    invoices_data = json.loads(Path(invoices).read_text(encoding="utf-8"))

    locales_dir = Path(locales)
    canonical = load_locale(locales_dir, "en")
    locale = load_locale(locales_dir, lang) if lang != "en" else canonical
    validate_locale(locale, canonical)

    template_path = Path(template)
    env = make_env(template_path.parent, locale["formatting_locale"])
    tpl = env.get_template(template_path.name)

    rendered_alerts = render_alerts(metrics_data.get("alerts", []), locale["ui"]["alerts"])

    html = tpl.render(
        t=locale["ui"],
        lang_code=locale["lang_code"],
        company=metrics_data.get("company") or "—",
        period=metrics_data.get("period") or {"start": "", "end": ""},
        count_total=metrics_data.get("count_total", 0),
        count_ingresos=metrics_data.get("count_ingresos", 0),
        count_gastos=metrics_data.get("count_gastos", 0),
        currencies=metrics_data.get("currencies", []),
        by_currency=metrics_data.get("by_currency", {}),
        invoices=invoices_data.get("facturas", []),
        alerts=rendered_alerts,
        generated_at=frozen_date or datetime.now().date().isoformat(),
    )
    Path(out).write_text(html, encoding="utf-8")
    click.echo(f"dashboard written: {out} (lang={lang})")


if __name__ == "__main__":
    main()
