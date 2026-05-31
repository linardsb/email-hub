# pyright: reportUnknownVariableType=false, reportAssignmentType=false
# pyright: reportUnknownArgumentType=false
"""Color-aware visual fidelity scoring for Figma-to-HTML conversion.

Compares a Figma frame screenshot against the rendered HTML screenshot,
producing per-section fidelity scores and a visual diff overlay.

The metric is perceptual and color-aware: per-pixel **CIEDE2000 ΔE** in
CIELAB space (``skimage.color.deltaE_ciede2000`` over ``rgb2lab``). The
mean ΔE of a region maps to a 0-1 similarity score. The legacy grayscale
SSIM path was color-blind — a wrong brand colour at matching luminance
scored as perfect — which is exactly the converter's main failure mode.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Literal

import numpy as np
from PIL import Image
from skimage.color import deltaE_ciede2000, rgb2lab

from app.core.logging import get_logger
from app.design_sync.figma.layout_analyzer import EmailSection
from app.shared.imaging import safe_image_open

logger = get_logger(__name__)

# Minimum section height in pixels for scoring to be meaningful
_MIN_SECTION_HEIGHT_PX = 8

# Luminance difference threshold for diff overlay (0-255 scale)
_DIFF_LUMINANCE_THRESHOLD = 51  # ~20% of 255

# Maximum perceptual CIEDE2000 ΔE used to normalise the similarity score.
# Black↔white is ΔE2000 ≈ 100 (the practical maximum for sRGB), so a region
# that differs maximally scores 0.0 and an identical region scores 1.0.
# For reference, ΔE ≈ 2.3 is the "just noticeable difference" threshold.
_DELTA_E_MAX = 100.0


@dataclass(frozen=True)
class SectionScore:
    """Per-section color-aware fidelity score."""

    section_id: str
    section_name: str
    section_type: str
    # Color-aware similarity (CIEDE2000-derived), 0.0-1.0. Field kept named
    # ``ssim`` for consumer back-compat; the value is no longer SSIM.
    ssim: float
    y_start: int  # pixel row in image
    y_end: int


@dataclass(frozen=True)
class FidelityScore:
    """Aggregate fidelity scoring result."""

    overall: float  # 0.0-1.0 (min color-aware score — worst section dominates)
    sections: list[SectionScore]
    diff_image: bytes | None  # Red-highlighted diff overlay PNG


def _load_rgb(image_bytes: bytes) -> np.ndarray:
    """Load PNG bytes as a float64 RGB numpy array (H, W, 3)."""
    img = safe_image_open(io.BytesIO(image_bytes)).convert("RGB")
    return np.asarray(img, dtype=np.float64)


def _to_grayscale(rgb: np.ndarray) -> np.ndarray:
    """Collapse an RGB float64 array to ITU-R 601 luminance (for the diff overlay)."""
    return rgb @ np.array([0.299, 0.587, 0.114], dtype=np.float64)


def _pad_to_match(img_a: np.ndarray, img_b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Pad RGB images with white (255.0) so both have the same H and W."""
    max_h = max(img_a.shape[0], img_b.shape[0])
    max_w = max(img_a.shape[1], img_b.shape[1])

    def _pad(img: np.ndarray) -> np.ndarray:
        if img.shape[0] == max_h and img.shape[1] == max_w:
            return img
        padded = np.full((max_h, max_w, img.shape[2]), 255.0, dtype=np.float64)
        padded[: img.shape[0], : img.shape[1], :] = img
        return padded

    return _pad(img_a), _pad(img_b)


def _apply_blur(img: np.ndarray, sigma: float) -> np.ndarray:
    """Apply per-channel Gaussian blur (no cross-channel mixing) to an RGB array."""
    if sigma <= 0:
        return img
    from scipy.ndimage import gaussian_filter  # type: ignore[import-untyped]

    # sigma=0 on the channel axis keeps R/G/B from bleeding into each other.
    result: np.ndarray = gaussian_filter(img, sigma=(sigma, sigma, 0))
    return result


def _color_similarity(rgb_a: np.ndarray, rgb_b: np.ndarray) -> float:
    """Color-aware similarity from mean per-pixel CIEDE2000 ΔE.

    Both inputs are RGB float64 arrays (H, W, 3) on a 0-255 scale. Returns a
    0-1 score: ``max(0, 1 - mean(ΔE) / _DELTA_E_MAX)`` — 1.0 = perceptually
    identical, 0.0 = maximal perceptual difference (≈ black↔white).
    """
    lab_a: np.ndarray = rgb2lab(rgb_a / 255.0)
    lab_b: np.ndarray = rgb2lab(rgb_b / 255.0)
    delta_e: np.ndarray = deltaE_ciede2000(lab_a, lab_b)  # type: ignore[no-untyped-call]
    mean_delta_e = float(np.mean(delta_e))
    score = 1.0 - (mean_delta_e / _DELTA_E_MAX)
    return float(np.clip(score, 0.0, 1.0))


def _generate_diff_image(figma_gray: np.ndarray, html_gray: np.ndarray) -> bytes:
    """Generate a red-highlighted diff overlay PNG (luminance-based overlay)."""
    diff = np.abs(figma_gray - html_gray)

    # Create RGB image from figma reference as base
    _h, _w = figma_gray.shape
    rgb = np.stack([figma_gray] * 3, axis=-1).astype(np.uint8)

    # Highlight pixels exceeding luminance threshold in red
    mask = diff > _DIFF_LUMINANCE_THRESHOLD
    rgb[mask] = [255, 0, 0]

    img = Image.fromarray(rgb, mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def score_fidelity(
    figma_image: bytes,
    html_image: bytes,
    sections: list[EmailSection],
    *,
    blur_sigma: float = 0.0,
    win_size: int = 7,  # noqa: ARG001 — retained for caller back-compat (legacy SSIM window)
) -> FidelityScore:
    """Compare Figma frame image against rendered HTML screenshot.

    Color-aware, blur-free, min-aggregated. Each region's score is the mean
    per-pixel CIEDE2000 ΔE mapped to 0-1 (see ``_color_similarity``); the
    overall score is the **minimum** section score so one broken section
    cannot be hidden by perfect siblings.

    Args:
        figma_image: PNG bytes of the Figma frame export.
        html_image: PNG bytes of the rendered HTML screenshot.
        sections: Layout sections with y_position/height for per-section scoring.
        blur_sigma: Optional Gaussian blur sigma (per-channel) to smooth
            anti-aliasing. Defaults to 0.0 (no smoothing) so few-pixel spacing
            and edge errors are not washed out. Kept for caller back-compat.
        win_size: Unused. Retained so existing callers passing the legacy SSIM
            window size keep working.

    Returns:
        FidelityScore with overall (min) score, per-section scores, and diff image.
    """
    figma_rgb = _load_rgb(figma_image)
    html_rgb = _load_rgb(html_image)

    # Pad to match dimensions
    figma_rgb, html_rgb = _pad_to_match(figma_rgb, html_rgb)

    # Optional anti-aliasing smoothing (off by default).
    figma_proc = _apply_blur(figma_rgb, blur_sigma)
    html_proc = _apply_blur(html_rgb, blur_sigma)

    # Compute per-section scores
    section_scores: list[SectionScore] = []
    design_total_height = _compute_design_height(sections)

    if design_total_height > 0:
        img_height = figma_proc.shape[0]
        scale = img_height / design_total_height

        for section in sections:
            if section.y_position is None or section.height is None:
                continue

            y_start = int(section.y_position * scale)
            y_end = int((section.y_position + section.height) * scale)
            y_end = min(y_end, img_height)

            if y_end - y_start < _MIN_SECTION_HEIGHT_PX:
                continue

            section_figma = figma_proc[y_start:y_end, :, :]
            section_html = html_proc[y_start:y_end, :, :]
            score_val = _color_similarity(section_figma, section_html)

            section_scores.append(
                SectionScore(
                    section_id=section.node_id,
                    section_name=section.node_name,
                    section_type=section.section_type.value,
                    ssim=round(score_val, 4),
                    y_start=y_start,
                    y_end=y_end,
                )
            )

    # Overall score: MIN of section scores (worst section dominates), or
    # full-image color score if no sections.
    if section_scores:
        overall = round(min(s.ssim for s in section_scores), 4)
    else:
        overall = round(_color_similarity(figma_proc, html_proc), 4)

    # Generate diff image from unblurred luminance for visual clarity
    diff_image = _generate_diff_image(_to_grayscale(figma_rgb), _to_grayscale(html_rgb))

    logger.info(
        "design_sync.fidelity_scored",
        overall_score=overall,
        section_count=len(section_scores),
        image_shape=figma_rgb.shape,
    )

    return FidelityScore(
        overall=overall,
        sections=section_scores,
        diff_image=diff_image,
    )


def classify_severity(
    ssim: float,
    *,
    critical_threshold: float = 0.70,
    warning_threshold: float = 0.85,
) -> Literal["ok", "warning", "critical"]:
    """Classify a 0-1 fidelity score into a severity level."""
    if ssim < critical_threshold:
        return "critical"
    if ssim < warning_threshold:
        return "warning"
    return "ok"


def _compute_design_height(sections: list[EmailSection]) -> float:
    """Compute total design height from section positions."""
    if not sections:
        return 0.0
    max_bottom = 0.0
    for s in sections:
        if s.y_position is not None and s.height is not None:
            bottom = s.y_position + s.height
            max_bottom = max(max_bottom, bottom)
    return max_bottom
