# pyright: reportUnknownArgumentType=false
"""Orchestration service for visual fidelity scoring.

Coordinates Figma frame export, HTML rendering, and SSIM scoring
to produce per-section visual fidelity metrics.
"""

from __future__ import annotations

import io
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image as PILImage

from app.core.config import get_settings
from app.core.logging import get_logger
from app.design_sync.exceptions import FidelityScoringError
from app.design_sync.figma.layout_analyzer import DesignLayoutDescription, EmailSection
from app.design_sync.tuning import FIDELITY_BLUR_SIGMA, FIDELITY_FIGMA_SCALE, FIDELITY_SSIM_WINDOW
from app.design_sync.visual_scorer import FidelityScore, classify_severity, score_fidelity
from app.shared.imaging import safe_image_open

if TYPE_CHECKING:
    from app.auth.models import User
    from app.design_sync.figma.service import FigmaDesignSyncService
    from app.design_sync.models import DesignConnection, DesignImport

logger = get_logger(__name__)

# Default rendering profile for fidelity comparison
_DEFAULT_PROFILE = "gmail_web"


class VisualFidelityService:
    """Orchestrates visual fidelity scoring for design imports."""

    async def score_import(
        self,
        design_import: DesignImport,
        connection: DesignConnection,
        html: str,
        layout: DesignLayoutDescription,
        user: User,  # noqa: ARG002  — reserved for future auth context
        *,
        figma_service: FigmaDesignSyncService | None = None,
    ) -> FidelityScore:
        """Score visual fidelity of converted HTML against Figma frames.

        Args:
            design_import: The import job being scored.
            connection: Design connection with Figma credentials.
            html: Converted email HTML to render.
            layout: Layout description with section positions.
            user: Current user (reserved for auth context).
            figma_service: Optional pre-configured Figma service.

        Returns:
            FidelityScore with overall SSIM, per-section scores, and diff image.
        """
        if not layout.sections:
            raise FidelityScoringError("No sections in layout — cannot score fidelity")

        # 1. Export Figma frame images for section node IDs
        figma_image = await self._capture_figma_composite(
            connection, layout.sections, figma_service=figma_service
        )

        # 2. Render HTML screenshot
        html_image = await self._render_html_screenshot(html)

        # 3. Compute fidelity scores
        result = score_fidelity(
            figma_image,
            html_image,
            layout.sections,
            blur_sigma=FIDELITY_BLUR_SIGMA,
            win_size=FIDELITY_SSIM_WINDOW,
        )

        # 4. Store diff image if present
        if result.diff_image:
            self._store_diff_image(design_import.id, result.diff_image)

        logger.info(
            "design_sync.fidelity_completed",
            import_id=design_import.id,
            overall_ssim=result.overall,
            section_count=len(result.sections),
        )

        return result

    async def _capture_figma_composite(
        self,
        connection: DesignConnection,
        sections: list[EmailSection],
        *,
        figma_service: FigmaDesignSyncService | None = None,
    ) -> bytes:
        """Export and stitch Figma section frames into a single composite image."""
        if figma_service is None:
            from app.design_sync.figma.service import FigmaDesignSyncService

            figma_service = FigmaDesignSyncService()

        # Decrypt access token
        from app.design_sync.crypto import decrypt_token

        access_token = decrypt_token(connection.encrypted_token)

        node_ids = [s.node_id for s in sections]
        exported = await figma_service.export_images(
            connection.file_ref,
            access_token,
            node_ids,
            format="png",
            scale=FIDELITY_FIGMA_SCALE,
        )

        if not exported:
            raise FidelityScoringError("Figma export returned no images")

        # Download all image bytes
        image_bytes_map: dict[str, bytes] = {}
        for exported_img in exported:
            raw = await figma_service.download_image_bytes(exported_img)
            image_bytes_map[exported_img.node_id] = raw

        # Stitch vertically in section order (by y_position)
        sorted_sections = sorted(
            [s for s in sections if s.node_id in image_bytes_map],
            key=lambda s: s.y_position if s.y_position is not None else 0.0,
        )

        if not sorted_sections:
            raise FidelityScoringError("No section images available for compositing")

        images: list[PILImage.Image] = []
        for section in sorted_sections:
            raw = image_bytes_map[section.node_id]
            images.append(safe_image_open(io.BytesIO(raw)).convert("RGB"))

        # Vertical concatenation
        total_width = max(img.width for img in images)
        total_height = sum(img.height for img in images)
        composite = PILImage.new("RGB", (total_width, total_height), (255, 255, 255))

        y_offset = 0
        for img in images:
            composite.paste(img, (0, y_offset))
            y_offset += img.height

        buf = io.BytesIO()
        composite.save(buf, format="PNG")
        return buf.getvalue()

    async def _render_html_screenshot(self, html: str) -> bytes:
        """Render email HTML to a PNG screenshot using Playwright."""
        from app.rendering.local.profiles import CLIENT_PROFILES
        from app.rendering.local.runner import capture_screenshot

        profile = CLIENT_PROFILES.get(_DEFAULT_PROFILE)
        if profile is None:
            raise FidelityScoringError(f"Rendering profile '{_DEFAULT_PROFILE}' not found")

        with tempfile.TemporaryDirectory(prefix="fidelity_") as tmpdir:
            return await capture_screenshot(html, profile, Path(tmpdir))

    def _store_diff_image(self, import_id: int, diff_bytes: bytes) -> Path:
        """Store diff image to disk for later retrieval."""
        settings = get_settings()
        diff_dir = Path(settings.design_sync.asset_storage_path) / "fidelity" / str(import_id)
        diff_dir.mkdir(parents=True, exist_ok=True)
        diff_path = diff_dir / "diff.png"
        diff_path.write_bytes(diff_bytes)
        logger.info(
            "design_sync.fidelity_diff_stored",
            import_id=import_id,
            path=str(diff_path),
            size_bytes=len(diff_bytes),
        )
        return diff_path

    @staticmethod
    def serialize_score(score: FidelityScore) -> dict[str, Any]:
        """Convert a FidelityScore to a JSON-serializable dict for persistence."""
        return {
            "overall_ssim": score.overall,
            "scored_at": datetime.now(tz=UTC).isoformat(),
            "sections": [
                {
                    "section_id": s.section_id,
                    "section_name": s.section_name,
                    "section_type": s.section_type,
                    "ssim": s.ssim,
                    "severity": classify_severity(s.ssim),
                }
                for s in score.sections
            ],
            "diff_image_available": score.diff_image is not None,
        }
