"""Asset storage pipeline for design sync — download, resize, store, serve."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.design_sync.exceptions import AssetDownloadError, AssetNotFoundError

logger = get_logger(__name__)

# Strict filename pattern: node IDs use colons (e.g. "1:2"), we normalise to underscores
_SAFE_FILENAME_RE = re.compile(r"^[a-zA-Z0-9_-]+\.(png|jpg|svg|pdf)$")
_DOWNLOAD_SEMAPHORE = asyncio.Semaphore(10)
_DOWNLOAD_TIMEOUT = 60.0
# 53.3d — audit-trail threshold for oversized stored assets (~200 KB).
_OVERSIZE_WARN_BYTES = 200_000


def _sanitize_node_id(node_id: str) -> str:
    """Convert Figma node ID (e.g. '1:2') to filesystem-safe string ('1_2')."""
    return node_id.replace(":", "_")


def _get_storage_dir(connection_id: int) -> Path:
    """Get the storage directory for a connection's assets."""
    settings = get_settings()
    base = Path(settings.design_sync.asset_storage_path)
    return base / str(connection_id)


def _get_asset_path(connection_id: int, node_id: str, fmt: str) -> Path:
    """Build the full path for a stored asset."""
    safe_id = _sanitize_node_id(node_id)
    filename = f"{safe_id}.{fmt}"
    if not _SAFE_FILENAME_RE.match(filename):
        raise AssetNotFoundError("Invalid asset filename")
    return _get_storage_dir(connection_id) / filename


def _try_resize_image(data: bytes, max_width: int, fmt: str) -> bytes:
    """Resize image if wider than max_width. Requires Pillow. Returns original if unavailable."""
    if fmt in ("svg", "pdf"):
        return data  # Can't resize vector/PDF formats
    try:
        from io import BytesIO

        from PIL import Image

        from app.shared.imaging import safe_image_open

        img = safe_image_open(BytesIO(data))
        if img.width <= max_width:
            return data
        ratio = max_width / img.width
        new_height = int(img.height * ratio)
        resized = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
        buf = BytesIO()
        save_fmt = "JPEG" if fmt == "jpg" else fmt.upper()
        resized.save(buf, format=save_fmt, optimize=True, quality=85)
        logger.info(
            "design_sync.asset_resized",
            original_width=img.width,
            new_width=max_width,
        )
        return buf.getvalue()
    except ImportError:
        return data  # Pillow not installed — store as-is
    except Exception as exc:
        logger.warning("design_sync.resize_failed", error=str(exc))
        return data  # Fallback: store original


async def _download_one(client: httpx.AsyncClient, url: str) -> bytes:
    """Download a single image URL with semaphore limiting."""
    async with _DOWNLOAD_SEMAPHORE:
        resp = await client.get(url, follow_redirects=True)
        if resp.status_code != 200:
            raise AssetDownloadError(f"Failed to download asset: HTTP {resp.status_code}")
        return resp.content


class DesignAssetService:
    """Downloads images from provider CDN URLs, stores locally, serves via path lookup."""

    async def download_and_store(
        self,
        connection_id: int,
        images: list[dict[str, Any]],
        *,
        fmt: str = "png",
    ) -> list[dict[str, str]]:
        """Download images from URLs and store locally.

        Args:
            connection_id: The connection these assets belong to.
            images: List of dicts with 'node_id' and 'url' keys.
            fmt: Image format (png, jpg, svg, pdf).

        Returns:
            List of dicts with 'node_id' and 'filename' for each stored asset.
        """
        settings = get_settings()
        max_width = settings.design_sync.asset_max_width
        storage_dir = _get_storage_dir(connection_id)
        storage_dir.mkdir(parents=True, exist_ok=True)

        stored: list[dict[str, str]] = []

        async with httpx.AsyncClient(timeout=_DOWNLOAD_TIMEOUT) as client:
            tasks: list[tuple[str, asyncio.Task[bytes]]] = []
            for img in images:
                url = img.get("url", "")
                node_id = img.get("node_id", "")
                if not url or not node_id:
                    continue
                tasks.append((node_id, asyncio.ensure_future(_download_one(client, url))))

            results = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)

        for (node_id, _), result in zip(tasks, results, strict=True):
            if isinstance(result, BaseException):
                logger.warning(
                    "design_sync.asset_download_failed",
                    node_id=node_id,
                    error=str(result),
                )
                continue

            data = _try_resize_image(result, max_width, fmt)
            # 53.3d — frame-export fallbacks can raster whole sections; Gmail's
            # 102 KB clip is per-HTML, not per-image, but keep the audit trail.
            if len(data) > _OVERSIZE_WARN_BYTES:
                logger.warning(
                    "design_sync.asset_oversized",
                    node_id=node_id,
                    size_bytes=len(data),
                )
            asset_path = _get_asset_path(connection_id, node_id, fmt)
            asset_path.write_bytes(data)

            stored.append(
                {
                    "node_id": node_id,
                    "filename": asset_path.name,
                }
            )

        logger.info(
            "design_sync.assets_stored",
            connection_id=connection_id,
            requested=len(images),
            stored=len(stored),
        )
        return stored

    def get_stored_path(self, connection_id: int, filename: str) -> Path:
        """Get the full path to a stored asset with security validation.

        Raises:
            AssetNotFoundError: If filename is invalid or file doesn't exist.
        """
        if not _SAFE_FILENAME_RE.match(filename):
            raise AssetNotFoundError("Invalid asset filename")

        storage_dir = _get_storage_dir(connection_id)
        full_path = (storage_dir / filename).resolve()

        # Path traversal guard: ensure resolved path is inside storage dir
        if not str(full_path).startswith(str(storage_dir.resolve())):
            raise AssetNotFoundError("Invalid asset path")

        if not full_path.is_file():
            raise AssetNotFoundError("Asset not found")

        return full_path

    def delete_connection_assets(self, connection_id: int) -> int:
        """Delete all stored assets for a connection. Returns count of deleted files."""
        storage_dir = _get_storage_dir(connection_id)
        if not storage_dir.exists():
            return 0
        count = 0
        for f in storage_dir.iterdir():
            if f.is_file():
                f.unlink()
                count += 1
        # Remove empty directory
        if storage_dir.exists() and not any(storage_dir.iterdir()):
            storage_dir.rmdir()
        logger.info(
            "design_sync.assets_deleted",
            connection_id=connection_id,
            count=count,
        )
        return count

    def list_stored_assets(self, connection_id: int) -> list[str]:
        """List filenames of stored assets for a connection."""
        storage_dir = _get_storage_dir(connection_id)
        if not storage_dir.exists():
            return []
        return sorted(f.name for f in storage_dir.iterdir() if f.is_file())
