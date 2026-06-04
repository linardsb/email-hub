"""Deterministic section-count ladder harness for converter regression fixtures.

Prints, per fixture ``data/debug/<case>/``, the count ladder that Track A/A1 of
``.agents/plans/53-converter-engine-fix.md`` uses to confirm (or refute) the
LEGO over-segmentation claim (8 → 21 → 17)::

    target_sections (manifest)
      → len(_get_section_candidates)        # pre wrapper-unwrap
      → len(analyze_layout().sections)      # post wrapper-unwrap
      → ConversionResult.sections_count     # rendered

plus per-section element bags (text/image/button counts) and a band-grouping
descriptor (sections sharing a ``parent_wrapper_id`` belong to one band — this
is the "17 blocks within 8 bands" measurement).

The structure is ``normalize_tree``-d before rows 2/3 are measured, exactly as
``EmailDesignDocument.from_legacy`` (the pipeline behind row 4) does — otherwise
the pre-unwrap rows would describe a different tree than the rendered count.

Run::

    python -m app.design_sync.tests.ladder_harness
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.design_sync.diagnose.report import load_structure_from_json
from app.design_sync.figma.layout_analyzer import (
    EmailSection,
    _find_primary_page,  # pyright: ignore[reportPrivateUsage]
    _get_section_candidates,  # pyright: ignore[reportPrivateUsage]
    analyze_layout,
)
from app.design_sync.figma.tree_normalizer import normalize_tree
from app.design_sync.tests.regression_runner import run_case_conversion

_DEBUG_DIR = Path(__file__).resolve().parents[3] / "data" / "debug"
_CASE_IDS = ("5", "6", "7", "8", "9", "10")


# ── target_sections source ───────────────────────────────────────
# NOTE: the *design target* lives ONLY in the top-level data/debug/manifest.yaml
# (keyed by case id). The per-case manifest.yaml's ``sections.count`` is pinned
# to the converter's own (broken) output, so reading it would make the ladder
# circular. See plan §2.2.


def load_target_sections() -> dict[str, int]:
    """Map case id → design ``target_sections`` from the top-level manifest."""
    data: dict[str, Any] = yaml.safe_load((_DEBUG_DIR / "manifest.yaml").read_text())
    targets: dict[str, int] = {}
    for case in data.get("cases", []):
        case_id = str(case.get("id", ""))
        if case_id and "target_sections" in case:
            targets[case_id] = int(case["target_sections"])
    return targets


# ── band grouping ────────────────────────────────────────────────


def band_descriptor(sections: list[EmailSection]) -> tuple[int, str]:
    """Group analysed sections into bands by shared ``parent_wrapper_id``.

    Returns ``(band_count, description)``. Sections without a parent wrapper are
    their own band; sections sharing a wrapper id collapse into one band.

    INVARIANT (read before reasoning about Track C): grouping by
    ``parent_wrapper_id`` exactly inverts ``_expand_container_wrappers``, so
    ``band_count`` equals the pre-unwrap candidate count (row 2) by construction
    — it is a cross-check, NOT independent recovery of ``target_sections``. When
    ``band_count == target`` (LEGO/slate) it is only because candidates happen to
    equal target there. The *per-wrapper breakdown* (which wrappers exploded, and
    by how much) is the real signal; the count alone carries no new information.
    """
    groups: dict[str, int] = {}
    order: list[str] = []
    for sec in sections:
        key = sec.parent_wrapper_id or f"~solo:{sec.node_id}"
        if key not in groups:
            groups[key] = 0
            order.append(key)
        groups[key] += 1
    multi = [f"{k.split(':')[-1]}={groups[k]}" for k in order if not k.startswith("~solo:")]
    solo = sum(1 for k in order if k.startswith("~solo:"))
    parts: list[str] = []
    if multi:
        parts.append("wrappers[" + ", ".join(multi) + "]")
    if solo:
        parts.append(f"solo={solo}")
    return len(groups), " ".join(parts) or "—"


# ── ladder ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class LadderRow:
    """One fixture's count ladder + per-section detail."""

    case_id: str
    name: str
    target: int | None
    candidates: int
    analyzed: int
    rendered: int
    bands: int
    band_desc: str
    bags: list[tuple[str, int, int, int]] = field(default_factory=list[tuple[str, int, int, int]])


def compute_ladder(case_id: str, targets: dict[str, int]) -> LadderRow | None:
    """Compute the ladder for one case dir; ``None`` if inputs are missing."""
    case_dir = _DEBUG_DIR / case_id
    structure_path = case_dir / "structure.json"
    tokens_path = case_dir / "tokens.json"
    if not structure_path.exists() or not tokens_path.exists():
        return None

    structure = load_structure_from_json(structure_path)
    # Match the pipeline: from_legacy normalizes (default _pre_normalized=False)
    # before analyze_layout. Measure rows 2/3 on the SAME normalized tree.
    norm_structure, _stats = normalize_tree(structure)

    candidates = 0
    if norm_structure.pages:
        page = _find_primary_page(norm_structure.pages)
        candidates = len(_get_section_candidates(page))

    layout = analyze_layout(norm_structure)
    bands, band_desc = band_descriptor(layout.sections)
    bags: list[tuple[str, int, int, int]] = [
        (sec.node_name[:28] or sec.node_id, len(sec.texts), len(sec.images), len(sec.buttons))
        for sec in layout.sections
    ]

    result = run_case_conversion(case_dir)
    rendered = result.sections_count if result is not None else -1

    # Prefer the per-case manifest name when available for a friendly label.
    name = ""
    manifest_path = case_dir / "manifest.yaml"
    if manifest_path.exists():
        mdata: dict[str, Any] = yaml.safe_load(manifest_path.read_text())
        name = str(mdata.get("name", ""))

    return LadderRow(
        case_id=case_id,
        name=name,
        target=targets.get(case_id),
        candidates=candidates,
        analyzed=len(layout.sections),
        rendered=rendered,
        bands=bands,
        band_desc=band_desc,
        bags=bags,
    )


def _fmt_target(target: int | None) -> str:
    return str(target) if target is not None else "?"


def print_ladder(rows: list[LadderRow]) -> None:
    """Print the 6-row ladder summary plus per-case element bags."""
    print("\n=== Converter section-count ladder ===")  # noqa: T201
    header = f"{'case':<5}{'target':>7}{'cand':>6}{'analyze':>9}{'render':>8}{'bands':>7}  name"
    print(header)  # noqa: T201
    print("-" * len(header))  # noqa: T201
    for r in rows:
        print(  # noqa: T201
            f"{r.case_id:<5}{_fmt_target(r.target):>7}{r.candidates:>6}"
            f"{r.analyzed:>9}{r.rendered:>8}{r.bands:>7}  {r.name[:48]}"
        )

    print("\n=== Per-case detail (band grouping + element bags) ===")  # noqa: T201
    for r in rows:
        print(f"\n[case {r.case_id}] {r.name}")  # noqa: T201
        print(  # noqa: T201
            f"  ladder: target={_fmt_target(r.target)} "
            f"→ candidates={r.candidates} → analyze={r.analyzed} → rendered={r.rendered}"
        )
        print(f"  bands:  {r.bands}  ({r.band_desc})")  # noqa: T201
        for label, t, i, b in r.bags:
            print(f"    - {label:<30} t={t} i={i} b={b}")  # noqa: T201


def main() -> None:
    """Compute and print the ladder for every fixture case."""
    targets = load_target_sections()
    rows: list[LadderRow] = []
    for case_id in _CASE_IDS:
        row = compute_ladder(case_id, targets)
        if row is None:
            print(f"SKIP case {case_id} (missing structure.json/tokens.json)")  # noqa: T201
            continue
        rows.append(row)
    print_ladder(rows)


if __name__ == "__main__":
    main()
