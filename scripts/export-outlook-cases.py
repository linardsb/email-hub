"""CE-4: export each case's converter HTML plus its images as a self-contained bundle.

Every classic-Outlook render source (Litmus, Email on Acid, an own rig, manual send) needs
the same input: the current converter HTML with images that resolve outside the live API.
See docs/outlook-render-source.md.

Usage (from repo root):

    uv run python scripts/export-outlook-cases.py                    # all gated cases
    uv run python scripts/export-outlook-cases.py --cases 5 7
    uv run python scripts/export-outlook-cases.py --cases 5 --asset-base-url https://cdn/x/5

Writes <out>/<case>/email.html, <out>/<case>/assets/*.png and <out>/manifest.json
(default <out> = .tmpscratch/outlook-export). Asset refs (`src="…"` and CSS `url('…')`)
become `assets/<node>.png`, or `<base>/<node>.png` with --asset-base-url. The base URL is
used as given for every case, so export one case per run when hosting per case.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.design_sync.fidelity_gate import DEBUG_DIR, current_commit, gated_cases  # noqa: E402
from app.design_sync.tests.regression_runner import run_case_conversion  # noqa: E402

# Bare API path, so both `src="…"` and `url('…')` refs match (node ids contain ':').
ASSET_REF_RE = re.compile(r"/api/v1/design-sync/assets/([^\"')\s]+?)\.png")
OUT = REPO / ".tmpscratch/outlook-export"


def export_case(
    case: str, out_dir: Path, *, asset_base_url: str | None = None
) -> dict[str, object]:
    """Write one case's bundle under ``out_dir/<case>`` and return its manifest row."""
    result = run_case_conversion(DEBUG_DIR / case)
    if result is None:
        raise SystemExit(f"case {case}: no structure.json/tokens.json under {DEBUG_DIR / case}")

    case_out = out_dir / case
    assets_out = case_out / "assets"
    assets_out.mkdir(parents=True, exist_ok=True)
    prefix = asset_base_url.rstrip("/") if asset_base_url else "assets"
    referenced: list[str] = []

    def _sub(match: re.Match[str]) -> str:
        name = f"{match.group(1).replace(':', '_')}.png"
        referenced.append(name)
        return f"{prefix}/{name}"

    html = ASSET_REF_RE.sub(_sub, result.html)
    missing: list[str] = []
    for name in sorted(set(referenced)):
        src = DEBUG_DIR / case / "assets" / name
        if src.is_file():
            shutil.copyfile(src, assets_out / name)
        else:
            missing.append(name)

    data = html.encode("utf-8")
    (case_out / "email.html").write_bytes(data)
    return {
        "case": case,
        "commit": current_commit(),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "img_srcs": len(referenced),
        "roundrect": html.count("v:roundrect"),
        "mso_blocks": html.count("<!--[if mso"),
        "missing_assets": missing,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", nargs="*", default=gated_cases(), help="case ids (default all)")
    parser.add_argument("--out", type=Path, default=OUT, help="output directory")
    parser.add_argument("--asset-base-url", default=None, help="absolute URL prefix for assets")
    args = parser.parse_args()

    rows = [export_case(c, args.out, asset_base_url=args.asset_base_url) for c in args.cases]
    (args.out / "manifest.json").write_text(json.dumps(rows, indent=2) + "\n")
    print("case     bytes  refs  roundrect  mso  missing")
    for r in rows:
        print(
            f"{r['case']:>7}  {r['bytes']:>6}  {r['img_srcs']:>4}  {r['roundrect']:>9}  "
            f"{r['mso_blocks']:>3}  {len(r['missing_assets'])}"
        )
    print(f"\nbundle + manifest.json -> {args.out}")


if __name__ == "__main__":
    main()
