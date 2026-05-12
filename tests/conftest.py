"""Shared pytest fixtures and constants."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

KIT_ROOT = Path(__file__).parent.parent.resolve()
SKILL_ROOT = KIT_ROOT / ".claude" / "skills" / "dashboard-facturas"
SCRIPTS = SKILL_ROOT / "scripts"
ASSETS = SKILL_ROOT / "assets"
LOCALES = ASSETS / "locales"
TEMPLATE = ASSETS / "dashboard-template.html"

FIXTURES = KIT_ROOT / "tests" / "fixtures"
INGRESOS = FIXTURES / "ingresos"
GASTOS = FIXTURES / "gastos"
GROUND_TRUTH = FIXTURES / "expected-facturas-datos.json"

FROZEN_DATE = "2026-05-12"  # any fixed date — tests don't care which


def run(cmd: list[str | Path], **kwargs) -> subprocess.CompletedProcess:
    """Run a subprocess, fail the test loudly if non-zero exit."""
    result = subprocess.run(
        [str(c) for c in cmd],
        capture_output=True,
        text=True,
        cwd=KIT_ROOT,
        **kwargs,
    )
    if result.returncode != 0:
        pytest.fail(
            f"command failed (exit {result.returncode})\n"
            f"  cmd: {' '.join(str(c) for c in cmd)}\n"
            f"  stderr: {result.stderr}\n"
            f"  stdout: {result.stdout}"
        )
    return result


@pytest.fixture
def parsed_json(tmp_path: Path) -> Path:
    """Parser output for the full fixture set. Cached per-test via tmp_path."""
    out = tmp_path / "facturas_datos.json"
    run([
        SCRIPTS / "parse-invoices.py",
        "--ingresos", INGRESOS,
        "--gastos", GASTOS,
        "--lang", "en",
        "--frozen-date", FROZEN_DATE,
        "--out", out,
    ])
    return out


@pytest.fixture
def metrics_json(parsed_json: Path, tmp_path: Path) -> Path:
    out = tmp_path / "metrics.json"
    run([
        SCRIPTS / "calculate-metrics.py",
        "--in", parsed_json,
        "--lang", "en",
        "--out", out,
    ])
    return out


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_invoice(inv: dict) -> dict:
    """Strip cosmetic differences (trailing zeros, null-vs-0 for absent IRPF)."""
    def num(x):
        if x is None:
            return 0.0
        return round(float(x), 2)
    return {
        "tipo": inv["tipo"],
        "numero": inv["numero"],
        "fecha": inv["fecha"],
        "emisor": inv["emisor"],
        "receptor": inv["receptor"],
        "base_imponible": num(inv["base_imponible"]),
        "iva_porcentaje": inv.get("iva_porcentaje"),
        "iva_cantidad": num(inv.get("iva_cantidad")),
        "irpf_porcentaje": inv.get("irpf_porcentaje") or 0,
        "irpf_cantidad": num(inv.get("irpf_cantidad")),
        "total": num(inv["total"]),
        "moneda": inv["moneda"],
    }
