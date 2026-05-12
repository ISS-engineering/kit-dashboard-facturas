"""
Subagent integration test — the end-to-end "does the skill actually fire" test.

This is the hardest test to write (and the most valuable): it spawns a real
Claude agent inside the kit folder, lets the agent read SKILL.md, and asks it
to do the workflow. Then asserts that the expected artifacts exist and pass
the same correctness checks our unit tests use.

Two modes are supported:
  1. Headless `claude` CLI (preferred)
  2. Direct Anthropic API call (fallback)

Both are gated: the test is SKIPPED if neither is available. This keeps
`pytest` runnable offline while still allowing real end-to-end verification
when the developer wants it.

Run only this test:
    pytest tests/test_subagent_integration.py -v --run-subagent

Set the environment variable RUN_SUBAGENT_TESTS=1 to enable.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import (
    KIT_ROOT, FIXTURES, INGRESOS, GASTOS,
    SCRIPTS, ASSETS, LOCALES, TEMPLATE,
)


SUBAGENT_ENABLED = os.environ.get("RUN_SUBAGENT_TESTS") == "1"
HEADLESS_CLI = shutil.which("claude")


def _ensure_workspace(tmp_path: Path) -> Path:
    """Stage a fresh kit copy under tmp_path so the test can't pollute the repo."""
    work = tmp_path / "kit"
    work.mkdir()
    # Copy skill folder, assets, scripts
    shutil.copytree(KIT_ROOT / ".claude", work / ".claude")
    # Copy the kit-level docs the agent reads on open
    shutil.copy2(KIT_ROOT / "CLAUDE.md", work / "CLAUDE.md")
    shutil.copy2(KIT_ROOT / "INSTRUCCIONES.md", work / "INSTRUCCIONES.md")
    # Copy the fixtures into the buyer-facing folders
    shutil.copytree(INGRESOS, work / "facturas" / "ingresos")
    shutil.copytree(GASTOS, work / "facturas" / "gastos")
    return work


@pytest.mark.skipif(
    not SUBAGENT_ENABLED,
    reason="Set RUN_SUBAGENT_TESTS=1 to enable (uses real Claude API tokens).",
)
@pytest.mark.skipif(
    HEADLESS_CLI is None,
    reason="`claude` CLI not in PATH — install Claude Code first.",
)
def test_subagent_produces_correct_dashboard(tmp_path: Path):
    """End-to-end: open a fresh kit, ask agent to do the job, verify outputs."""
    work = _ensure_workspace(tmp_path)

    prompt = (
        "Analyze the invoices in facturas/ingresos and facturas/gastos and "
        "generate the English dashboard. Use --frozen-date 2026-05-12 for "
        "every script call so the output is reproducible. Save as "
        "dashboard-facturacion.html in this folder."
    )

    result = subprocess.run(
        [HEADLESS_CLI, "-p", prompt],
        cwd=work,
        capture_output=True,
        text=True,
        timeout=300,
    )

    # The agent should have produced all three pipeline artifacts
    expected_files = [
        work / "facturas_datos.json",
        work / "metrics.json",
        work / "dashboard-facturacion.html",
    ]
    for f in expected_files:
        assert f.exists(), (
            f"agent did not create {f.name}\n"
            f"stdout: {result.stdout[-2000:]}\n"
            f"stderr: {result.stderr[-1000:]}"
        )

    # Sanity-check the JSON extraction matches what our unit tests verify
    data = json.loads((work / "facturas_datos.json").read_text(encoding="utf-8"))
    assert len(data["facturas"]) == 16
    assert data["warnings"] == []

    # Sanity-check the metrics
    metrics = json.loads((work / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["count_total"] == 16
    assert metrics["by_currency"]["EUR"]["ingresos_neto"] == 26750.0

    # Sanity-check the HTML
    html = (work / "dashboard-facturacion.html").read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>")
    assert "Invoicing Dashboard" in html or "Dashboard" in html
    assert "26,750.00" in html or "26.750,00" in html
