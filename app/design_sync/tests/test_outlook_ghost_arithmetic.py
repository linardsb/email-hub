"""Static Word-box arithmetic gate for Outlook MSO ghost tables (Track G · G9).

The Figma→email converter emits Outlook "ghost tables" (``<!--[if mso]>…<table
width><tr><td>…``) so the Word rendering engine lays out multi-column sections
that modern clients do with ``display:inline-block``. Nothing in the suite
renders the Word engine, so width defects there ship un-scored. This static gate
walks every MSO ghost in the six committed baselines and asserts the Word-box
arithmetic — no render required:

- **self-consistency:** ``Σ(ghost <td width>) == ghost <table width>``.
- **container-fit:** ``ghost <table width> + Σ(host horizontal paddings) ≤
  container`` (600, or 640 for c6/c9). Overflow (``>``) is always a FAIL (the F7
  overflow symptom). The strict ``==`` half — underflow is a FAIL — is enforced
  only for a *non-centered* ghost; an ``align="center"`` strip may legitimately
  total less than the container, so it is exempt from the underflow check. Every
  ghost in the current corpus is centered, so today only the overflow half ever
  fires; the underflow branch is dead-but-defensive against a future
  non-centered ghost.
- **img self-consistency:** every ``<img>`` carrying an inline ``max-width:Npx``
  has ``width="N"`` (locks the ``_clamp_img_max_width`` desync seam — F3).

Ported verbatim (algorithm) from the validated reference
``.agents/plans/53-g9-ghost-probe.py`` — GREEN on all six baselines with the
container-fit arithmetic live, and three independent RED-proofs firing. The
inset math is imported as ``_style_horizontal_padding_px`` from the renderer so
the gate can never drift from what the converter actually emits. Note that the
shared helper counts a non-px padding as ``0`` — a fail-safe "don't over-shrink"
for the *converter*, but for this *gate* that under-counts ``inset`` and so
under-estimates ``fit``: an unparseable host padding is the gate's false-pass
direction. Latent only — every host inset in the six baselines is integer px
(asserted GREEN); the ghost-count guard below (``_EXPECTED_GHOSTS``) is the
backstop against a silently toothless gate.

**Scope note (F3):** the img check locks only the ``attr == max-width``
self-consistency seam. It does NOT cover the column rescalers
(``_shrink_column_ghost_widths`` et al.) failing to rewrite a *contained*
``<img>`` when they shrink a column — that rescale-miss is latent-not-manifest in
the corpus and logged as deferred ``phase-53g-g9-img-not-rescaled-with-column``.
Unmarked on purpose so it runs under ``make test`` / ``make check``.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

from app.design_sync.component_renderer import _style_horizontal_padding_px

# app/design_sync/tests/ -> parents[3] == repo root (mirrors the sibling
# converter tests' _DEBUG_DIR).
_DEBUG_DIR = Path(__file__).resolve().parents[3] / "data" / "debug"
_CASES = ["5", "6", "7", "8", "9", "10"]

# Anti-vacuous guard: the number of MSO ghosts each baseline must yield today.
# ``_check`` returns ``[]`` for *zero* ghosts, so if the converter's ghost-emit
# format ever drifts and the regexes stop matching, the arithmetic assertions
# would pass silently on nothing checked. This exact-count assertion turns that
# into a loud failure (and self-documents the corpus). Update when a baseline is
# legitimately regenerated with a different ghost count.
_EXPECTED_GHOSTS = {"5": 4, "6": 2, "7": 7, "8": 3, "9": 1, "10": 5}

# Reused verbatim from component_renderer so the gate checks precisely what the
# converter emits (the ghost skeleton and the two width surfaces).
_TABLE_W_RE = re.compile(r'<table\b[^>]*\bwidth="(\d+)"[^>]*>')
_ALIGN_C_RE = re.compile(r'<table\b[^>]*\balign="center"')
_COL_TD_RE = re.compile(r'<td width="(\d+)" valign="top"')
_SEP_RE = re.compile(r'</td>\s*<td width="(\d+)" valign="top"')
_IMG_RE = re.compile(r"<img\b[^>]*>")


class _GhostWalker(HTMLParser):
    """Assemble every MSO ghost's Word-box geometry from fragmented comments.

    A unified LIFO ``frames`` stack: every ghost OPEN pushes a frame tagged
    ``"container"`` (bare ``<tr><td>``) or ``"percol"`` (``<td width
    valign="top">`` column cells); every column separator appends to the nearest
    ``percol`` frame; every skeleton ``</td></tr></table>`` pops the most-recent
    frame — so a nested split sub-ghost inside a column can't clobber the
    enclosing per-column ghost. Two non-obvious invariants the reference already
    resolved and this port preserves:

    1. A self-contained fragment (open AND close in one comment — a spacer
       ghost, or a rare single-fragment column ghost) is handled standalone and
       never pushes a frame, so a stray ``</table>`` can't finalize the wrong
       ghost.
    2. ``inset`` is captured at OPEN (from the nearest container's stack depth):
       the ancestor inset cells (band, card) are on ``td_stack`` when the ghost
       opens but are back at the same depth by its close, so summing at CLOSE
       would always yield 0 — a toothless gate the overflow proof can't fail.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.td_stack: list[int] = []
        self.frames: list[dict[str, Any]] = []
        self.ghosts: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "td":
            style = {k.lower(): (v or "") for k, v in attrs}.get("style", "")
            self.td_stack.append(_style_horizontal_padding_px(style))

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "td" and self.td_stack:
            self.td_stack.pop()

    def _nearest_container(self) -> dict[str, Any] | None:
        for frame in reversed(self.frames):
            if frame["kind"] == "container":
                return frame
        return None

    def _top_percol(self) -> dict[str, Any] | None:
        for frame in reversed(self.frames):
            if frame["kind"] == "percol":
                return frame
        return None

    def _open_inset_and_container(self) -> tuple[int, int | None]:
        """Inset (Σ real-td padding, container-inward) + container width, at OPEN."""
        container = self._nearest_container()
        base = container["base"] if container else 0
        return sum(self.td_stack[base:]), (container["W"] if container else None)

    def handle_comment(self, data: str) -> None:
        if "[if mso]" not in data:
            return
        has_open = _TABLE_W_RE.search(data)
        has_close = "</table>" in data
        first_col = _COL_TD_RE.search(data)
        sep = _SEP_RE.search(data)
        skeleton_close = "</td></tr></table>" in data

        # Open AND close in one fragment: spacer ghost, or a rare single-fragment
        # per-column ghost. Handle standalone; never push a frame (invariant 1).
        if has_open and has_close:
            if first_col:
                inset, container_w = self._open_inset_and_container()
                self.ghosts.append(
                    {
                        "W": int(has_open.group(1)),
                        "align": bool(_ALIGN_C_RE.search(data)),
                        "tds": [int(m.group(1)) for m in _COL_TD_RE.finditer(data)],
                        "inset": inset,
                        "C": container_w,
                    }
                )
            return
        if has_open and first_col:  # per-column OPEN -> push frame
            inset, container_w = self._open_inset_and_container()
            self.frames.append(
                {
                    "kind": "percol",
                    "W": int(has_open.group(1)),
                    "align": bool(_ALIGN_C_RE.search(data)),
                    "tds": [int(first_col.group(1))],
                    "inset": inset,
                    "C": container_w,
                }
            )
        elif has_open:  # container/wrapper OPEN (bare td)
            self.frames.append(
                {"kind": "container", "W": int(has_open.group(1)), "base": len(self.td_stack)}
            )
        else:  # non-open fragment: a separator and a close can co-occur here
            # Handle sep and close independently (NOT elif): if one comment ever
            # carried both the last column separator AND the skeleton close, an
            # elif would drop the close and leak the frame — corrupting later
            # _nearest_container / _top_percol lookups. Append the td first, then
            # pop, so the final column is counted before the ghost is finalized.
            if sep:  # column separator -> nearest percol frame
                frame = self._top_percol()
                if frame is not None:
                    frame["tds"].append(int(sep.group(1)))
            if skeleton_close and self.frames:  # CLOSE -> pop most-recent frame
                frame = self.frames.pop()
                if frame["kind"] == "percol":
                    self.ghosts.append(
                        {
                            "W": frame["W"],
                            "align": frame["align"],
                            "tds": frame["tds"],
                            "inset": frame["inset"],
                            "C": frame["C"],
                        }
                    )


def _check(html: str) -> list[str]:
    """Return a list of Word-box violation strings for ``html`` (empty == GREEN)."""
    violations: list[str] = []
    walker = _GhostWalker()
    walker.feed(html)
    for ghost in walker.ghosts:
        td_sum = sum(ghost["tds"])
        if td_sum != ghost["W"]:
            violations.append(
                f"self-consistency: Sigma(td)={td_sum} != W={ghost['W']} tds={ghost['tds']}"
            )
            continue
        container_w = ghost["C"]
        if container_w is None:
            continue
        fit = ghost["W"] + ghost["inset"]
        if fit > container_w:
            violations.append(
                f"OVERFLOW: W+inset={fit} > container={container_w} "
                f"(W={ghost['W']} inset={ghost['inset']})"
            )
        elif fit < container_w and not ghost["align"]:
            violations.append(f"UNDERFLOW(!center): W+inset={fit} < container={container_w}")
    # Img self-consistency: attr == inline max-width (where a max-width exists).
    # Fluid imgs with width:100% and no max-width are out of scope (Non-Goals).
    for tag in _IMG_RE.findall(html):
        width_attr = re.search(r'\bwidth="(\d+)"', tag)
        max_width = re.search(r"max-width:\s*(\d+)px", tag)
        if width_attr and max_width and width_attr.group(1) != max_width.group(1):
            violations.append(
                f'img: width="{width_attr.group(1)}" != max-width:{max_width.group(1)}px'
            )
    return violations


def _mutate(html: str, old: str, new: str, n: int = 1) -> str:
    """Replace ``old`` with ``new`` on an in-memory copy (never a committed baseline).

    ``n`` is passed straight to ``str.replace`` — ``n=-1`` replaces every
    occurrence. The ``old in html`` assert makes anchor drift fail legibly.
    """
    assert old in html, f"mutation anchor not found: {old!r}"
    return html.replace(old, new, n)


def _load(case_id: str) -> str:
    return (_DEBUG_DIR / case_id / "expected.html").read_text()


class TestWordBoxArithmetic:
    """Every MSO ghost in the six baselines must balance its Word-box arithmetic."""

    @pytest.mark.parametrize("case_id", _CASES)
    def test_baseline_ghost_arithmetic_balances(self, case_id: str) -> None:
        """Self-consistency + container-fit + img all hold on the committed baseline."""
        html = _load(case_id)
        walker = _GhostWalker()
        walker.feed(html)
        # Guard first: a drifted emit-format would yield zero ghosts and pass the
        # arithmetic vacuously (see _EXPECTED_GHOSTS).
        assert len(walker.ghosts) == _EXPECTED_GHOSTS[case_id], (
            f"c{case_id}: walked {len(walker.ghosts)} ghosts, expected "
            f"{_EXPECTED_GHOSTS[case_id]} — converter ghost-emit format drift?"
        )
        assert _check(html) == []

    # -- RED-proofs: each targets ONE assertion so no single mutation vacuously
    #    satisfies all three (proven in the reference probe). --------------------

    def test_gate_catches_overflow(self) -> None:
        """Inflating a c7 ghost past ``container - inset`` (Sum td still == W) -> OVERFLOW."""
        # Keep Σtd == W while inflating: 512->560 and every 256->280 (280+280=560),
        # so the ghost stays self-consistent and only the container-fit check trips.
        over = _mutate(_load("7"), 'width="512"', 'width="560"', n=1)
        over = _mutate(over, 'width="256" valign="top"', 'width="280" valign="top"', n=-1)
        assert any("OVERFLOW" in v for v in _check(over))

    def test_gate_catches_self_inconsistency(self) -> None:
        """Bumping ONE c7 column ``<td width>`` so ``Σtd != W`` -> self-consistency FAIL."""
        broken = _mutate(_load("7"), 'width="256" valign="top"', 'width="266" valign="top"', n=1)
        assert any("self-consistency" in v for v in _check(broken))

    def test_gate_catches_img_mismatch(self) -> None:
        """Desyncing one c9 ``<img width=>`` attr from its ``max-width`` -> img FAIL."""
        broken = _mutate(
            _load("9"),
            'width="560" style="display: block; width: 100%; max-width: 560px;',
            'width="999" style="display: block; width: 100%; max-width: 560px;',
            n=1,
        )
        assert any(v.startswith("img:") for v in _check(broken))
