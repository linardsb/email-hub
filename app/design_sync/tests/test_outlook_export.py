"""Tests for scripts/export-outlook-cases.py (CE-4 part 1).

Run over the real committed cases: the export must leave no API-only asset ref,
copy every referenced asset, and change nothing in the markup but those refs.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path
from typing import Any, NamedTuple

import pytest

from app.design_sync.fidelity_gate import DEBUG_DIR, gated_cases
from app.design_sync.tests.regression_runner import run_case_conversion

_API_PREFIX = "/api/v1/design-sync/assets/"
_BASE_URL = "https://cdn.example.test/ce4/5"


def _export_script() -> Any:
    path = Path(__file__).resolve().parents[3] / "scripts" / "export-outlook-cases.py"
    spec = importlib.util.spec_from_file_location("export_outlook_cases", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CaseExport(NamedTuple):
    converter_html: str
    rel_dir: Path
    rel_row: dict[str, Any]
    abs_dir: Path
    abs_row: dict[str, Any]


@pytest.fixture(scope="module")
def exports(tmp_path_factory: pytest.TempPathFactory) -> dict[str, CaseExport]:
    script = _export_script()
    rel_out = tmp_path_factory.mktemp("rel")
    abs_out = tmp_path_factory.mktemp("abs")
    result: dict[str, CaseExport] = {}
    for case in gated_cases():
        converted = run_case_conversion(DEBUG_DIR / case)
        if converted is None:
            continue
        rel_row = script.export_case(case, rel_out)
        abs_row = script.export_case(case, abs_out, asset_base_url=_BASE_URL)
        result[case] = CaseExport(converted.html, rel_out / case, rel_row, abs_out / case, abs_row)
    return result


def _get(exports: dict[str, CaseExport], case: str) -> CaseExport:
    if case not in exports:
        pytest.skip(f"case {case}: structure.json or tokens.json missing")
    return exports[case]


@pytest.mark.parametrize("case", gated_cases())
def test_no_api_asset_ref_survives(exports: dict[str, CaseExport], case: str) -> None:
    exp = _get(exports, case)
    assert _API_PREFIX in exp.converter_html
    assert _API_PREFIX not in (exp.rel_dir / "email.html").read_text(encoding="utf-8")
    assert _API_PREFIX not in (exp.abs_dir / "email.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("case", gated_cases())
def test_every_relative_src_has_a_copied_file(exports: dict[str, CaseExport], case: str) -> None:
    exp = _get(exports, case)
    html = (exp.rel_dir / "email.html").read_text(encoding="utf-8")
    refs = re.findall(r"assets/([^\"')\s]+?\.png)", html)
    assert refs
    for name in refs:
        assert (exp.rel_dir / "assets" / name).is_file(), name
    assert exp.rel_row["missing_assets"] == []


@pytest.mark.parametrize("case", gated_cases())
def test_base_url_mode_rewrites_absolute(exports: dict[str, CaseExport], case: str) -> None:
    exp = _get(exports, case)
    html = (exp.abs_dir / "email.html").read_text(encoding="utf-8")
    refs = re.findall(re.escape(_BASE_URL) + r"/[^\"')\s]+", html)
    assert len(refs) == exp.converter_html.count(_API_PREFIX)
    assert all(ref.endswith(".png") for ref in refs)


@pytest.mark.parametrize("case", gated_cases())
def test_markup_unchanged_except_asset_refs(exports: dict[str, CaseExport], case: str) -> None:
    exp = _get(exports, case)
    exported = (exp.rel_dir / "email.html").read_text(encoding="utf-8")
    before = re.split(r"/api/v1/design-sync/assets/[^\"')\s]+?\.png", exp.converter_html)
    after = re.split(r"assets/[^\"')\s]+?\.png", exported)
    assert before == after


@pytest.mark.parametrize("case", gated_cases())
def test_manifest_counts_match_file(exports: dict[str, CaseExport], case: str) -> None:
    exp = _get(exports, case)
    data = (exp.rel_dir / "email.html").read_bytes()
    html = data.decode("utf-8")
    row = exp.rel_row
    assert row["sha256"] == hashlib.sha256(data).hexdigest()
    assert row["bytes"] == len(data)
    assert row["roundrect"] == html.count("v:roundrect")
    assert row["mso_blocks"] == html.count("<!--[if mso")
    assert row["commit"]
    json.dumps(row)  # the row must serialise into manifest.json
