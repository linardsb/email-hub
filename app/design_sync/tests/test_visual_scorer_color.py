# pyright: reportPrivateUsage=false
"""Phase 52.1 — proof that the fidelity metric is color-aware, blur-free, min-aggregated.

These tests prove the metric's CODE CORRECTNESS using synthetic PIL/numpy images
only — NO golden fixtures, NO Playwright, NO real ``visual_design.png`` references.
They do NOT prove the metric runs end-to-end on real designs; image registration
against a full-design screenshot remains unwired (see module docstring / report).

Defects fixed (RC-F), each pinned by a test below:
  1. Color-blindness: ``.convert("L")`` collapsed colour to luminance, so a wrong
     brand colour at matching luminance scored as PERFECT.
  2. Blur: sigma=1.0 default smoothed away the few-pixel edge errors the converter makes.
  3. Mean aggregation: one perfect section hid a totally broken one.
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image

from app.design_sync.figma.layout_analyzer import (
    ColumnLayout,
    EmailSection,
    EmailSectionType,
)
from app.design_sync.visual_scorer import score_fidelity

# Brand blue and a DIFFERENT hue (olive) chosen to have ~matching ITU-601
# luminance so the OLD grayscale path is blind to the difference.
_BRAND_BLUE = (26, 115, 232)  # #1a73e8
_OLIVE = (120, 108, 40)  # distinct hue, near-identical luminance


def _itu_luminance(rgb: tuple[int, int, int]) -> float:
    """ITU-R 601 luminance == what PIL ``.convert("L")`` computes."""
    r, g, b = rgb
    return 0.299 * r + 0.587 * g + 0.114 * b


def _solid_png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    img = Image.new("RGB", (width, height), rgb)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _array_to_png(arr: np.ndarray) -> bytes:
    img = Image.fromarray(arr.astype(np.uint8), mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_section(
    *,
    node_id: str = "1:1",
    node_name: str = "Hero",
    section_type: EmailSectionType = EmailSectionType.HERO,
    y_position: float = 0.0,
    height: float = 100.0,
) -> EmailSection:
    return EmailSection(
        section_type=section_type,
        node_id=node_id,
        node_name=node_name,
        y_position=y_position,
        width=100.0,
        height=height,
        column_layout=ColumnLayout.SINGLE,
    )


# ── 1. Color-awareness (the headline bug) ──


class TestColorAwareness:
    def test_old_grayscale_path_is_blind_to_these_colors(self) -> None:
        """Demonstrate the OLD blindness: ITU luminance collapses the two hues.

        ``.convert("L")`` would map both colours to (near-)identical grey, so the
        legacy grayscale metric saw them as the same pixel value.
        """
        l_blue = _itu_luminance(_BRAND_BLUE)
        l_olive = _itu_luminance(_OLIVE)
        # Within ~2/255 — the grayscale metric cannot tell these apart.
        assert abs(l_blue - l_olive) < 3.0

    def test_wrong_brand_color_scores_low(self) -> None:
        """New metric scores a wrong-hue/matching-luminance candidate LOW."""
        reference = _solid_png(100, 100, _BRAND_BLUE)
        candidate = _solid_png(100, 100, _OLIVE)
        sections = [_make_section(y_position=0, height=100)]

        result = score_fidelity(reference, candidate, sections, blur_sigma=0.0)

        # Old grayscale path would have scored these ~perfect (matched luminance);
        # the color-aware metric sees a large perceptual ΔE.
        assert result.overall < 0.6
        assert result.sections[0].ssim < 0.6

    def test_identical_color_still_perfect(self) -> None:
        """Same colour → perfect score (sanity that low score is hue-driven)."""
        ref = _solid_png(100, 100, _BRAND_BLUE)
        sections = [_make_section(y_position=0, height=100)]
        result = score_fidelity(ref, ref, sections, blur_sigma=0.0)
        assert result.overall >= 0.99


# ── 2. Min aggregation (worst section dominates) ──


class TestMinAggregation:
    def test_one_broken_section_dominates(self) -> None:
        """3 sections, 2 perfect + 1 wrong-hue → overall ≈ MIN, not mean."""
        # img height == sum of section heights so bands map 1:1 (scale == 1).
        height_each = 100
        ref_arr = np.zeros((3 * height_each, 100, 3), dtype=np.uint8)
        cand_arr = np.zeros((3 * height_each, 100, 3), dtype=np.uint8)

        # Sections 0 and 1 identical (perfect); section 2 wrong hue (broken).
        for band, color in enumerate([_BRAND_BLUE, (200, 50, 50)]):
            ref_arr[band * height_each : (band + 1) * height_each] = color
            cand_arr[band * height_each : (band + 1) * height_each] = color
        # Broken band: reference blue, candidate olive (matched luminance).
        ref_arr[2 * height_each :] = _BRAND_BLUE
        cand_arr[2 * height_each :] = _OLIVE

        sections = [
            _make_section(node_id="1:1", y_position=0, height=height_each),
            _make_section(node_id="1:2", y_position=height_each, height=height_each),
            _make_section(node_id="1:3", y_position=2 * height_each, height=height_each),
        ]

        result = score_fidelity(_array_to_png(ref_arr), _array_to_png(cand_arr), sections)

        assert len(result.sections) == 3
        scores = [s.ssim for s in result.sections]
        broken = min(scores)
        # Overall is the MIN section score, not the (much higher) mean.
        assert result.overall == broken
        assert result.overall < float(np.mean(scores))
        # And the broken section really is the wrong one.
        assert result.sections[2].ssim == broken
        assert result.sections[0].ssim >= 0.99
        assert result.sections[1].ssim >= 0.99


# ── 3. Identity ──


class TestIdentity:
    def test_identical_images_perfect(self) -> None:
        ref = _solid_png(120, 90, (45, 130, 90))
        sections = [_make_section(y_position=0, height=90)]
        result = score_fidelity(ref, ref, sections, blur_sigma=0.0)
        assert result.overall >= 0.99


# ── 4. No-blur (edges are not smoothed away) ──


class TestNoBlur:
    @staticmethod
    def _stripes(width: int, height: int, *, shift: int) -> np.ndarray:
        """Vertical 2px-wide black/white stripes (period 4), shifted by `shift` px."""
        arr = np.zeros((height, width, 3), dtype=np.uint8)
        cols = ((np.arange(width) + shift) // 2) % 2 == 0
        arr[:, cols] = 255
        return arr

    def test_two_px_shift_high_frequency_pattern_scores_below_one(self) -> None:
        """A 2px-shifted high-frequency stripe pattern scores meaningfully < 1.0.

        Proves edges are not smoothed away: a 2px shift on a period-4 stripe
        pattern flips every stripe black<->white. A blurring metric would wash
        this out toward 1.0; the blur-free metric registers a large error.
        """
        ref = self._stripes(100, 100, shift=0)
        cand = self._stripes(100, 100, shift=2)  # half-period shift → phase flip
        sections = [_make_section(y_position=0, height=100)]

        # Default blur_sigma == 0.0 — no smoothing.
        result = score_fidelity(_array_to_png(ref), _array_to_png(cand), sections)

        assert result.overall < 0.95
