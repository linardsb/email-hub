"""Tests for physical-card-surface detection (Phase 50.7, Rule 9 prep)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.design_sync.diagnose.report import load_structure_from_json
from app.design_sync.figma.physical_card_detector import (
    collect_sibling_radii,
    detect_physical_card_surface,
)
from app.design_sync.protocol import DesignFileStructure, DesignNode, DesignNodeType

_LEGO_FIXTURE = Path(__file__).resolve().parents[3] / "data" / "debug" / "7" / "structure.json"


def _node(
    *,
    node_id: str = "n1",
    name: str = "frame",
    node_type: DesignNodeType = DesignNodeType.FRAME,
    width: float | None = None,
    height: float | None = None,
    fill_color: str | None = None,
    corner_radius: float | None = None,
    corner_radii: tuple[float, ...] | None = None,
    image_ref: str | None = None,
    children: list[DesignNode] | None = None,
) -> DesignNode:
    return DesignNode(
        id=node_id,
        name=name,
        type=node_type,
        children=children or [],
        width=width,
        height=height,
        fill_color=fill_color,
        corner_radius=corner_radius,
        corner_radii=corner_radii,
        image_ref=image_ref,
    )


def _image(
    *,
    width: float,
    height: float,
    node_id: str = "img",
    name: str = "image",
) -> DesignNode:
    return _node(
        node_id=node_id,
        name=name,
        node_type=DesignNodeType.IMAGE,
        width=width,
        height=height,
    )


# ── Aspect ratio signal ────────────────────────────────────────────────────


class TestAspectRatioSignal:
    def test_id_1_aspect_ratio(self) -> None:
        card = _node(width=600, height=378)  # 1.587 — within 5% of 1.586
        result = detect_physical_card_surface(card)
        assert "aspect_ratio_id_1" in result.signals

    def test_loyalty_aspect_ratio(self) -> None:
        card = _node(width=600, height=300)  # 2.0
        result = detect_physical_card_surface(card)
        assert "aspect_ratio_loyalty" in result.signals

    def test_boarding_pass_aspect_ratio(self) -> None:
        card = _node(width=600, height=450)  # 1.333
        result = detect_physical_card_surface(card)
        assert "aspect_ratio_boarding_pass" in result.signals

    def test_aspect_ratio_outside_tolerance(self) -> None:
        card = _node(width=600, height=500)  # 1.2 — not near any target
        result = detect_physical_card_surface(card)
        assert all(not s.startswith("aspect_ratio_") for s in result.signals)


# ── Barcode signal ─────────────────────────────────────────────────────────


class TestBarcodeSignal:
    def test_barcode_child_detected(self) -> None:
        card = _node(
            width=600,
            height=600,  # square — no aspect signal
            children=[_image(width=440, height=90)],  # 4.89 ratio
        )
        result = detect_physical_card_surface(card)
        assert "barcode_child" in result.signals

    def test_no_barcode_when_below_ratio(self) -> None:
        card = _node(
            width=600,
            height=600,
            children=[_image(width=200, height=200)],  # 1:1
        )
        result = detect_physical_card_surface(card)
        assert "barcode_child" not in result.signals

    def test_barcode_via_image_ref_frame(self) -> None:
        # FRAME with image_ref counts as image-bearing.
        barcode = _node(
            node_id="bc",
            node_type=DesignNodeType.FRAME,
            width=480,
            height=80,
            image_ref="abc123",
        )
        card = _node(width=600, height=600, children=[barcode])
        result = detect_physical_card_surface(card)
        assert "barcode_child" in result.signals


# ── Logo on white field ────────────────────────────────────────────────────


class TestLogoOnWhiteField:
    def test_logo_on_white_field(self) -> None:
        white_field = _node(
            node_id="wf",
            width=200,
            height=200,
            fill_color="#FFFFFF",
            children=[_image(width=100, height=40)],  # 4000 / 40000 = 10%
        )
        card = _node(width=600, height=600, children=[white_field])
        result = detect_physical_card_surface(card)
        assert "logo_on_white_field" in result.signals

    def test_no_logo_on_non_white_field(self) -> None:
        lime_field = _node(
            node_id="lf",
            width=200,
            height=200,
            fill_color="#A4D65E",
            children=[_image(width=100, height=40)],
        )
        card = _node(width=600, height=600, children=[lime_field])
        result = detect_physical_card_surface(card)
        assert "logo_on_white_field" not in result.signals

    def test_no_logo_when_image_too_large(self) -> None:
        white_field = _node(
            node_id="wf",
            width=200,
            height=200,
            fill_color="#ffffff",
            children=[_image(width=180, height=180)],  # 81% fill — full content
        )
        card = _node(width=600, height=600, children=[white_field])
        result = detect_physical_card_surface(card)
        assert "logo_on_white_field" not in result.signals


# ── Distinct corner radius ─────────────────────────────────────────────────


class TestDistinctCornerRadius:
    def test_distinct_corner_radius(self) -> None:
        card = _node(width=600, height=600, corner_radius=24)
        result = detect_physical_card_surface(card, sibling_radii=[8.0, 8.0])
        assert "distinct_corner_radius" in result.signals

    def test_no_distinct_radius_when_matches_siblings(self) -> None:
        card = _node(width=600, height=600, corner_radius=24)
        result = detect_physical_card_surface(card, sibling_radii=[24.0, 8.0])
        assert "distinct_corner_radius" not in result.signals

    def test_no_signal_below_min_radius(self) -> None:
        card = _node(width=600, height=600, corner_radius=8)
        result = detect_physical_card_surface(card, sibling_radii=[0.0])
        assert "distinct_corner_radius" not in result.signals

    def test_falls_back_to_corner_radii_per_corner(self) -> None:
        # Figma exports per-corner radii in ``corner_radii`` and may leave
        # ``corner_radius`` as ``None``. Detector mirrors layout_analyzer's
        # ``_resolve_corner_radius`` and uses the per-corner max.
        card = _node(
            width=600,
            height=600,
            corner_radius=None,
            corner_radii=(24.0, 24.0, 24.0, 24.0),
        )
        result = detect_physical_card_surface(card, sibling_radii=[8.0])
        assert "distinct_corner_radius" in result.signals

    def test_corner_radii_uses_max(self) -> None:
        # Mixed radii — the max corner is what defines the visual radius for
        # purposes of physical-card detection (matches layout_analyzer pattern).
        card = _node(
            width=600,
            height=600,
            corner_radius=None,
            corner_radii=(0.0, 0.0, 24.0, 24.0),
        )
        result = detect_physical_card_surface(card, sibling_radii=[0.0])
        assert "distinct_corner_radius" in result.signals


# ── Aggregate threshold ────────────────────────────────────────────────────


class TestPhysicalThreshold:
    def test_physical_when_two_signals_fire(self) -> None:
        # 600x378 (ID-1) + barcode descendant -> 2 signals
        card = _node(
            width=600,
            height=378,
            children=[_image(width=440, height=90)],
        )
        result = detect_physical_card_surface(card)
        assert result.is_physical is True
        assert len(result.signals) >= 2

    def test_not_physical_with_one_signal(self) -> None:
        # Square card with barcode — only 1 signal
        card = _node(
            width=600,
            height=600,
            children=[_image(width=440, height=90)],
        )
        result = detect_physical_card_surface(card)
        assert result.is_physical is False
        assert result.signals == ("barcode_child",)

    def test_lego_membership_card_pattern(self) -> None:
        # LEGO Insiders membership card: 24px corner radius, white field with
        # logo, barcode strip — three signals fire.
        white_logo_field = _node(
            node_id="logo_wrap",
            width=200,
            height=200,
            fill_color="#ffffff",
            children=[_image(node_id="logo", width=120, height=48)],
        )
        barcode = _image(node_id="barcode", width=440, height=90)
        card = _node(
            node_id="membership",
            width=600,
            height=378,  # also matches ID-1
            corner_radius=24,
            children=[white_logo_field, barcode],
        )
        result = detect_physical_card_surface(card, sibling_radii=[8.0])
        assert result.is_physical is True
        assert "logo_on_white_field" in result.signals
        assert "barcode_child" in result.signals
        assert "distinct_corner_radius" in result.signals


# ── Real-fixture validation (Phase 50.8) ───────────────────────────────────


def _find_membership_card(
    structure: DesignFileStructure,
) -> tuple[DesignNode, DesignNode]:
    """Return (card_node, parent_node) for the LEGO membership card.

    The card is an ``mj-section`` with ``corner_radius=18`` nested inside a
    top-level ``mj-wrapper``. Walking by attribute keeps the test resilient to
    Figma frame-order churn.
    """
    for page in structure.pages:
        for root in page.children:
            for section in root.children:
                for wrapper in section.children:
                    if (
                        wrapper.type == DesignNodeType.FRAME
                        and wrapper.name == "mj-section"
                        and wrapper.corner_radius == 18.0
                    ):
                        return wrapper, section
    msg = "LEGO membership card mj-section (radius=18) not found in structure.json"
    raise AssertionError(msg)


class TestLEGORealFixture:
    """AC #4 closure — detector validated against real LEGO Figma extract.

    The production ``layout_analyzer`` pipeline does NOT currently surface this
    detection because the card is nested inside a top-level ``mj-wrapper`` and
    detection runs only on top-level sections (tracked separately as
    ``phase-50.8-nested-physical-cards`` in ``.agents/deferred-items.json``).
    """

    def test_lego_membership_card_detected_on_real_fixture(self) -> None:
        if not _LEGO_FIXTURE.exists():
            pytest.skip(f"LEGO fixture missing: {_LEGO_FIXTURE}")

        structure = load_structure_from_json(_LEGO_FIXTURE)
        card, parent = _find_membership_card(structure)

        sibling_radii = collect_sibling_radii(
            parent.children,
            exclude_node_id=card.id,
        )

        detection = detect_physical_card_surface(
            card,
            sibling_radii=sibling_radii,
            min_signals=2,
        )

        assert detection.is_physical is True, (
            f"LEGO card not classified as physical; signals={detection.signals}"
        )
        assert "barcode_child" in detection.signals
        assert "distinct_corner_radius" in detection.signals


# ── Sibling radii helper ───────────────────────────────────────────────────


class TestCollectSiblingRadii:
    def test_excludes_self_and_drops_none(self) -> None:
        nodes = [
            _node(node_id="a", corner_radius=8),
            _node(node_id="b", corner_radius=24),
            _node(node_id="c", corner_radius=None),
        ]
        radii = collect_sibling_radii(nodes, exclude_node_id="b")
        assert radii == [8.0]
