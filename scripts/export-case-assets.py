#!/usr/bin/env python3
"""Export Figma node-render PNGs for converter regression fixtures.

The converter emits ``<img src="/api/v1/design-sync/assets/{node_id}.png">``
for each image it places. Those node-ids are the ground truth of what each
fixture needs on disk; this script reads them straight out of the committed
``expected.html`` and renders each via Figma's image API.

Usage:
    FIGMA_TOKEN=figd_xxx python scripts/export-case-assets.py            # cases 6,7,8,9,10
    FIGMA_TOKEN=figd_xxx python scripts/export-case-assets.py 9 10       # specific cases

Saves to ``data/debug/<case>/assets/<node_id : -> _>.png`` (the filename
``_resolve_local_assets`` looks up). Verified byte-identical to the real
import pipeline's output on case 5 at scale=2.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

FILE_KEY = "VUlWjZGAEVZr3mK1EawsYR"  # "The Ultimate Email Design System" (Community)
FIGMA_API = "https://api.figma.com"
SCALE = 2  # matches the on-disk case-5 assets byte-for-byte
DEFAULT_CASES = ["6", "7", "8", "9", "10"]
TINY_BYTES = 512  # below this a render is likely blank/transparent -> flag for review
THROTTLE_S = 0.4  # polite delay between Figma requests
MAX_RETRIES = 5

ROOT = Path(__file__).resolve().parents[1]
ASSET_RE = re.compile(r"/assets/([^\"'\s)]+)\.png")


def _open(req: urllib.request.Request | str, timeout: int = 120) -> bytes:
    """urlopen with 429-aware exponential backoff."""
    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < MAX_RETRIES - 1:
                wait = int(e.headers.get("Retry-After", 0)) or min(60, 5 * 2**attempt)
                print(f"    429 rate-limited; sleeping {wait}s (attempt {attempt + 1})")
                time.sleep(wait)
                continue
            raise
    raise RuntimeError("unreachable")


def referenced_node_ids(expected_html: Path) -> list[str]:
    """Distinct image node-ids the converter emits for a fixture (colon form)."""
    html = expected_html.read_text(encoding="utf-8")
    seen: dict[str, None] = {}
    for nid in ASSET_RE.findall(html):
        seen.setdefault(nid, None)
    return list(seen)


def render_urls(token: str, node_ids: list[str]) -> dict[str, str | None]:
    """Batch-render node-ids (<=100/batch) -> {node_id: render_url | None}."""
    out: dict[str, str | None] = {}
    for i in range(0, len(node_ids), 100):
        batch = node_ids[i : i + 100]
        q = f"ids={','.join(batch)}&format=png&scale={SCALE}"
        req = urllib.request.Request(  # noqa: S310 - fixed Figma host
            f"{FIGMA_API}/v1/images/{FILE_KEY}?{q}",
            headers={"X-Figma-Token": token},
        )
        payload: dict[str, Any] = json.loads(_open(req))
        images = payload.get("images", {})
        for nid in batch:
            out[nid] = images.get(nid)
        time.sleep(THROTTLE_S)
    return out


def export_case(token: str, case: str) -> int:
    """Render + save all referenced assets for one case. Returns failure count."""
    case_dir = ROOT / "data" / "debug" / case
    expected = case_dir / "expected.html"
    if not expected.exists():
        print(f"case {case}: no expected.html -> skip")
        return 0

    node_ids = referenced_node_ids(expected)
    assets_dir = case_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    urls = render_urls(token, node_ids)

    failures = 0
    blanks: list[str] = []
    print(f"\n=== case {case}: {len(node_ids)} referenced node-ids ===")
    for nid in node_ids:
        url = urls.get(nid)
        if not url:
            print(f"  {nid:<12} NO RENDER URL (node missing/unrenderable)")
            failures += 1
            continue
        data = _open(url)
        out = assets_dir / f"{nid.replace(':', '_')}.png"
        out.write_bytes(data)
        flag = ""
        if len(data) < TINY_BYTES:
            blanks.append(nid)
            flag = "  <-- TINY, review for blank"
        print(f"  {nid:<12} {len(data):>9} bytes -> {out.name}{flag}")
        time.sleep(THROTTLE_S)

    if failures:
        print(f"  ! {failures} node(s) failed to render")
    if blanks:
        print(f"  ! {len(blanks)} tiny render(s) to eyeball: {', '.join(blanks)}")
    return failures


def main() -> None:
    token = os.environ.get("FIGMA_TOKEN")
    if not token:
        sys.exit("FIGMA_TOKEN env var is required")
    cases = sys.argv[1:] or DEFAULT_CASES
    total_fail = sum(export_case(token, c) for c in cases)
    print(f"\nDone. {total_fail} failed render(s) across {len(cases)} case(s).")
    if total_fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
