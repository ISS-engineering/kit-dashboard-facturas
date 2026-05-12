"""Black-box tests for calculate-metrics.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import SCRIPTS, run, load


# ---------------------------------------------------------------------------
# Top-line totals (manually verified against ground-truth invoices)
# ---------------------------------------------------------------------------

def test_top_level_shape(metrics_json: Path):
    m = load(metrics_json)
    assert m["count_total"] == 16
    assert m["count_ingresos"] == 10
    assert m["count_gastos"] == 6
    assert m["currencies"] == ["EUR"]
    assert m["company"] == "Estudio Creativo Vega SL"


def test_eur_totals(metrics_json: Path):
    eur = load(metrics_json)["by_currency"]["EUR"]
    assert eur["ingresos_neto"] == 26750.0
    assert eur["ingresos_bruto"] == 28355.0
    assert eur["gastos_neto"] == 588.63
    assert eur["gastos_bruto"] == 712.24
    assert eur["balance_neto"] == pytest.approx(26750.0 - 588.63, abs=0.01)


def test_vat_settlement(metrics_json: Path):
    eur = load(metrics_json)["by_currency"]["EUR"]
    # Collected − paid = settle
    assert eur["iva_a_liquidar"] == pytest.approx(
        eur["iva_repercutido"] - eur["iva_soportado"], abs=0.01
    )


def test_irpf_is_15pct_of_ingresos_neto(metrics_json: Path):
    """Fixture data: every income invoice has IRPF -15%."""
    eur = load(metrics_json)["by_currency"]["EUR"]
    assert eur["irpf_retenido"] == pytest.approx(eur["ingresos_neto"] * 0.15, abs=0.01)


def test_factura_media(metrics_json: Path):
    eur = load(metrics_json)["by_currency"]["EUR"]
    assert eur["factura_media"] == pytest.approx(eur["ingresos_neto"] / 10, abs=0.01)


# ---------------------------------------------------------------------------
# Quarterly bucketing
# ---------------------------------------------------------------------------

def test_quarterly_buckets(metrics_json: Path):
    qs = load(metrics_json)["by_currency"]["EUR"]["quarterly_vat"]
    assert [q["quarter"] for q in qs] == ["2025-Q4", "2026-Q1"]

    # Each quarter's net = collected − paid
    for q in qs:
        assert q["iva_net"] == pytest.approx(
            q["iva_collected"] - q["iva_paid"], abs=0.01
        )


def test_quarterly_totals_sum_to_yearly(metrics_json: Path):
    eur = load(metrics_json)["by_currency"]["EUR"]
    qs = eur["quarterly_vat"]
    assert sum(q["iva_collected"] for q in qs) == pytest.approx(
        eur["iva_repercutido"], abs=0.01
    )
    assert sum(q["iva_paid"] for q in qs) == pytest.approx(
        eur["iva_soportado"], abs=0.01
    )


# ---------------------------------------------------------------------------
# Top clients
# ---------------------------------------------------------------------------

def test_top_clients_sorted_desc(metrics_json: Path):
    clients = load(metrics_json)["by_currency"]["EUR"]["top_clients"]
    revenues = [c["net_revenue"] for c in clients]
    assert revenues == sorted(revenues, reverse=True)


def test_top_clients_percentages_sum_to_100(metrics_json: Path):
    clients = load(metrics_json)["by_currency"]["EUR"]["top_clients"]
    total_pct = sum(c["pct"] for c in clients)
    # Allow 0.1pp rounding slack since each pct is rounded to 2 decimals
    assert total_pct == pytest.approx(100.0, abs=0.1)


def test_top_client_below_dependency_threshold(metrics_json: Path):
    """Fixture data has no client ≥ 40%, so no client_dependency alert."""
    m = load(metrics_json)
    keys = [a["key"] for a in m["alerts"]]
    assert "client_dependency" not in keys


# ---------------------------------------------------------------------------
# Monthly evolution
# ---------------------------------------------------------------------------

def test_monthly_evolution_covers_period(metrics_json: Path):
    """Should have one entry per month from Oct 2025 to Mar 2026 (6 months)."""
    months = load(metrics_json)["by_currency"]["EUR"]["monthly_evolution"]
    assert [m["month"] for m in months] == [
        "2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03",
    ]


def test_monthly_totals_match_yearly(metrics_json: Path):
    eur = load(metrics_json)["by_currency"]["EUR"]
    ing_sum = sum(m["ingresos_neto"] for m in eur["monthly_evolution"])
    gas_sum = sum(m["gastos_neto"] for m in eur["monthly_evolution"])
    assert ing_sum == pytest.approx(eur["ingresos_neto"], abs=0.01)
    assert gas_sum == pytest.approx(eur["gastos_neto"], abs=0.01)


# ---------------------------------------------------------------------------
# Trend
# ---------------------------------------------------------------------------

def test_trend_detected(metrics_json: Path):
    """Fixture has rising revenue Q4-2025 → Q1-2026, expect trend_up."""
    trend = load(metrics_json)["by_currency"]["EUR"]["trend"]
    assert trend is not None
    assert trend["direction"] == "up"
    assert trend["pct"] > 10


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def test_idempotent(parsed_json: Path, tmp_path: Path):
    out1 = tmp_path / "m1.json"
    out2 = tmp_path / "m2.json"
    for out in (out1, out2):
        run([SCRIPTS / "calculate-metrics.py",
             "--in", parsed_json, "--lang", "en", "--out", out])
    assert out1.read_bytes() == out2.read_bytes()
