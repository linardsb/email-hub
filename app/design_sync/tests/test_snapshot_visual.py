"""Visual regression: Playwright screenshot of converter output vs Figma design.png.

Renders converter HTML output to a screenshot, pixel-diffs against the Figma design
screenshot captured by 40.3. Measures visual fidelity — how close the converter output
looks to the original design.

This is a fidelity metric, not a pass/fail gate. The mismatch percentage starts high
(~40-60%) and should decrease with each converter improvement.

Run: make snapshot-visual
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.design_sync.converter_service import DesignConverterService
from app.design_sync.diagnose.report import load_structure_from_json, load_tokens_from_json
from app.design_sync.email_design_document import EmailDesignDocument
from app.rendering.exceptions import VisualDiffError
from app.rendering.local.profiles import RenderingProfile
from app.rendering.local.runner import capture_screenshot
from app.rendering.visual_diff import DiffResult, run_odiff

_DEBUG_DIR = Path(__file__).resolve().parents[3] / "data" / "debug"
_MANIFEST = _DEBUG_DIR / "manifest.yaml"
_REFERENCE_DIR = (
    Path(__file__).resolve().parents[3]
    / "email-templates"
    / "training_HTML"
    / "for_converter_engine"
)

# Mapping: case ID → reference HTML filename
_REFERENCE_MAP: dict[str, str] = {
    "5": "maap-kask.html",
    "6": "starbucks-pumpkin-spice.html",
    "10": "mammut-duvet-day.html",
}

# Simple profile for visual fidelity screenshots — 600px wide email viewport
_FIDELITY_PROFILE = RenderingProfile(
    name="fidelity_600",
    viewport_width=600,
    viewport_height=900,
    browser="cr",
)


# ── Helpers ──────────────────────────────────────────────────────


def _serve_directory(root: Path) -> tuple[HTTPServer, int]:
    """Start a localhost HTTP server serving files from root. Returns (server, port)."""
    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    server = HTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


_IMG_SRC_RE = re.compile(r'src="([^"]*)"')


def _rewrite_image_paths(html: str, base_url: str, case_id: str) -> str:
    """Rewrite image src paths to use the HTTP server URL."""

    def _replace(m: re.Match[str]) -> str:
        src = m.group(1)
        if not src or src.startswith("http"):
            return m.group(0)
        # Normalize the path — could be relative or just a filename
        filename = Path(src).name
        return f'src="{base_url}/debug/{case_id}/assets/{filename}"'

    return _IMG_SRC_RE.sub(_replace, html)


def _load_manifest() -> list[dict[str, Any]]:
    """Load cases from manifest."""
    if not _MANIFEST.exists():
        return []
    data = yaml.safe_load(_MANIFEST.read_text())
    return data.get("cases", []) if data else []


def _get_visual_case_ids() -> list[str]:
    """Return case IDs that have design_image: true."""
    return [
        c["id"]
        for c in _load_manifest()
        if c.get("status") == "active" and c.get("design_image") is True
    ]


def _get_visual_threshold(case_id: str) -> float:
    """Get per-case visual threshold (default 0.95 = 95% diff allowed)."""
    for c in _load_manifest():
        if c["id"] == case_id:
            return float(c.get("visual_threshold", 0.95))
    return 0.95


# ── Core pipeline ────────────────────────────────────────────────


def _run_conversion(case_dir: Path) -> str:
    """Convert design inputs → HTML string."""
    structure = load_structure_from_json(case_dir / "structure.json")
    tokens = load_tokens_from_json(case_dir / "tokens.json")
    document = EmailDesignDocument.from_legacy(structure, tokens)
    result = DesignConverterService().convert_document(document)
    return result.html


async def _screenshot_html(html: str, output_dir: Path, serve_root: Path, case_id: str) -> Path:
    """Render HTML to PNG via Playwright. Returns path to rendered.png."""
    server, port = _serve_directory(serve_root)
    try:
        base_url = f"http://127.0.0.1:{port}"
        rewritten = _rewrite_image_paths(html, base_url, case_id)

        # Write rewritten HTML for reference / debugging
        html_path = output_dir / "_visual_test.html"
        html_path.write_text(rewritten, encoding="utf-8")

        # capture_screenshot writes to output_dir/{profile.name}.png and returns bytes
        await capture_screenshot(rewritten, _FIDELITY_PROFILE, output_dir)

        # Rename profile-named file to rendered.png
        profile_png = output_dir / f"{_FIDELITY_PROFILE.name}.png"
        rendered_path = output_dir / "rendered.png"
        profile_png.rename(rendered_path)
        return rendered_path
    finally:
        server.shutdown()


async def _diff_images(
    design_path: Path,
    rendered_path: Path,
    output_dir: Path,
    diff_name: str = "diff.png",
) -> DiffResult:
    """Pixel diff two images. Handles dimension mismatch gracefully."""
    diff_path = output_dir / diff_name
    try:
        return await run_odiff(design_path, rendered_path, diff_path, threshold=0.01)
    except VisualDiffError:
        # Dimension mismatch — resize rendered to match design, retry
        from PIL import Image

        from app.shared.imaging import safe_image_open

        design_img = safe_image_open(design_path)
        rendered_img = safe_image_open(rendered_path)
        if design_img.size != rendered_img.size:
            resized = rendered_img.resize(design_img.size, Image.Resampling.LANCZOS)
            resized_path = output_dir / "rendered_resized.png"
            resized.save(resized_path)
            return await run_odiff(design_path, resized_path, diff_path, threshold=0.01)
        raise


def _save_report(
    output_dir: Path,
    diff_result: DiffResult,
    threshold: float,
    label: str = "converter",
) -> None:
    """Save visual_report.json with fidelity metrics."""
    report = {
        "label": label,
        "mismatch_pct": diff_result.diff_percentage,
        "pixel_count": diff_result.pixel_count,
        "identical": diff_result.identical,
        "threshold": threshold,
        "passed": diff_result.diff_percentage <= threshold * 100,
    }
    report_path = output_dir / "visual_report.json"
    # Merge with existing report if present
    existing: dict[str, Any] = {}
    if report_path.exists():
        existing = json.loads(report_path.read_text())
    existing[label] = report
    report_path.write_text(json.dumps(existing, indent=2))


# ── Test classes ─────────────────────────────────────────────────


@pytest.mark.visual_regression
class TestSnapshotVisualRegression:
    """Converter output → screenshot → pixel diff vs Figma design.png."""

    @pytest.mark.parametrize("case_id", _get_visual_case_ids())
    def test_visual_fidelity(self, case_id: str) -> None:
        case_dir = _DEBUG_DIR / case_id
        design_path = case_dir / "design.png"
        assert design_path.exists(), f"No design.png for case {case_id}"

        # 1. Run converter
        html = _run_conversion(case_dir)
        assert html, f"Empty HTML for case {case_id}"

        # 2. Screenshot via Playwright
        serve_root = _DEBUG_DIR.parent  # data/ — so debug/{case}/assets/ is accessible
        rendered_path = asyncio.run(_screenshot_html(html, case_dir, serve_root, case_id))

        # 3. Pixel diff
        threshold = _get_visual_threshold(case_id)
        diff_result = asyncio.run(_diff_images(design_path, rendered_path, case_dir))

        # 4. Save artifacts
        _save_report(case_dir, diff_result, threshold, label="converter")

        # Don't fail unless above threshold (permissive initially)
        pct = diff_result.diff_percentage
        if pct > threshold * 100:
            pytest.fail(
                f"Visual mismatch {pct:.1f}% exceeds threshold {threshold * 100:.0f}% "
                f"for case {case_id}. Diff saved to {case_dir / 'diff.png'}"
            )


@pytest.mark.visual_regression
class TestReferenceVisualFidelity:
    """Hand-built reference HTML → screenshot → pixel diff vs design.png.

    Establishes the best achievable fidelity baseline. The gap between
    reference fidelity and converter fidelity is the work remaining.
    """

    @pytest.mark.parametrize("case_id", _get_visual_case_ids())
    def test_reference_fidelity(self, case_id: str) -> None:
        case_dir = _DEBUG_DIR / case_id
        design_path = case_dir / "design.png"
        assert design_path.exists(), f"No design.png for case {case_id}"

        ref_filename = _REFERENCE_MAP.get(case_id)
        if not ref_filename:
            pytest.skip(f"No reference HTML mapping for case {case_id}")
        ref_path = _REFERENCE_DIR / ref_filename
        if not ref_path.exists():
            pytest.skip(f"Reference HTML not found: {ref_path}")

        ref_html = ref_path.read_text(encoding="utf-8")
        serve_root = _DEBUG_DIR.parent

        rendered_path = asyncio.run(_screenshot_html(ref_html, case_dir, serve_root, case_id))

        # Rename to reference_rendered.png to avoid clobbering converter rendered.png
        ref_rendered = case_dir / "reference_rendered.png"
        rendered_path.rename(ref_rendered)

        diff_result = asyncio.run(
            _diff_images(design_path, ref_rendered, case_dir, diff_name="reference_diff.png")
        )

        _save_report(case_dir, diff_result, threshold=0.95, label="reference")
