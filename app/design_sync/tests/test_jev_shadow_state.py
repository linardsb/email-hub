"""Jev shadow state serializer on real fixtures (plan T5).

Fixture ids, all in the normalised tree of the tracked ``data/debug`` cases:

- R1 Starbucks case 6, section ``2833:1475`` (heuristic ``social`` / ``social-icons``):
  holds a node named ``mj-social`` and the legal ``Ref: 26-6-NWSL-3-0-0-EM-SR-NA-…`` text.
- R2 slate case 9, section ``2833:2117``: IMAGE ``2833:2126`` "afterIcon" (24x24)
  inside the ``mj-button`` FRAME ``2833:2123``.
- R3 maap case 5, sections ``2833:1643`` and ``2833:1650`` (heuristic ``hero`` /
  ``hero-block``): ``Sub-Headline`` text plus the product image.

A missing id is fixture drift and fails loudly; the fixtures are tracked.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest

from app.design_sync.jev_shadow import state as state_mod
from app.design_sync.jev_shadow.shadow import index_nodes
from app.design_sync.jev_shadow.state import SectionState, build_section_state
from app.design_sync.protocol import DesignNode
from app.design_sync.tests.jev_shadow_capture import CapturedCase, capture_case

_CASES = ("5", "6", "7", "8", "9", "10")
_HEX_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")
_PX_RE = re.compile(r"\d+(\.\d+)?\s*px")


@pytest.fixture(scope="module")
def cases() -> dict[str, CapturedCase]:
    return {c: capture_case(c) for c in _CASES}


def _state_for(case: CapturedCase, section_node_id: str) -> SectionState:
    nodes = index_nodes(case.structure)
    for i, match in enumerate(case.matches):
        if match.section.node_id == section_node_id:
            return build_section_state(match.section, nodes[section_node_id], i, len(case.matches))
    raise AssertionError(f"section {section_node_id} not in case {case.case_id} matches")


def _node(st: SectionState, figma_id: str) -> dict[str, Any]:
    short = st.short_id(figma_id)
    assert short is not None, f"node {figma_id} missing from state"
    nodes: list[dict[str, Any]] = st.state["nodes"]  # type: ignore[assignment]
    return next(n for n in nodes if n["id"] == short)


def _nodes(st: SectionState) -> list[dict[str, Any]]:
    return st.state["nodes"]  # type: ignore[return-value]


def test_r1_social_section_keeps_social_name_and_legal_text(
    cases: dict[str, CapturedCase],
) -> None:
    st = _state_for(cases["6"], "2833:1475")
    assert any(n["name"] == "mj-social" for n in _nodes(st))
    texts = [n.get("text", "") for n in _nodes(st)]
    assert any(t.startswith("Ref: 26-6-NWSL-3-0-0-EM-SR-NA-") for t in texts)


def test_r2_slate_after_icon_is_inside_button_and_icon_sized(
    cases: dict[str, CapturedCase],
) -> None:
    st = _state_for(cases["9"], "2833:2117")
    icon = _node(st, "2833:2126")
    assert icon["inside_button"] is True
    assert icon["size"] == "icon-sized"
    assert icon["type"] == "image"
    # ``mj-button`` sits inside the button-shaped ``mj-button-Frame`` wrapper;
    # the body text next to it (``mj-text`` 2833:2121) does not.
    assert _node(st, "2833:2123")["inside_button"] is True
    assert _node(st, "2833:2121")["inside_button"] is False


@pytest.mark.parametrize("section_id", ["2833:1643", "2833:1650"])
def test_r3_maap_hero_carries_subheadline_and_bucketed_image(
    cases: dict[str, CapturedCase], section_id: str
) -> None:
    st = _state_for(cases["5"], section_id)
    sub = [n for n in _nodes(st) if n["type"] == "text" and n["name"] == "Sub-Headline"]
    assert sub, "Sub-Headline text missing"
    assert any(n["text"].startswith("MAAP x KASK Protone Icon") for n in sub)
    assert all(n["size"] != "unknown" and n["role"] for n in sub)
    images = [n for n in _nodes(st) if n["type"] in ("image", "vector", "instance")]
    assert images
    assert all(n["size"] in {"icon-sized", "small", "half-width", "full-width"} for n in images)


def _expected_counts(case: CapturedCase, index: int, node: DesignNode) -> dict[str, int]:
    section = case.matches[index].section
    return {
        "texts": len(section.texts),
        "headings": len([t for t in section.texts if t.is_heading]),
        "images": len(section.images),
        "icon_sized_images": len(
            [
                i
                for i in section.images
                if i.width is not None and i.height is not None and max(i.width, i.height) <= 64
            ]
        ),
        "buttons": len(section.buttons),
        "direct_children": len([c for c in node.children if c.visible]),
    }


@pytest.mark.parametrize("case_id", _CASES)
def test_no_hex_no_px_and_counts_match(cases: dict[str, CapturedCase], case_id: str) -> None:
    case = cases[case_id]
    nodes = index_nodes(case.structure)
    for i, match in enumerate(case.matches):
        node = nodes[match.section.node_id]
        st = build_section_state(match.section, node, i, len(case.matches))
        dumped = json.dumps(st.state)
        assert _HEX_RE.search(dumped) is None, f"hex in section {i}"
        assert _PX_RE.search(dumped) is None, f"px in section {i}"
        counts: dict[str, int] = st.state["counts"]  # type: ignore[assignment]
        expected = _expected_counts(case, i, node)
        assert {k: counts[k] for k in expected} == expected
        assert counts["nodes_inside_buttons"] == sum(1 for n in _nodes(st) if n["inside_button"])
        assert set(st.ids) == {n["id"] for n in _nodes(st)}


def test_truncation_keeps_shallowest_nodes(
    cases: dict[str, CapturedCase], monkeypatch: pytest.MonkeyPatch
) -> None:
    case = cases["10"]
    nodes = index_nodes(case.structure)
    sizes = [
        (len(state_mod._walk(nodes[m.section.node_id])), i) for i, m in enumerate(case.matches)
    ]
    full_size, idx = max(sizes)
    assert full_size > 20
    match = case.matches[idx]
    monkeypatch.setattr(state_mod, "MAX_STATE_NODES", 20)
    st = build_section_state(match.section, nodes[match.section.node_id], idx, len(case.matches))
    kept = _nodes(st)
    assert st.state["truncated"] is True
    assert len(kept) == 20
    dropped_min_depth = min(
        d
        for n, d, _ in state_mod._walk(nodes[match.section.node_id])
        if n.id not in st.ids.values()
    )
    assert max(n["depth"] for n in kept) <= dropped_min_depth
