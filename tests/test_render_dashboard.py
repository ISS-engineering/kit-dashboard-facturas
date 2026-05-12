"""Black-box tests for render-dashboard.py."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from conftest import (
    SCRIPTS, TEMPLATE, LOCALES, FROZEN_DATE, run,
)


@pytest.fixture
def render(metrics_json: Path, parsed_json: Path, tmp_path: Path):
    """Render the dashboard for a given language and return its path + content."""
    def _render(lang: str) -> tuple[Path, str]:
        out = tmp_path / f"dashboard-{lang}.html"
        run([
            SCRIPTS / "render-dashboard.py",
            "--metrics", metrics_json,
            "--invoices", parsed_json,
            "--lang", lang,
            "--template", TEMPLATE,
            "--locales", LOCALES,
            "--frozen-date", FROZEN_DATE,
            "--out", out,
        ])
        return out, out.read_text(encoding="utf-8")
    return _render


# ---------------------------------------------------------------------------
# All 5 languages render and produce valid HTML
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("lang", ["en", "es", "de", "fr", "it"])
def test_renders_in_each_supported_language(render, lang):
    path, html = render(lang)
    assert path.exists()
    assert html.startswith("<!doctype html>")
    assert f'<html lang="{lang}">' in html
    assert "</html>" in html


# ---------------------------------------------------------------------------
# Language-specific label assertions
# ---------------------------------------------------------------------------

LABEL_PROBES = {
    "en": ["Invoicing Dashboard", "VAT collected", "Top clients by revenue"],
    "es": ["Dashboard de facturación", "IVA repercutido", "Top clientes por facturación"],
    "de": ["Rechnungs-Dashboard", "MwSt. eingenommen", "Top-Kunden nach Umsatz"],
    "fr": ["Tableau de bord de facturation", "TVA collectée", "Meilleurs clients par chiffre"],
    "it": ["Dashboard di fatturazione", "IVA a debito", "Migliori clienti per fatturato"],
}


@pytest.mark.parametrize("lang,probes", LABEL_PROBES.items())
def test_localized_labels_present(render, lang, probes):
    _, html = render(lang)
    for probe in probes:
        assert probe in html, f"missing {probe!r} in {lang} dashboard"


# ---------------------------------------------------------------------------
# Number formatting per locale (en vs eu)
# ---------------------------------------------------------------------------

def test_us_number_format_in_english(render):
    _, html = render("en")
    # 26 750 should render as €26,750.00 (US thousands sep)
    assert "€26,750.00" in html


@pytest.mark.parametrize("lang", ["es", "de", "fr", "it"])
def test_european_number_format(render, lang):
    _, html = render(lang)
    # European locales use various thousands separators: '.', space, NBSP, narrow NBSP.
    # The regex character class \s + literal '.' covers them all.
    pattern = re.compile(r"26[.\s]750,00")
    assert pattern.search(html), (
        f"european number format not found in {lang} dashboard"
    )


# ---------------------------------------------------------------------------
# Locale validation
# ---------------------------------------------------------------------------

def test_unknown_lang_fails(tmp_path: Path, metrics_json: Path, parsed_json: Path):
    out = tmp_path / "x.html"
    result = subprocess.run(
        [str(SCRIPTS / "render-dashboard.py"),
         "--metrics", str(metrics_json),
         "--invoices", str(parsed_json),
         "--lang", "xx",
         "--template", str(TEMPLATE),
         "--locales", str(LOCALES),
         "--out", str(out)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "not found" in result.stderr


def test_all_locales_validate_against_canonical_en():
    """Every locale must define every key that en.json defines."""
    en = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))

    def keys(obj, prefix=""):
        out = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                out.append(f"{prefix}.{k}".lstrip("."))
                out.extend(keys(v, f"{prefix}.{k}"))
        return out

    canonical_keys = set(keys(en))
    for locale_file in LOCALES.glob("*.json"):
        loc = json.loads(locale_file.read_text(encoding="utf-8"))
        loc_keys = set(keys(loc))
        missing = canonical_keys - loc_keys
        assert not missing, f"{locale_file.name} is missing keys: {sorted(missing)}"


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def test_idempotent_within_same_frozen_date(metrics_json: Path, parsed_json: Path,
                                              tmp_path: Path):
    a = tmp_path / "a.html"
    b = tmp_path / "b.html"
    for out in (a, b):
        run([
            SCRIPTS / "render-dashboard.py",
            "--metrics", metrics_json, "--invoices", parsed_json,
            "--lang", "en",
            "--template", TEMPLATE, "--locales", LOCALES,
            "--frozen-date", FROZEN_DATE,
            "--out", out,
        ])
    assert a.read_bytes() == b.read_bytes()
