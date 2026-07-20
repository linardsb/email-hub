"""Detect N consecutive structurally similar sections and merge into RepeatingGroup."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.logging import get_logger
from app.design_sync.figma.layout_analyzer import (
    ColumnLayout,
    EmailSection,
    EmailSectionType,
)

logger = get_logger(__name__)

_SKIP_TYPES: frozenset[EmailSectionType] = frozenset(
    {
        EmailSectionType.DIVIDER,
        EmailSectionType.SPACER,
    }
)


@dataclass(frozen=True)
class SiblingSignature:
    """Structural fingerprint of a section for similarity comparison."""

    image_count: int
    text_count: int
    button_count: int
    has_heading: bool
    column_layout: ColumnLayout
    approx_height_bucket: int  # height // 20


@dataclass(frozen=True)
class BandRule:
    """A rule row re-injected between band members (item 1 · phase-53.5).

    ``group_by_wrapper``'s ``absorb_spacers`` drops DIVIDER pseudo-sections
    before render (A2-ratified). A DIVIDER that carried a stroke leaves this
    marker so the renderer re-injects a ``border-top`` rule row AFTER the member
    at ``after_member_index`` — the surviving member it originally followed.
    """

    after_member_index: int
    stroke_color: str
    stroke_weight: float | None = None


@dataclass(frozen=True)
class RepeatingGroup:
    """A group of structurally similar consecutive sections."""

    sections: list[EmailSection]
    container_bgcolor: str | None = None
    container_padding: tuple[float, float, float, float] | None = None
    pattern_component: str | None = None
    repeat_count: int = 0
    group_confidence: float = 0.0
    # item 1 (phase-53.5) — border-top rules for absorbed DIVIDER sections,
    # re-injected between members by ``render_repeating_group``.
    internal_rules: tuple[BandRule, ...] = ()

    def __post_init__(self) -> None:
        if self.repeat_count == 0:
            object.__setattr__(self, "repeat_count", len(self.sections))


_WEIGHTS: dict[str, float] = {
    "image_count": 0.30,
    "text_count": 0.25,
    "button_count": 0.15,
    "has_heading": 0.15,
    "column_layout": 0.10,
    "height_bucket": 0.05,
}


def detect_repeating_groups(
    sections: list[EmailSection],
    *,
    min_group_size: int = 2,
    similarity_threshold: float = 0.8,
) -> list[EmailSection | RepeatingGroup]:
    """Detect consecutive structurally similar sections and merge into groups.

    Returns mixed list: unchanged EmailSection for singles, RepeatingGroup for runs.
    DIVIDER/SPACER sections are never grouped but don't break runs.
    """
    if len(sections) < min_group_size:
        return list(sections)

    signatures = [_compute_signature(s) for s in sections]
    result: list[EmailSection | RepeatingGroup] = []
    i = 0

    while i < len(sections):
        if sections[i].section_type in _SKIP_TYPES:
            result.append(sections[i])
            i += 1
            continue

        # Try to extend a run of similar sections starting at i
        run = [i]
        j = i + 1
        skipped_indices: list[int] = []

        while j < len(sections):
            if sections[j].section_type in _SKIP_TYPES:
                skipped_indices.append(j)
                j += 1
                continue

            sim = _signature_similarity(signatures[i], signatures[j])
            if sim >= similarity_threshold:
                run.append(j)
                j += 1
            else:
                break

        if len(run) >= min_group_size:
            run_sections = [sections[idx] for idx in run]
            avg_sim = _average_pairwise_similarity(
                [signatures[idx] for idx in run],
            )
            container_bg = run_sections[0].bg_color

            group = RepeatingGroup(
                sections=run_sections,
                container_bgcolor=container_bg,
                group_confidence=avg_sim,
            )
            # Emit skipped DIVIDER/SPACER sections before the group
            for sk in skipped_indices:
                if sk < run[0]:
                    result.append(sections[sk])
            result.append(group)
            logger.info(
                "sibling.group_detected",
                repeat_count=len(run_sections),
                confidence=round(avg_sim, 3),
                first_node=run_sections[0].node_id,
            )
            i = j
        else:
            result.append(sections[i])
            i += 1

    return result


def group_by_wrapper(
    sections: list[EmailSection],
    *,
    absorb_spacers: bool = True,
) -> list[EmailSection | RepeatingGroup]:
    """Group consecutive sections sharing a ``parent_wrapper_id`` into bands.

    Phase 53 Track C1. Unlike :func:`detect_repeating_groups` — which re-derives
    structural similarity and is defeated by the alternating image/text card
    explosion a coloured wrapper produces — this uses the EXACT band membership
    ``_expand_container_wrappers`` already stamped at explosion time: every
    section carrying the same ``parent_wrapper_id`` came from one wrapper and is
    therefore one band.

    Design-agnostic: keys only on the wrapper id the unwrap pre-pass recorded,
    never on any specific design. A wrapper that exploded into a single section
    (``parent_wrapper_id`` set but no sibling) passes through as a solo section;
    sections with no ``parent_wrapper_id`` pass through unchanged.

    When ``absorb_spacers`` is set (Track C2), SPACER/DIVIDER pseudo-sections
    inside a band are dropped — they describe inter-card padding, not their own
    rendered row. A band's wrapper fill (``container_bg``) becomes the band
    background.

    NOTE (spike finding): grouping is unconditional on wrapper membership — a
    band is one visual unit regardless of whether its children are similar.
    Requiring similarity to group was prototyped (Track C2) and rejected: it
    splits LEGO's heterogeneous-but-single colour bands (content/content/footer
    under one wrapper), which must render as one section. The under-segmenter
    fix needs the opposite policy on the same signal — see the report / 53.1.
    """
    result: list[EmailSection | RepeatingGroup] = []
    i = 0
    n = len(sections)
    while i < n:
        wid = sections[i].parent_wrapper_id
        if wid is None:
            result.append(sections[i])
            i += 1
            continue

        run: list[EmailSection] = []
        j = i
        while j < n and sections[j].parent_wrapper_id == wid:
            run.append(sections[j])
            j += 1

        if absorb_spacers:
            members: list[EmailSection] = []
            internal_rules: list[BandRule] = []
            for s in run:
                if s.section_type in _SKIP_TYPES:
                    # A DIVIDER (not a SPACER) with a stroke leaves a rule after
                    # the member it followed; a leading divider (no preceding
                    # member) is dropped defensively. Hex-gating lives at render.
                    if s.section_type == EmailSectionType.DIVIDER and s.stroke_color and members:
                        internal_rules.append(
                            BandRule(
                                after_member_index=len(members) - 1,
                                stroke_color=s.stroke_color,
                                stroke_weight=s.stroke_weight,
                            )
                        )
                else:
                    members.append(s)
        else:
            members = list(run)
            internal_rules = []

        if len(members) >= 2:
            result.append(
                RepeatingGroup(
                    sections=members,
                    container_bgcolor=members[0].container_bg,
                    group_confidence=1.0,
                    internal_rules=tuple(internal_rules),
                )
            )
            logger.info(
                "sibling.wrapper_band_grouped",
                wrapper_id=wid,
                section_count=len(members),
                absorbed=len(run) - len(members),
            )
        else:
            # Single real child (or all-spacer band) — emit the surviving
            # sections individually so nothing is lost.
            result.extend(members or run)
        i = j

    return result


def _compute_signature(section: EmailSection) -> SiblingSignature:
    height_bucket = int((section.height if section.height is not None else 0) // 20)
    return SiblingSignature(
        image_count=len(section.images),
        text_count=len(section.texts),
        button_count=len(section.buttons),
        has_heading=any(t.is_heading for t in section.texts),
        column_layout=section.column_layout,
        approx_height_bucket=height_bucket,
    )


def _signature_similarity(a: SiblingSignature, b: SiblingSignature) -> float:
    score = 0.0
    score += _WEIGHTS["image_count"] * (1.0 if a.image_count == b.image_count else 0.0)
    score += _WEIGHTS["text_count"] * (1.0 if a.text_count == b.text_count else 0.0)
    score += _WEIGHTS["button_count"] * (1.0 if a.button_count == b.button_count else 0.0)
    score += _WEIGHTS["has_heading"] * (1.0 if a.has_heading == b.has_heading else 0.0)
    score += _WEIGHTS["column_layout"] * (1.0 if a.column_layout == b.column_layout else 0.0)
    score += _WEIGHTS["height_bucket"] * (
        1.0 if abs(a.approx_height_bucket - b.approx_height_bucket) <= 1 else 0.0
    )
    return score


def _average_pairwise_similarity(sigs: list[SiblingSignature]) -> float:
    if len(sigs) < 2:
        return 1.0
    total = sum(
        _signature_similarity(sigs[i], sigs[j])
        for i in range(len(sigs))
        for j in range(i + 1, len(sigs))
    )
    pairs = len(sigs) * (len(sigs) - 1) / 2
    return total / pairs
