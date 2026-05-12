"""Black-box tests for parse-invoices.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import (
    GROUND_TRUTH, INGRESOS, GASTOS, SCRIPTS, FROZEN_DATE,
    run, load, normalize_invoice,
)


# ---------------------------------------------------------------------------
# Happy path — full fixture set vs. ground truth
# ---------------------------------------------------------------------------

def test_parses_all_16_fixtures_with_no_warnings(parsed_json: Path):
    data = load(parsed_json)
    assert len(data["facturas"]) == 16
    assert data["warnings"] == []
    assert data["fecha_generacion"] == FROZEN_DATE


def test_ingreso_gasto_counts(parsed_json: Path):
    data = load(parsed_json)
    ingresos = [i for i in data["facturas"] if i["tipo"] == "ingreso"]
    gastos = [i for i in data["facturas"] if i["tipo"] == "gasto"]
    assert len(ingresos) == 10
    assert len(gastos) == 6


def test_per_invoice_math_balances(parsed_json: Path):
    """For every invoice, base + iva + irpf must equal total within 1 cent."""
    data = load(parsed_json)
    for inv in data["facturas"]:
        computed = (
            (inv["base_imponible"] or 0.0)
            + (inv["iva_cantidad"] or 0.0)
            + (inv["irpf_cantidad"] or 0.0)
        )
        assert abs(computed - inv["total"]) <= 0.01, (
            f"{inv['archivo']}: base+iva+irpf={computed:.2f} != total={inv['total']:.2f}"
        )


def test_semantic_match_against_ground_truth(parsed_json: Path):
    """Every field on every invoice equals the bundled ground truth."""
    actual = sorted(load(parsed_json)["facturas"], key=lambda i: i["numero"])
    expected = sorted(load(GROUND_TRUTH)["facturas"], key=lambda i: i["numero"])
    assert len(actual) == len(expected)
    for a, e in zip(actual, expected):
        assert normalize_invoice(a) == normalize_invoice(e), (
            f"diff at invoice {a['numero']}"
        )


def test_emisor_propio_detected(parsed_json: Path):
    data = load(parsed_json)
    assert data["emisor_propio"]["nombre"] == "Estudio Creativo Vega SL"


def test_date_range(parsed_json: Path):
    data = load(parsed_json)
    assert data["rango"] == "2025-10-01 a 2026-03-20"


def test_all_currency_eur(parsed_json: Path):
    data = load(parsed_json)
    assert {i["moneda"] for i in data["facturas"]} == {"EUR"}


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_only_ingresos(tmp_path: Path):
    """Parser must work when only one folder is supplied."""
    out = tmp_path / "out.json"
    run([
        SCRIPTS / "parse-invoices.py",
        "--ingresos", INGRESOS,
        "--lang", "en",
        "--frozen-date", FROZEN_DATE,
        "--out", out,
    ])
    data = load(out)
    assert len(data["facturas"]) == 10
    assert all(i["tipo"] == "ingreso" for i in data["facturas"])


def test_only_gastos(tmp_path: Path):
    out = tmp_path / "out.json"
    run([
        SCRIPTS / "parse-invoices.py",
        "--gastos", GASTOS,
        "--lang", "en",
        "--frozen-date", FROZEN_DATE,
        "--out", out,
    ])
    data = load(out)
    assert len(data["facturas"]) == 6
    assert all(i["tipo"] == "gasto" for i in data["facturas"])


def test_empty_folder_exits_nonzero(tmp_path: Path):
    import subprocess
    empty = tmp_path / "empty"
    empty.mkdir()
    out = tmp_path / "out.json"
    result = subprocess.run(
        [str(SCRIPTS / "parse-invoices.py"),
         "--ingresos", str(empty),
         "--lang", "en",
         "--out", str(out)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "no PDFs" in result.stderr


def test_idempotent(tmp_path: Path):
    """Same inputs + same --frozen-date → byte-identical output."""
    out1 = tmp_path / "a.json"
    out2 = tmp_path / "b.json"
    for out in (out1, out2):
        run([
            SCRIPTS / "parse-invoices.py",
            "--ingresos", INGRESOS, "--gastos", GASTOS,
            "--lang", "en", "--frozen-date", FROZEN_DATE,
            "--out", out,
        ])
    assert out1.read_bytes() == out2.read_bytes()


# ---------------------------------------------------------------------------
# Number parsing — exercised via a hand-crafted input via the helper module.
# These check internal parsing primitives without subprocess overhead.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def parser_module():
    """Import parse-invoices.py as a module, bypassing the click CLI."""
    import importlib.util
    import sys
    path = SCRIPTS / "parse-invoices.py"
    spec = importlib.util.spec_from_file_location("parse_invoices", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    # Register before exec so @dataclass can resolve cls.__module__
    sys.modules["parse_invoices"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("raw,expected", [
    ("1.800,00", 1800.0),
    ("1,800.00", 1800.0),
    ("59,99", 59.99),
    ("59.99", 59.99),
    ("-270,00", -270.0),
    ("12 345,67", 12345.67),
    ("1.234.567,89", 1234567.89),
])
def test_parse_amount(parser_module, raw, expected):
    assert parser_module.parse_amount(raw) == pytest.approx(expected)


@pytest.mark.parametrize("raw,expected", [
    ("2025-10-12", "2025-10-12"),
    ("12/10/2025", "2025-10-12"),
    ("12-10-2025", "2025-10-12"),
    ("12 de octubre de 2025", "2025-10-12"),
    ("October 12, 2025", "2025-10-12"),
])
def test_parse_date(parser_module, raw, expected):
    assert parser_module.parse_date(raw).isoformat() == expected
