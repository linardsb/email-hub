"""Track-F fidelity harness: render current converter output per case, score vs reference,
save side-by-side composites (audit-4 method, docs/converter_audit_4.md §1).

Usage (from repo root, needs Playwright + local case assets — see
`phase-53.7-asset-reexport-prerequisite`):

    uv run python scripts/score-fidelity-cases.py            # all 6 cases
    uv run python scripts/score-fidelity-cases.py --cases 7 8

Prints the full_image / section_min / section_median table (the plan §6 log format) and
writes rendered PNGs + reference-vs-render composites to .tmpscratch/fidelity/.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.design_sync.fidelity_case_scorer import (  # noqa: E402
    render_case_png,
    score_case_fidelity,
)

CASES = {
    "5": "maap",
    "6": "Starbucks",
    "7": "Lego",  # reference PNG has the known `viaual_design.png` typo — glob handles it
    "8": "performance_reimagined",
    "9": "slate",
    "10": "mammut",
}
REF_ROOT = REPO / "email-templates/training_HTML/for_converter_engine"
OUT = REPO / ".tmpscratch/fidelity"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", nargs="*", default=list(CASES), help="case ids (default all)")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    results: dict[str, dict[str, object]] = {}
    for case in args.cases:
        tmpl = CASES[case]
        case_dir = REPO / "data/debug" / case
        ref_candidates = list((REF_ROOT / tmpl).glob("*ual_design.png"))
        if not ref_candidates:
            print(f"case {case}: NO reference PNG under {REF_ROOT / tmpl}")
            continue
        ref_bytes = ref_candidates[0].read_bytes()

        rendered = asyncio.run(render_case_png(case_dir))
        (OUT / f"case{case}_rendered.png").write_bytes(rendered)

        res = score_case_fidelity(case_dir, ref_bytes, rendered)
        results[case] = {
            "template": tmpl,
            "full_image": res.full_image,
            "section_min": res.section_min,
            "section_median": res.section_median,
            "sections": [round(s.ssim, 3) for s in res.score.sections],
        }

        ref_img = Image.open(io.BytesIO(ref_bytes)).convert("RGB")
        ren_img = Image.open(io.BytesIO(rendered)).convert("RGB")
        scale = ref_img.height / ren_img.height
        ren_scaled = ren_img.resize((int(ren_img.width * scale), ref_img.height), Image.LANCZOS)
        comp = Image.new("RGB", (ref_img.width + ren_scaled.width + 12, ref_img.height), "#ff00ff")
        comp.paste(ref_img, (0, 0))
        comp.paste(ren_scaled, (ref_img.width + 12, 0))
        comp.save(OUT / f"case{case}_side_by_side.png")

    print("\ncase  full_image  section_min  section_median")
    for case, r in results.items():
        print(
            f"{case:>4}  {r['full_image']:>10.3f}  {r['section_min']:>11.3f}  "
            f"{r['section_median']:>14.3f}  ({r['template']})"
        )
    (OUT / "scores.json").write_text(json.dumps(results, indent=2))
    print(f"\ncomposites + scores.json -> {OUT}")


if __name__ == "__main__":
    main()
