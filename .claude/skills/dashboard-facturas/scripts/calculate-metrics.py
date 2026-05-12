#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["click>=8.1"]
# ///
"""
Deterministic metrics calculator. Consumes facturas_datos.json (from
parse-invoices.py), produces metrics.json consumed by render-dashboard.py.

All math defined in references/iva-rules.md lives here — never in the LLM.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import click


# ---------------------------------------------------------------------------
# Rounding helper — all currency math uses banker's-free cent precision
# ---------------------------------------------------------------------------

def cents(x: float) -> float:
    """Round to 2 decimals, eliminating IEEE-754 trailing noise."""
    return round(x + 0.0, 2)


# ---------------------------------------------------------------------------
# Bucketing
# ---------------------------------------------------------------------------

def month_key(iso_date: str) -> str:
    return iso_date[:7]  # "YYYY-MM"


def quarter_key(iso_date: str) -> str:
    y, m = int(iso_date[:4]), int(iso_date[5:7])
    q = (m - 1) // 3 + 1
    return f"{y}-Q{q}"


def all_months_between(start: str, end: str) -> list[str]:
    """Inclusive list of YYYY-MM keys between two ISO dates."""
    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    out: list[str] = []
    y, m = s.year, s.month
    while (y, m) <= (e.year, e.month):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            m = 1
            y += 1
    return out


# ---------------------------------------------------------------------------
# Per-currency metrics
# ---------------------------------------------------------------------------

def metrics_for_currency(invoices: list[dict], currency: str) -> dict[str, Any]:
    rows = [inv for inv in invoices if inv.get("moneda") == currency]
    ingresos = [r for r in rows if r["tipo"] == "ingreso"]
    gastos = [r for r in rows if r["tipo"] == "gasto"]

    def s(rows: list[dict], field: str) -> float:
        return cents(sum((r.get(field) or 0.0) for r in rows))

    ingresos_neto = s(ingresos, "base_imponible")
    ingresos_iva = s(ingresos, "iva_cantidad")
    ingresos_irpf = s(ingresos, "irpf_cantidad")  # negative
    ingresos_bruto = s(ingresos, "total")

    gastos_neto = s(gastos, "base_imponible")
    gastos_iva = s(gastos, "iva_cantidad")
    gastos_bruto = s(gastos, "total")

    return {
        "currency": currency,
        "ingresos_neto": ingresos_neto,
        "ingresos_bruto": ingresos_bruto,
        "gastos_neto": gastos_neto,
        "gastos_bruto": gastos_bruto,
        "balance_neto": cents(ingresos_neto - gastos_neto),
        "iva_repercutido": ingresos_iva,
        "iva_soportado": gastos_iva,
        "iva_a_liquidar": cents(ingresos_iva - gastos_iva),
        "irpf_retenido": cents(-ingresos_irpf),  # report as positive amount withheld
        "factura_media": cents(ingresos_neto / len(ingresos)) if ingresos else 0.0,
        "count_ingresos": len(ingresos),
        "count_gastos": len(gastos),
        "client_count": len({r.get("receptor") for r in ingresos if r.get("receptor")}),
    }


def monthly_evolution(invoices: list[dict], currency: str,
                       start: str, end: str) -> list[dict]:
    by_month_ing: dict[str, float] = defaultdict(float)
    by_month_gas: dict[str, float] = defaultdict(float)
    for inv in invoices:
        if inv.get("moneda") != currency or not inv.get("fecha"):
            continue
        mk = month_key(inv["fecha"])
        if inv["tipo"] == "ingreso":
            by_month_ing[mk] += inv.get("base_imponible") or 0.0
        else:
            by_month_gas[mk] += inv.get("base_imponible") or 0.0

    return [
        {
            "month": mk,
            "ingresos_neto": cents(by_month_ing.get(mk, 0.0)),
            "gastos_neto": cents(by_month_gas.get(mk, 0.0)),
        }
        for mk in all_months_between(start, end)
    ]


def quarterly_vat(invoices: list[dict], currency: str) -> list[dict]:
    by_q_collected: dict[str, float] = defaultdict(float)
    by_q_paid: dict[str, float] = defaultdict(float)
    quarters: set[str] = set()
    for inv in invoices:
        if inv.get("moneda") != currency or not inv.get("fecha"):
            continue
        qk = quarter_key(inv["fecha"])
        quarters.add(qk)
        if inv["tipo"] == "ingreso":
            by_q_collected[qk] += inv.get("iva_cantidad") or 0.0
        else:
            by_q_paid[qk] += inv.get("iva_cantidad") or 0.0

    return [
        {
            "quarter": q,
            "iva_collected": cents(by_q_collected.get(q, 0.0)),
            "iva_paid": cents(by_q_paid.get(q, 0.0)),
            "iva_net": cents(by_q_collected.get(q, 0.0) - by_q_paid.get(q, 0.0)),
        }
        for q in sorted(quarters)
    ]


def top_clients(invoices: list[dict], currency: str, limit: int = 10) -> list[dict]:
    by_client_revenue: dict[str, float] = defaultdict(float)
    by_client_count: dict[str, int] = defaultdict(int)
    for inv in invoices:
        if inv.get("moneda") != currency or inv["tipo"] != "ingreso":
            continue
        client = inv.get("receptor")
        if not client:
            continue
        by_client_revenue[client] += inv.get("base_imponible") or 0.0
        by_client_count[client] += 1

    total = sum(by_client_revenue.values())
    rows = [
        {
            "client": c,
            "invoice_count": by_client_count[c],
            "net_revenue": cents(rev),
            "pct": cents(rev / total * 100) if total > 0 else 0.0,
        }
        for c, rev in sorted(by_client_revenue.items(),
                              key=lambda kv: kv[1], reverse=True)
    ]
    return rows[:limit]


def detect_trend(monthly: list[dict]) -> dict | None:
    """Compare last 3 months of ingresos_neto to the 3 prior months."""
    if len(monthly) < 6:
        return None
    recent = sum(m["ingresos_neto"] for m in monthly[-3:])
    prior = sum(m["ingresos_neto"] for m in monthly[-6:-3])
    if prior <= 0:
        return None
    pct = (recent - prior) / prior * 100
    if pct >= 10:
        return {"direction": "up", "pct": cents(pct)}
    if pct <= -10:
        return {"direction": "down", "pct": cents(pct)}
    return {"direction": "flat", "pct": cents(pct)}


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

def build_alerts(invoices: list[dict], by_currency: dict[str, dict],
                 currencies: list[str]) -> list[dict]:
    alerts: list[dict] = []

    if len(currencies) > 1:
        alerts.append({"key": "mixed_currency", "params": {}})

    for cur in currencies:
        clients = top_clients(invoices, cur, limit=1)
        if clients and clients[0]["pct"] >= 40:
            alerts.append({
                "key": "client_dependency",
                "params": {"client": clients[0]["client"], "pct": clients[0]["pct"]},
            })

        monthly = by_currency[cur]["monthly_evolution"]
        zero_months = [
            m["month"] for m in monthly
            if m["ingresos_neto"] == 0 and m["gastos_neto"] == 0
        ]
        for m in zero_months:
            alerts.append({"key": "month_no_billing", "params": {"month": m}})

        trend = by_currency[cur].get("trend")
        if trend:
            if trend["direction"] == "up":
                alerts.append({"key": "trend_up", "params": {"pct": trend["pct"]}})
            elif trend["direction"] == "down":
                alerts.append({"key": "trend_down", "params": {"pct": abs(trend["pct"])}})
            else:
                alerts.append({"key": "trend_flat", "params": {}})

    missing_iva = sum(
        1 for inv in invoices
        if inv["tipo"] == "ingreso" and inv.get("iva_cantidad") is None
    )
    if missing_iva:
        alerts.append({"key": "missing_iva", "params": {"count": missing_iva}})

    return alerts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.option("--in", "input_path", required=True, type=click.Path(exists=True))
@click.option("--lang", default="en", show_default=True)
@click.option("--out", required=True, type=click.Path())
def main(input_path: str, lang: str, out: str) -> None:
    data = json.loads(Path(input_path).read_text(encoding="utf-8"))
    invoices: list[dict] = data["facturas"]

    if not invoices:
        click.echo("error: facturas list is empty", err=True)
        sys.exit(1)

    dates = sorted([inv["fecha"] for inv in invoices if inv.get("fecha")])
    period = {"start": dates[0], "end": dates[-1]} if dates else None
    currencies = sorted({inv.get("moneda") for inv in invoices if inv.get("moneda")})

    by_currency: dict[str, dict] = {}
    for cur in currencies:
        m = metrics_for_currency(invoices, cur)
        m["monthly_evolution"] = monthly_evolution(invoices, cur,
                                                     period["start"], period["end"])
        m["quarterly_vat"] = quarterly_vat(invoices, cur)
        m["top_clients"] = top_clients(invoices, cur)
        m["trend"] = detect_trend(m["monthly_evolution"])
        by_currency[cur] = m

    metrics = {
        "lang": lang,
        "company": data.get("emisor_propio", {}).get("nombre"),
        "period": period,
        "count_total": len(invoices),
        "count_ingresos": sum(1 for i in invoices if i["tipo"] == "ingreso"),
        "count_gastos": sum(1 for i in invoices if i["tipo"] == "gasto"),
        "currencies": currencies,
        "by_currency": by_currency,
        "alerts": build_alerts(invoices, by_currency, currencies),
        "source_warnings": data.get("warnings", []),
    }

    Path(out).write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    click.echo(f"metrics written: {len(currencies)} currency/currencies, "
               f"{len(metrics['alerts'])} alert(s)")


if __name__ == "__main__":
    main()
