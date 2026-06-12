"""Tests for sibling pattern detector — repeated-content grouping (Phase 49.1)."""

from __future__ import annotations

from app.design_sync.figma.layout_analyzer import (
    ButtonElement,
    ColumnLayout,
    EmailSection,
    EmailSectionType,
    ImagePlaceholder,
    TextBlock,
)
from app.design_sync.sibling_detector import (
    RepeatingGroup,
    _compute_signature,
    _signature_similarity,
    detect_repeating_groups,
    group_by_wrapper,
)


def _make_section(
    section_type: EmailSectionType = EmailSectionType.CONTENT,
    *,
    node_id: str = "frame_1",
    texts: list[TextBlock] | None = None,
    images: list[ImagePlaceholder] | None = None,
    buttons: list[ButtonElement] | None = None,
    column_layout: ColumnLayout = ColumnLayout.SINGLE,
    height: float | None = 200,
    bg_color: str | None = None,
) -> EmailSection:
    return EmailSection(
        section_type=section_type,
        node_id=node_id,
        node_name="Section",
        texts=texts or [],
        images=images or [],
        buttons=buttons or [],
        column_layout=column_layout,
        column_count=1,
        height=height,
        bg_color=bg_color,
        column_groups=[],
    )


def _text(content: str = "Hello", *, is_heading: bool = False) -> TextBlock:
    return TextBlock(node_id="t1", content=content, is_heading=is_heading)


def _image(node_id: str = "img_1") -> ImagePlaceholder:
    return ImagePlaceholder(node_id=node_id, node_name="photo", width=600, height=400)


def _button(text: str = "Click me") -> ButtonElement:
    return ButtonElement(node_id="btn_1", text=text)


class TestSiblingSignature:
    """Test signature computation from EmailSection."""

    def test_compute_signature_basic(self) -> None:
        section = _make_section(
            texts=[_text("Title", is_heading=True), _text("Body")],
            images=[_image()],
            height=200,
        )
        sig = _compute_signature(section)

        assert sig.image_count == 1
        assert sig.text_count == 2
        assert sig.button_count == 0
        assert sig.has_heading is True
        assert sig.column_layout == ColumnLayout.SINGLE
        assert sig.approx_height_bucket == 10  # 200 // 20

    def test_height_bucketing(self) -> None:
        s120 = _make_section(height=120)
        s135 = _make_section(height=135)
        s160 = _make_section(height=160)

        sig120 = _compute_signature(s120)
        sig135 = _compute_signature(s135)
        sig160 = _compute_signature(s160)

        assert sig120.approx_height_bucket == 6  # 120 // 20
        assert sig135.approx_height_bucket == 6  # 135 // 20 = 6
        assert sig160.approx_height_bucket == 8  # 160 // 20

    def test_empty_section(self) -> None:
        section = _make_section(height=0)
        sig = _compute_signature(section)

        assert sig.image_count == 0
        assert sig.text_count == 0
        assert sig.button_count == 0
        assert sig.has_heading is False
        assert sig.approx_height_bucket == 0


class TestSignatureSimilarity:
    """Test weighted similarity scoring between signatures."""

    def test_identical_signatures(self) -> None:
        section = _make_section(
            texts=[_text()],
            images=[_image()],
            buttons=[_button()],
            height=200,
        )
        sig = _compute_signature(section)
        assert _signature_similarity(sig, sig) == 1.0

    def test_completely_different(self) -> None:
        s1 = _make_section(
            texts=[_text("A", is_heading=True)],
            images=[_image()],
            height=200,
            column_layout=ColumnLayout.SINGLE,
        )
        s2 = _make_section(
            texts=[],
            images=[],
            buttons=[_button(), _button()],
            height=500,
            column_layout=ColumnLayout.TWO_COLUMN,
        )
        sig1 = _compute_signature(s1)
        sig2 = _compute_signature(s2)
        assert _signature_similarity(sig1, sig2) == 0.0

    def test_partial_match(self) -> None:
        """Same images and texts, different buttons → 0.85."""
        s1 = _make_section(
            texts=[_text()],
            images=[_image()],
            height=200,
        )
        s2 = _make_section(
            texts=[_text()],
            images=[_image()],
            buttons=[_button()],
            height=200,
        )
        sig1 = _compute_signature(s1)
        sig2 = _compute_signature(s2)
        sim = _signature_similarity(sig1, sig2)
        # image_count(0.30) + text_count(0.25) + has_heading(0.15) + column_layout(0.10) + height(0.05) = 0.85
        assert abs(sim - 0.85) < 1e-9


class TestDetectRepeatingGroups:
    """Test the main detect_repeating_groups() entry point."""

    def test_five_identical_sections_grouped(self) -> None:
        """5 icon+heading+body sections → 1 RepeatingGroup(5)."""
        sections = [
            _make_section(
                node_id=f"frame_{i}",
                texts=[_text("Title", is_heading=True), _text("Body text")],
                images=[_image(node_id=f"img_{i}")],
                height=200,
            )
            for i in range(5)
        ]
        result = detect_repeating_groups(sections)

        assert len(result) == 1
        group = result[0]
        assert isinstance(group, RepeatingGroup)
        assert group.repeat_count == 5
        assert len(group.sections) == 5
        assert group.group_confidence == 1.0

    def test_three_product_cards(self) -> None:
        """3 image+text+button sections → 1 RepeatingGroup(3)."""
        sections = [
            _make_section(
                node_id=f"card_{i}",
                texts=[_text("Product name")],
                images=[_image(node_id=f"prod_{i}")],
                buttons=[_button("Buy")],
                height=300,
            )
            for i in range(3)
        ]
        result = detect_repeating_groups(sections)

        assert len(result) == 1
        assert isinstance(result[0], RepeatingGroup)
        assert result[0].repeat_count == 3

    def test_mixed_sections_only_similar_grouped(self) -> None:
        """hero, text, 5 reasons, footer → [hero, text, group(5), footer]."""
        hero = _make_section(
            node_id="hero",
            section_type=EmailSectionType.HERO,
            images=[_image()],
            height=500,
        )
        text = _make_section(
            node_id="text",
            texts=[_text("Intro paragraph")],
            height=100,
        )
        reasons = [
            _make_section(
                node_id=f"reason_{i}",
                texts=[_text("Reason", is_heading=True), _text("Description")],
                images=[_image(node_id=f"icon_{i}")],
                height=200,
            )
            for i in range(5)
        ]
        footer = _make_section(
            node_id="footer",
            section_type=EmailSectionType.FOOTER,
            texts=[_text("Unsubscribe")],
            height=80,
        )

        sections = [hero, text, *reasons, footer]
        result = detect_repeating_groups(sections)

        assert len(result) == 4
        assert isinstance(result[0], EmailSection)  # hero
        assert isinstance(result[1], EmailSection)  # text
        assert isinstance(result[2], RepeatingGroup)  # 5 reasons
        assert result[2].repeat_count == 5
        assert isinstance(result[3], EmailSection)  # footer

    def test_divider_between_similar_breaks_nothing(self) -> None:
        """DIVIDER inside run of 3 similar → still group(3), DIVIDER preserved."""
        similar = [
            _make_section(
                node_id=f"item_{i}",
                texts=[_text("Item")],
                images=[_image(node_id=f"img_{i}")],
                height=200,
            )
            for i in range(3)
        ]
        divider = _make_section(
            node_id="div",
            section_type=EmailSectionType.DIVIDER,
            height=10,
        )
        # Insert divider between item 1 and item 2
        sections = [similar[0], divider, similar[1], similar[2]]
        result = detect_repeating_groups(sections)

        # The divider is skipped during grouping but preserved in output
        groups = [r for r in result if isinstance(r, RepeatingGroup)]
        assert len(groups) == 1
        assert groups[0].repeat_count == 3

    def test_single_section_no_grouping(self) -> None:
        sections = [_make_section()]
        result = detect_repeating_groups(sections)

        assert len(result) == 1
        assert isinstance(result[0], EmailSection)

    def test_below_min_group_size(self) -> None:
        """1 similar pair with min_group=3 → no grouping."""
        sections = [
            _make_section(node_id="a", texts=[_text()], height=200),
            _make_section(node_id="b", texts=[_text()], height=200),
        ]
        result = detect_repeating_groups(sections, min_group_size=3)

        assert len(result) == 2
        assert all(isinstance(r, EmailSection) for r in result)


class TestConfig:
    """Test config integration."""

    def test_threshold_respected(self) -> None:
        """threshold=1.0 → no groups when minor height diff exists."""
        sections = [
            _make_section(node_id="a", texts=[_text()], height=200),
            _make_section(node_id="b", texts=[_text()], height=220),
            _make_section(node_id="c", texts=[_text()], height=240),
        ]
        # Height buckets: 10, 11, 12 — adjacent pairs are within ±1 but
        # with threshold=1.0, even the height_bucket tolerance isn't enough
        # if any other field differs. Here all other fields match, so
        # a vs b → height_bucket 0.05 penalty → 0.95, below 1.0
        result = detect_repeating_groups(sections, similarity_threshold=1.0)

        # a(200→bucket 10) vs b(220→bucket 11): within ±1 → match → 1.0
        # b(220→bucket 11) vs c(240→bucket 12): within ±1 → match → 1.0
        # But a(10) vs c(12): diff=2, not within ±1 → 0.95
        # Run starts at a: a→b (1.0 ≥ 1.0 ✓), a→c (0.95 < 1.0 ✗) → group(a,b), then c alone
        assert len(result) == 2

    def test_disabled_returns_original(self) -> None:
        """When detection is disabled the sections pass through unchanged."""
        sections = [_make_section(node_id=f"s_{i}", texts=[_text()], height=200) for i in range(5)]
        # We can't easily pass the config flag here since detect_repeating_groups
        # doesn't take an enabled flag — the caller (converter_service) checks it.
        # Instead verify min_group_size > len(sections) produces passthrough.
        result = detect_repeating_groups(sections, min_group_size=100)

        assert len(result) == 5
        assert all(isinstance(r, EmailSection) for r in result)


def _wrapped_section(
    *,
    node_id: str,
    parent_wrapper_id: str | None,
    container_bg: str | None = None,
    section_type: EmailSectionType = EmailSectionType.CONTENT,
    images: list[ImagePlaceholder] | None = None,
) -> EmailSection:
    """An EmailSection carrying the band tags the wrapper unwrap pre-pass stamps."""
    return EmailSection(
        section_type=section_type,
        node_id=node_id,
        node_name="Section",
        texts=[_text()],
        images=images or [],
        buttons=[],
        column_layout=ColumnLayout.SINGLE,
        column_count=1,
        height=200,
        bg_color=None,
        column_groups=[],
        container_bg=container_bg,
        parent_wrapper_id=parent_wrapper_id,
    )


class TestGroupByWrapper:
    """Phase 53 C1/C2 — band grouping by exact parent_wrapper_id."""

    def test_shared_wrapper_id_collapses_to_one_band(self) -> None:
        sections = [
            _wrapped_section(node_id="a", parent_wrapper_id="w1", container_bg="#AA1733"),
            _wrapped_section(node_id="b", parent_wrapper_id="w1", container_bg="#AA1733"),
            _wrapped_section(node_id="c", parent_wrapper_id="w1", container_bg="#AA1733"),
        ]
        result = group_by_wrapper(sections)
        assert len(result) == 1
        band = result[0]
        assert isinstance(band, RepeatingGroup)
        assert len(band.sections) == 3
        assert band.container_bgcolor == "#AA1733"

    def test_no_wrapper_id_passes_through_solo(self) -> None:
        sections = [
            _wrapped_section(node_id="a", parent_wrapper_id=None),
            _wrapped_section(node_id="b", parent_wrapper_id=None),
        ]
        result = group_by_wrapper(sections)
        assert len(result) == 2
        assert all(isinstance(r, EmailSection) for r in result)

    def test_single_member_wrapper_stays_solo(self) -> None:
        sections = [_wrapped_section(node_id="a", parent_wrapper_id="w1")]
        result = group_by_wrapper(sections)
        assert len(result) == 1
        assert isinstance(result[0], EmailSection)

    def test_distinct_wrapper_ids_form_distinct_bands(self) -> None:
        sections = [
            _wrapped_section(node_id="a", parent_wrapper_id="w1"),
            _wrapped_section(node_id="b", parent_wrapper_id="w1"),
            _wrapped_section(node_id="c", parent_wrapper_id="w2"),
            _wrapped_section(node_id="d", parent_wrapper_id="w2"),
        ]
        result = group_by_wrapper(sections)
        assert len(result) == 2
        assert all(isinstance(r, RepeatingGroup) for r in result)

    def test_spacer_absorbed_inside_band(self) -> None:
        sections = [
            _wrapped_section(node_id="a", parent_wrapper_id="w1"),
            _wrapped_section(
                node_id="sp", parent_wrapper_id="w1", section_type=EmailSectionType.SPACER
            ),
            _wrapped_section(node_id="b", parent_wrapper_id="w1"),
        ]
        result = group_by_wrapper(sections, absorb_spacers=True)
        assert len(result) == 1
        band = result[0]
        assert isinstance(band, RepeatingGroup)
        # SPACER dropped — only the two real cards remain as rendered rows.
        assert [s.node_id for s in band.sections] == ["a", "b"]

    def test_spacer_retained_when_absorb_off(self) -> None:
        sections = [
            _wrapped_section(node_id="a", parent_wrapper_id="w1"),
            _wrapped_section(
                node_id="sp", parent_wrapper_id="w1", section_type=EmailSectionType.SPACER
            ),
            _wrapped_section(node_id="b", parent_wrapper_id="w1"),
        ]
        result = group_by_wrapper(sections, absorb_spacers=False)
        band = result[0]
        assert isinstance(band, RepeatingGroup)
        assert len(band.sections) == 3

    def test_heterogeneous_band_still_groups(self) -> None:
        # A coloured wrapper holding content + content + footer is ONE visual
        # band and must collapse to one section regardless of dissimilarity
        # (the LEGO wrapper-2040 case). Grouping keys on membership, not shape.
        sections = [
            _wrapped_section(node_id="a", parent_wrapper_id="w1"),
            _wrapped_section(node_id="b", parent_wrapper_id="w1", images=[_image()]),
            _wrapped_section(
                node_id="c", parent_wrapper_id="w1", section_type=EmailSectionType.FOOTER
            ),
        ]
        result = group_by_wrapper(sections)
        assert len(result) == 1
        assert isinstance(result[0], RepeatingGroup)
