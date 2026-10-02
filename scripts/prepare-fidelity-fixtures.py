#!/usr/bin/env python3
"""One-shot fixture preparation for the per-section fidelity gate (CE-1, #419).

For each gated case this script:

1. writes ``data/debug/<case>/reference_1x.png``: the design reference PNG
   resized (LANCZOS) to the case's frame width (max ``EmailSection.width``);
2. for cases 6-10, backs up ``assets/`` to ``assets_fullres/`` (gitignored, once)
   and overwrites every asset the current converter output references with a
   copy at most 600px wide (case 5's assets are already committed: untouched);
3. prints the ``.gitignore`` allowlist block for the references and assets.

Reads the untracked design PNGs under
``email-templates/training_HTML/for_converter_engine/``, so it runs only on a
machine that has them. The gate itself never reads them.

Usage:
    uv run python scripts/prepare-fidelity-fixtures.py [--cases reframe]
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.design_sync.fidelity_case_scorer import _ASSET_SRC_RE  # noqa: E402
from app.design_sync.tests.regression_runner import run_case_conversion  # noqa: E402

CASES = {
    "5": "maap",
    "6": "Starbucks",
    "7": "Lego",  # reference PNG has the known `viaual_design.png` typo — glob handles it
    "8": "performance_reimagined",
    "9": "slate",
    "10": "mammut",
    "reframe": "reframe_2025",
}
REF_ROOT = REPO / "email-templates/training_HTML/for_converter_engine"
MAX_ASSET_WIDTH = 600
COMMITTED_ASSET_CASES = {"5"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", nargs="+", default=list(CASES), help="case ids (default all)")
    args = parser.parse_args()
    allow: list[str] = ["!data/debug/*/reference_1x.png"]
    for case in args.cases:
        design = CASES[case]
        case_dir = REPO / "data/debug" / case
        result = run_case_conversion(case_dir)
        if result is None or result.layout is None:
            raise SystemExit(f"case {case}: missing structure.json/tokens.json")
        frame_width = round(max(s.width or 0 for s in result.layout.sections))

        ref_src = next((REF_ROOT / design).glob("*ual_design.png"))
        with Image.open(ref_src) as ref:
            height = round(ref.height * frame_width / ref.width)
            ref_1x = ref.convert("RGB").resize((frame_width, height), Image.Resampling.LANCZOS)
        ref_1x.save(case_dir / "reference_1x.png", optimize=True)
        print(f"case {case}: reference {ref_src.name} -> {frame_width}x{height}")

        nodes = sorted({m.group(1).replace(":", "_") for m in _ASSET_SRC_RE.finditer(result.html)})
        assets = case_dir / "assets"
        missing = [n for n in nodes if not (assets / f"{n}.png").exists()]
        if missing:
            raise SystemExit(f"case {case}: referenced assets missing on disk: {missing}")
        if case in COMMITTED_ASSET_CASES:
            print(f"case {case}: {len(nodes)} referenced assets, already committed")
            continue

        backup = case_dir / "assets_fullres"
        if not backup.exists():
            shutil.copytree(assets, backup)
        resized = 0
        for node in nodes:
            with Image.open(backup / f"{node}.png") as img:
                img.load()
                if img.width > MAX_ASSET_WIDTH:
                    h = round(img.height * MAX_ASSET_WIDTH / img.width)
                    # Palette/bitmap modes only resample NEAREST; widen first.
                    if img.mode not in ("RGB", "RGBA"):
                        img = img.convert("RGBA")
                    img = img.resize((MAX_ASSET_WIDTH, h), Image.Resampling.LANCZOS)
                    resized += 1
                img.save(assets / f"{node}.png", optimize=True)
        print(f"case {case}: {len(nodes)} referenced assets, {resized} downscaled")

        allow += [f"!data/debug/{case}/assets/", f"data/debug/{case}/assets/*"]
        allow += [f"!data/debug/{case}/assets/{n}.png" for n in nodes]

    partial = set(args.cases) != set(CASES)
    print(
        "\n# .gitignore block"
        + (" (APPEND these lines; the existing block stays)" if partial else "")
    )
    print("\n".join(allow))


if __name__ == "__main__":
    main()
