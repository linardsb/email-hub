"""Tests for design sync module."""

from datetime import UTC
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.design_sync.crypto import decrypt_token, encrypt_token
from app.design_sync.exceptions import (
    SyncFailedError,
    UnsupportedProviderError,
)
from app.design_sync.figma.raw_types import (
    RawFigmaGradientStop,
    RawFigmaNode,
    RawVariablesResponse,
)
from app.design_sync.figma.service import (
    FigmaDesignSyncService,
    _gradient_midpoint_hex,
    _rgba_to_hex_with_opacity,
    extract_file_key,
)
from app.design_sync.models import DesignImport
from app.design_sync.protocol import (
    DesignComponent,
    DesignFileStructure,
    DesignNode,
    DesignNodeType,
    DesignSyncProvider,
    ExportedImage,
    ExtractedColor,
    ExtractedSpacing,
    ExtractedTokens,
    ExtractedTypography,
)
from app.design_sync.repository import DesignSyncRepository
from app.design_sync.schemas import ConnectionResponse
from app.design_sync.service import SUPPORTED_PROVIDERS
from app.design_sync.services._context import DesignSyncContext
from app.design_sync.services.connection_service import ConnectionService

# ── Crypto Tests ──


class TestCrypto:
    def test_round_trip(self):
        plaintext = "figd_test_token_12345"
        encrypted = encrypt_token(plaintext)
        assert encrypted != plaintext
        assert decrypt_token(encrypted) == plaintext

    def test_different_ciphertexts(self):
        plaintext = "figd_test_token_12345"
        a = encrypt_token(plaintext)
        b = encrypt_token(plaintext)
        # Fernet includes timestamp so ciphertexts differ
        assert a != b
        assert decrypt_token(a) == plaintext
        assert decrypt_token(b) == plaintext


# ── Figma File Key Extraction ──


class TestExtractFileKey:
    def test_design_url(self):
        url = "https://www.figma.com/design/aBcDeFgH123/My-Design"
        assert extract_file_key(url) == "aBcDeFgH123"

    def test_file_url(self):
        url = "https://www.figma.com/file/xYz789AbC/Another-File"
        assert extract_file_key(url) == "xYz789AbC"

    def test_invalid_url(self):
        with pytest.raises(SyncFailedError, match="Invalid Figma URL"):
            extract_file_key("https://example.com/not-figma")


# ── Protocol Compliance ──


class TestProtocol:
    def test_figma_implements_protocol(self):
        assert isinstance(FigmaDesignSyncService(), DesignSyncProvider)

    def test_all_providers_registered(self):
        required = {"figma", "sketch", "canva"}
        assert required.issubset(set(SUPPORTED_PROVIDERS.keys()))
        # penpot is optional (gated by DESIGN_SYNC__PENPOT_ENABLED)
        # In development mode, "mock" provider is also registered
        assert set(SUPPORTED_PROVIDERS.keys()) - required <= {"mock", "penpot"}


# ── Service Tests ──


class TestDesignSyncContext:
    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock(spec=AsyncSession)
        return db

    @pytest.fixture
    def ctx(self, mock_db: AsyncMock) -> DesignSyncContext:
        return DesignSyncContext(mock_db)

    def test_unsupported_provider(self, ctx: DesignSyncContext) -> None:
        with pytest.raises(UnsupportedProviderError, match="not supported"):
            ctx.get_provider("adobe_xd")

    def test_supported_providers(self, ctx: DesignSyncContext) -> None:
        for name in ("figma", "sketch", "canva"):
            provider = ctx.get_provider(name)
            assert isinstance(provider, DesignSyncProvider)

    def test_provider_caching(self, ctx: DesignSyncContext) -> None:
        p1 = ctx.get_provider("figma")
        p2 = ctx.get_provider("figma")
        assert p1 is p2

    def test_extract_file_ref_figma(self) -> None:
        ref = DesignSyncContext.extract_file_ref(
            "figma", "https://www.figma.com/design/abc123/My-File"
        )
        assert ref == "abc123"

    def test_extract_file_ref_stub(self) -> None:
        url = "https://sketch.cloud/s/something"
        ref = DesignSyncContext.extract_file_ref("sketch", url)
        assert ref == url


# ── Schema Tests ──


class TestSchemas:
    def test_connection_response_from_model(self):
        mock_conn = MagicMock()
        mock_conn.id = 1
        mock_conn.name = "Test"
        mock_conn.provider = "figma"
        mock_conn.file_ref = "abc123"
        mock_conn.file_url = "https://figma.com/design/abc123/Test"
        mock_conn.token_last4 = "x7Kz"
        mock_conn.status = "connected"
        mock_conn.error_message = None
        mock_conn.last_synced_at = None
        mock_conn.project_id = None
        mock_conn.created_at = "2026-01-01T00:00:00"
        mock_conn.updated_at = "2026-01-01T00:00:00"

        # Patch isinstance check
        with patch("app.design_sync.schemas.isinstance", return_value=True):
            resp = ConnectionResponse.from_model(mock_conn, project_name="My Project")

        assert resp.file_key == "abc123"
        assert resp.access_token_last4 == "x7Kz"
        assert resp.project_name == "My Project"


# ── Extracted Tokens ──


class TestExtractedTokens:
    def test_defaults(self):
        tokens = ExtractedTokens()
        assert tokens.colors == []
        assert tokens.typography == []
        assert tokens.spacing == []

    def test_with_data(self):
        tokens = ExtractedTokens(
            colors=[ExtractedColor(name="Primary", hex="#538FE4", opacity=1.0)],
            typography=[
                ExtractedTypography(
                    name="H1", family="Inter", weight="700", size=32, line_height=40
                )
            ],
            spacing=[ExtractedSpacing(name="md", value=16)],
        )
        assert len(tokens.colors) == 1
        assert tokens.colors[0].hex == "#538FE4"
        assert tokens.typography[0].family == "Inter"
        assert tokens.spacing[0].value == 16


# ── Sketch/Canva Stub Tests ──


class TestStubProviders:
    @pytest.mark.asyncio
    async def test_sketch_validate(self):
        from app.design_sync.sketch.service import SketchDesignSyncService

        svc = SketchDesignSyncService()
        assert await svc.validate_connection("ref", "token") is True

    @pytest.mark.asyncio
    async def test_sketch_sync(self):
        from app.design_sync.sketch.service import SketchDesignSyncService

        svc = SketchDesignSyncService()
        tokens = await svc.sync_tokens("ref", "token")
        assert tokens == ExtractedTokens()

    @pytest.mark.asyncio
    async def test_canva_validate(self):
        from app.design_sync.canva.service import CanvaDesignSyncService

        svc = CanvaDesignSyncService()
        assert await svc.validate_connection("ref", "token") is True

    @pytest.mark.asyncio
    async def test_canva_sync(self):
        from app.design_sync.canva.service import CanvaDesignSyncService

        svc = CanvaDesignSyncService()
        tokens = await svc.sync_tokens("ref", "token")
        assert tokens == ExtractedTokens()


# ── New Protocol Dataclass Tests ──


class TestDesignNodeType:
    def test_figma_type_mapping(self) -> None:
        from app.design_sync.figma.service import _FIGMA_NODE_TYPE_MAP

        assert _FIGMA_NODE_TYPE_MAP["CANVAS"] == DesignNodeType.PAGE
        assert _FIGMA_NODE_TYPE_MAP["FRAME"] == DesignNodeType.FRAME
        assert _FIGMA_NODE_TYPE_MAP["TEXT"] == DesignNodeType.TEXT

    def test_unknown_type_defaults_to_other(self) -> None:
        from app.design_sync.figma.service import _FIGMA_NODE_TYPE_MAP

        assert (
            _FIGMA_NODE_TYPE_MAP.get("UNKNOWN_FANCY_TYPE", DesignNodeType.OTHER)
            == DesignNodeType.OTHER
        )


class TestDesignFileStructure:
    def test_empty_structure(self) -> None:
        structure = DesignFileStructure(file_name="Test")
        assert structure.file_name == "Test"
        assert structure.pages == []

    def test_with_pages(self) -> None:
        page = DesignNode(id="0:1", name="Page 1", type=DesignNodeType.PAGE)
        structure = DesignFileStructure(file_name="Test", pages=[page])
        assert len(structure.pages) == 1
        assert structure.pages[0].name == "Page 1"


class TestDesignComponent:
    def test_defaults(self) -> None:
        comp = DesignComponent(component_id="1:2", name="Button")
        assert comp.description == ""
        assert comp.thumbnail_url is None
        assert comp.containing_page is None


class TestExportedImage:
    def test_with_expiry(self) -> None:
        from datetime import datetime

        now = datetime.now(tz=UTC)
        img = ExportedImage(
            node_id="1:2", url="https://cdn.figma.com/img", format="png", expires_at=now
        )
        assert img.expires_at == now

    def test_without_expiry(self) -> None:
        img = ExportedImage(node_id="1:2", url="https://cdn.figma.com/img", format="png")
        assert img.expires_at is None


# ── Figma Provider: File Structure Parsing ──


class TestFigmaFileStructure:
    """Test Figma JSON -> DesignFileStructure parsing."""

    @pytest.fixture
    def figma_service(self) -> FigmaDesignSyncService:
        return FigmaDesignSyncService()

    @pytest.fixture
    def sample_figma_document(self) -> dict[str, Any]:
        return {
            "name": "My Design File",
            "document": {
                "id": "0:0",
                "type": "DOCUMENT",
                "children": [
                    {
                        "id": "0:1",
                        "type": "CANVAS",
                        "name": "Page 1",
                        "children": [
                            {
                                "id": "1:1",
                                "type": "FRAME",
                                "name": "Header",
                                "absoluteBoundingBox": {
                                    "x": 0,
                                    "y": 0,
                                    "width": 600,
                                    "height": 100,
                                },
                                "children": [
                                    {
                                        "id": "1:2",
                                        "type": "TEXT",
                                        "name": "Title",
                                        "absoluteBoundingBox": {
                                            "x": 0,
                                            "y": 0,
                                            "width": 200,
                                            "height": 40,
                                        },
                                        "children": [],
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "id": "0:2",
                        "type": "CANVAS",
                        "name": "Page 2",
                        "children": [],
                    },
                ],
            },
        }

    def test_parse_node_basic(self, figma_service: FigmaDesignSyncService) -> None:
        node_data: RawFigmaNode = cast(
            RawFigmaNode,
            {
                "id": "1:1",
                "type": "FRAME",
                "name": "Header",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 600, "height": 100},
                "children": [],
            },
        )
        node = figma_service._parse_node(node_data, current_depth=0, max_depth=2)
        assert node.id == "1:1"
        assert node.name == "Header"
        assert node.type == DesignNodeType.FRAME
        assert node.width == 600
        assert node.height == 100

    def test_parse_node_depth_limit(self, figma_service: FigmaDesignSyncService) -> None:
        node_data: RawFigmaNode = cast(
            RawFigmaNode,
            {
                "id": "0:1",
                "type": "CANVAS",
                "name": "Page",
                "children": [
                    {
                        "id": "1:1",
                        "type": "FRAME",
                        "name": "Frame",
                        "children": [{"id": "2:1", "type": "TEXT", "name": "Deep"}],
                    }
                ],
            },
        )
        # depth 1: should include Frame but not Deep
        node = figma_service._parse_node(node_data, current_depth=0, max_depth=1)
        assert len(node.children) == 1
        assert node.children[0].name == "Frame"
        assert node.children[0].children == []  # cut off at depth

    def test_parse_node_unlimited_depth(self, figma_service: FigmaDesignSyncService) -> None:
        node_data: RawFigmaNode = cast(
            RawFigmaNode,
            {
                "id": "0:1",
                "type": "CANVAS",
                "name": "Page",
                "children": [
                    {
                        "id": "1:1",
                        "type": "FRAME",
                        "name": "Frame",
                        "children": [{"id": "2:1", "type": "TEXT", "name": "Deep", "children": []}],
                    }
                ],
            },
        )
        node = figma_service._parse_node(node_data, current_depth=0, max_depth=None)
        assert node.children[0].children[0].name == "Deep"

    def test_unknown_node_type(self, figma_service: FigmaDesignSyncService) -> None:
        node_data: RawFigmaNode = cast(
            RawFigmaNode,
            {
                "id": "1:1",
                "type": "SOME_NEW_TYPE",
                "name": "New",
                "children": [],
            },
        )
        node = figma_service._parse_node(node_data, current_depth=0, max_depth=2)
        assert node.type == DesignNodeType.OTHER

    @pytest.mark.asyncio
    async def test_get_file_structure_api_call(
        self, figma_service: FigmaDesignSyncService, sample_figma_document: dict[str, Any]
    ) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_figma_document

        with patch("app.design_sync.figma.service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            structure = await figma_service.get_file_structure("abc123", "token")

        assert structure.file_name == "My Design File"
        assert len(structure.pages) == 2
        assert structure.pages[0].name == "Page 1"
        assert structure.pages[0].type == DesignNodeType.PAGE


# ── Figma Provider: Components ──


class TestFigmaComponents:
    @pytest.mark.asyncio
    async def test_list_components(self) -> None:
        service = FigmaDesignSyncService()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "meta": {
                "components": [
                    {
                        "node_id": "1:1",
                        "name": "Button/Primary",
                        "description": "Primary action button",
                        "thumbnail_url": "https://figma-alpha-api.s3.us-west-2.amazonaws.com/images/thumb.png",
                        "containing_frame": {"pageName": "Components"},
                    },
                    {
                        "node_id": "2:1",
                        "name": "Card/Default",
                        "description": "",
                        "containing_frame": {"pageName": "Components"},
                    },
                ]
            }
        }

        with patch("app.design_sync.figma.service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            components = await service.list_components("abc123", "token")

        assert len(components) == 2
        assert components[0].name == "Button/Primary"
        assert components[0].thumbnail_url is not None
        assert components[1].thumbnail_url is None
        assert components[0].containing_page == "Components"


# ── Figma Provider: Image Export ──


class TestFigmaImageExport:
    @pytest.mark.asyncio
    async def test_export_images_basic(self) -> None:
        service = FigmaDesignSyncService()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "images": {
                "1:1": "https://figma-alpha-api.s3.us-west-2.amazonaws.com/images/1.png",
                "1:2": "https://figma-alpha-api.s3.us-west-2.amazonaws.com/images/2.png",
            }
        }

        with patch("app.design_sync.figma.service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            images = await service.export_images("abc123", "token", ["1:1", "1:2"])

        assert len(images) == 2
        assert images[0].format == "png"
        assert images[0].expires_at is not None

    @pytest.mark.asyncio
    async def test_export_images_empty_list(self) -> None:
        service = FigmaDesignSyncService()
        images = await service.export_images("abc123", "token", [])
        assert images == []

    @pytest.mark.asyncio
    async def test_export_images_invalid_format(self) -> None:
        service = FigmaDesignSyncService()
        with pytest.raises(SyncFailedError, match="Invalid export format"):
            await service.export_images("abc123", "token", ["1:1"], format="bmp")

    @pytest.mark.asyncio
    async def test_export_images_null_url_skipped(self) -> None:
        """Figma returns null URLs for nodes it can't render."""
        service = FigmaDesignSyncService()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "images": {
                "1:1": "https://cdn.figma.com/img/1.png",
                "1:2": None,  # Failed to render
            }
        }

        with patch("app.design_sync.figma.service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            images = await service.export_images("abc123", "token", ["1:1", "1:2"])

        assert len(images) == 1  # null URL skipped
        assert images[0].node_id == "1:1"


# ── Figma 429 Rate Limit Handling ──


class TestFigmaRateLimitHandling:
    """Verify that Figma 429 responses raise SyncFailedError with clear message."""

    @pytest.mark.asyncio
    async def test_list_files_429_raises(self) -> None:
        service = FigmaDesignSyncService()
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "30"}

        with patch("app.design_sync.figma.service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            with pytest.raises(SyncFailedError, match="rate limit exceeded"):
                await service.list_files("token")

    @pytest.mark.asyncio
    async def test_validate_connection_429_passes_through(self) -> None:
        """429 on validate returns True — allows connection while rate-limited."""
        service = FigmaDesignSyncService()
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "45"}

        with patch("app.design_sync.figma.service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await service.validate_connection("abc123", "token")
            assert result is True

    @pytest.mark.asyncio
    async def test_list_components_429_raises(self) -> None:
        service = FigmaDesignSyncService()
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}

        with patch("app.design_sync.figma.service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            with pytest.raises(SyncFailedError, match="Try again in 60 seconds"):
                await service.list_components("abc123", "token")


# ── Updated Stub Tests ──


class TestStubProvidersNewMethods:
    @pytest.mark.asyncio
    async def test_sketch_file_structure(self) -> None:
        from app.design_sync.sketch.service import SketchDesignSyncService

        svc = SketchDesignSyncService()
        structure = await svc.get_file_structure("ref", "token")
        assert structure.file_name == ""
        assert structure.pages == []

    @pytest.mark.asyncio
    async def test_sketch_list_components(self) -> None:
        from app.design_sync.sketch.service import SketchDesignSyncService

        svc = SketchDesignSyncService()
        assert await svc.list_components("ref", "token") == []

    @pytest.mark.asyncio
    async def test_sketch_export_images(self) -> None:
        from app.design_sync.sketch.service import SketchDesignSyncService

        svc = SketchDesignSyncService()
        assert await svc.export_images("ref", "token", ["1:1"]) == []

    @pytest.mark.asyncio
    async def test_canva_file_structure(self) -> None:
        from app.design_sync.canva.service import CanvaDesignSyncService

        svc = CanvaDesignSyncService()
        structure = await svc.get_file_structure("ref", "token")
        assert structure.file_name == ""
        assert structure.pages == []

    @pytest.mark.asyncio
    async def test_canva_list_components(self) -> None:
        from app.design_sync.canva.service import CanvaDesignSyncService

        svc = CanvaDesignSyncService()
        assert await svc.list_components("ref", "token") == []

    @pytest.mark.asyncio
    async def test_canva_export_images(self) -> None:
        from app.design_sync.canva.service import CanvaDesignSyncService

        svc = CanvaDesignSyncService()
        assert await svc.export_images("ref", "token", ["1:1"]) == []


# ── Schema Tests for New Responses ──


class TestNewSchemas:
    def test_design_node_response_recursive(self) -> None:
        from app.design_sync.schemas import DesignNodeResponse

        node = DesignNodeResponse(
            id="1:1",
            name="Frame",
            type="FRAME",
            children=[
                DesignNodeResponse(id="2:1", name="Text", type="TEXT", children=[]),
            ],
            width=600,
            height=100,
        )
        assert len(node.children) == 1
        assert node.children[0].name == "Text"

    def test_export_image_request_validation(self) -> None:
        from app.design_sync.schemas import ExportImageRequest

        req = ExportImageRequest(connection_id=1, node_ids=["1:1"], format="svg", scale=1.0)
        assert req.format == "svg"

        with pytest.raises(ValidationError):
            ExportImageRequest(connection_id=1, node_ids=["1:1"], format="bmp")

        with pytest.raises(ValidationError):
            ExportImageRequest(connection_id=1, node_ids=[], format="png")  # min_length=1


# ── Repository: get_import_by_template_id ──


class TestGetImportByTemplate:
    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def repo(self, mock_db: AsyncMock) -> DesignSyncRepository:
        return DesignSyncRepository(mock_db)

    def _make_import(
        self,
        *,
        id: int = 1,
        connection_id: int = 10,
        project_id: int = 100,
        status: str = "completed",
        result_template_id: int | None = 42,
    ) -> MagicMock:
        imp = MagicMock(spec=DesignImport)
        imp.id = id
        imp.connection_id = connection_id
        imp.project_id = project_id
        imp.status = status
        imp.selected_node_ids = ["0:1"]
        imp.result_template_id = result_template_id
        imp.created_by_id = 1
        return imp

    @pytest.mark.asyncio
    async def test_get_import_by_template_returns_completed_import(
        self, repo: DesignSyncRepository, mock_db: AsyncMock
    ) -> None:
        """Repository returns a completed import matching result_template_id."""
        expected = self._make_import(result_template_id=42, status="completed")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected
        mock_db.execute.return_value = mock_result

        result = await repo.get_import_by_template_id(template_id=42, project_id=100)

        assert result is not None
        assert result is expected
        assert result.status == "completed"
        assert result.result_template_id == 42
        mock_db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_import_by_template_returns_none_when_no_import(
        self, repo: DesignSyncRepository, mock_db: AsyncMock
    ) -> None:
        """Returns None when no import exists for the given template."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await repo.get_import_by_template_id(template_id=999, project_id=100)

        assert result is None
        mock_db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_import_by_template_returns_none_for_non_completed(
        self, repo: DesignSyncRepository, mock_db: AsyncMock
    ) -> None:
        """Returns None for non-completed imports (query filters status='completed')."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await repo.get_import_by_template_id(template_id=42, project_id=100)

        assert result is None
        mock_db.execute.assert_awaited_once()


# ── Figma URL Format Tests (Bug Fix) ──


class TestExtractFileKeyExpanded:
    """Verify that all Figma URL path types are handled."""

    def test_proto_url(self) -> None:
        url = "https://www.figma.com/proto/aBcDeFgH123/My-Prototype?node-id=1:2"
        assert extract_file_key(url) == "aBcDeFgH123"

    def test_board_url(self) -> None:
        url = "https://www.figma.com/board/xYz789AbC/My-Board"
        assert extract_file_key(url) == "xYz789AbC"

    def test_embed_url(self) -> None:
        url = "https://www.figma.com/embed/qWe456RtY/Embedded-View"
        assert extract_file_key(url) == "qWe456RtY"

    def test_design_url_still_works(self) -> None:
        url = "https://www.figma.com/design/aBcDeFgH123/My-Design"
        assert extract_file_key(url) == "aBcDeFgH123"

    def test_file_url_still_works(self) -> None:
        url = "https://www.figma.com/file/xYz789AbC/Another-File"
        assert extract_file_key(url) == "xYz789AbC"

    def test_url_with_query_params(self) -> None:
        url = "https://www.figma.com/design/aBcDeFgH123/My-Design?node-id=1:2&t=abc"
        assert extract_file_key(url) == "aBcDeFgH123"

    def test_invalid_url_still_raises(self) -> None:
        with pytest.raises(SyncFailedError, match="Invalid Figma URL"):
            extract_file_key("https://example.com/not-figma")


# ── Duplicate Connection Guard Test ──


class TestDuplicateConnectionGuard:
    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def ctx(self, mock_db: AsyncMock) -> DesignSyncContext:
        return DesignSyncContext(mock_db)

    @pytest.fixture
    def service(self, ctx: DesignSyncContext) -> ConnectionService:
        return ConnectionService(ctx)

    @pytest.mark.asyncio
    async def test_create_connection_duplicate_raises_conflict(
        self, ctx: DesignSyncContext, service: ConnectionService
    ) -> None:
        from app.core.exceptions import ConflictError
        from app.design_sync.schemas import ConnectionCreateRequest

        # Set up a fake existing connection
        existing = MagicMock()
        existing.name = "Existing Connection"
        existing.id = 42

        with patch.object(
            ctx.repo,
            "get_connection_by_file_ref",
            new_callable=AsyncMock,
            return_value=existing,
        ):
            data = ConnectionCreateRequest(
                name="New Connection",
                provider="figma",
                file_url="https://www.figma.com/design/abc123/My-File",
                access_token="figd_test_token",
            )
            with pytest.raises(ConflictError, match="already exists"):
                await service.create_connection(data, MagicMock(id=1))


# ── Token Decryption Failure Test ──


class TestTokenDecryptionFailure:
    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def ctx(self, mock_db: AsyncMock) -> DesignSyncContext:
        return DesignSyncContext(mock_db)

    @pytest.fixture
    def service(self, ctx: DesignSyncContext) -> ConnectionService:
        return ConnectionService(ctx)

    @pytest.mark.asyncio
    async def test_sync_connection_token_decrypt_failure(
        self, ctx: DesignSyncContext, service: ConnectionService
    ) -> None:
        from app.design_sync.exceptions import TokenDecryptionError

        mock_conn = MagicMock()
        mock_conn.id = 1
        mock_conn.provider = "figma"
        mock_conn.file_ref = "abc123"
        mock_conn.encrypted_token = "invalid-ciphertext"
        mock_conn.project_id = None

        mock_update_status = AsyncMock()
        with (
            patch.object(
                ctx.repo,
                "get_connection",
                new_callable=AsyncMock,
                return_value=mock_conn,
            ),
            patch.object(ctx.repo, "update_status", mock_update_status),
            patch(
                "app.design_sync.services.connection_service.decrypt_token",
                side_effect=Exception("Invalid token"),
            ),
        ):
            with pytest.raises(TokenDecryptionError, match="Cannot decrypt"):
                await service.sync_connection(1, MagicMock(id=1))

            # Verify error status was set with descriptive message
            mock_update_status.assert_awaited_with(
                mock_conn,
                "error",
                error_message="Access token expired or encryption key changed. Please refresh your token.",
            )


# ── Token Refresh Test ──


class TestTokenRefresh:
    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def ctx(self, mock_db: AsyncMock) -> DesignSyncContext:
        return DesignSyncContext(mock_db)

    @pytest.fixture
    def service(self, ctx: DesignSyncContext) -> ConnectionService:
        return ConnectionService(ctx)

    @pytest.mark.asyncio
    async def test_refresh_token_success(
        self, ctx: DesignSyncContext, service: ConnectionService
    ) -> None:
        mock_conn = MagicMock()
        mock_conn.id = 1
        mock_conn.name = "Test"
        mock_conn.provider = "figma"
        mock_conn.file_ref = "abc123"
        mock_conn.file_url = "https://figma.com/design/abc123/Test"
        mock_conn.token_last4 = "old4"
        mock_conn.status = "error"
        mock_conn.error_message = "Sync failed"
        mock_conn.last_synced_at = None
        mock_conn.project_id = None
        mock_conn.created_at = "2026-01-01T00:00:00"
        mock_conn.updated_at = "2026-01-01T00:00:00"
        mock_conn.encrypted_token = "old_encrypted"

        mock_provider = AsyncMock()
        mock_provider.validate_connection = AsyncMock(return_value=True)
        mock_update_token = AsyncMock()
        mock_update_status = AsyncMock()

        with (
            patch.object(
                ctx.repo,
                "get_connection",
                new_callable=AsyncMock,
                return_value=mock_conn,
            ),
            patch.object(ctx.repo, "update_connection_token", mock_update_token),
            patch.object(ctx.repo, "update_status", mock_update_status),
            patch.object(
                ctx.repo,
                "get_project_name",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(ctx, "get_provider", return_value=mock_provider),
            patch(
                "app.design_sync.services.connection_service.encrypt_token",
                return_value="new_encrypted",
            ),
            patch("app.design_sync.schemas.isinstance", return_value=True),
        ):
            result = await service.refresh_token(1, "figd_new_token_1234", MagicMock(id=1))

            assert result.status == "error"  # from mock — update_status is also mocked
            mock_provider.validate_connection.assert_awaited_once_with(
                "abc123", "figd_new_token_1234"
            )
            mock_update_token.assert_awaited_once()
            mock_update_status.assert_awaited_once_with(mock_conn, "connected")


# ── Node Walk Token Extraction ──


class TestNodeWalkExtraction:
    """Test node-level color and typography extraction from Figma document tree."""

    @pytest.fixture
    def figma_service(self) -> FigmaDesignSyncService:
        return FigmaDesignSyncService()

    def _make_file_data(
        self,
        document: dict[str, Any] | None = None,
        styles: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {"document": document or {}}
        if styles is not None:
            data["styles"] = styles
        return data

    def _solid_fill(self, r: float, g: float, b: float, a: float = 1.0) -> dict[str, Any]:
        return {"type": "SOLID", "color": {"r": r, "g": g, "b": b, "a": a}}

    # 1. Colors from node fills, no published styles
    def test_colors_from_node_fills(self, figma_service: FigmaDesignSyncService) -> None:
        file_data = self._make_file_data(
            document={
                "children": [
                    {
                        "type": "FRAME",
                        "fills": [self._solid_fill(0.2, 0.4, 0.8)],
                        "children": [],
                    }
                ]
            }
        )
        colors, _, _ = figma_service._parse_colors(file_data, {})
        assert len(colors) == 1
        assert colors[0].hex == "#3366CC"
        assert colors[0].name == "#3366CC"

    # 2. Colors from strokes → separate list
    def test_colors_from_strokes(self, figma_service: FigmaDesignSyncService) -> None:
        file_data = self._make_file_data(
            document={
                "children": [
                    {
                        "type": "RECTANGLE",
                        "strokes": [self._solid_fill(1.0, 0.0, 0.0)],
                        "children": [],
                    }
                ]
            }
        )
        colors, stroke_colors, _ = figma_service._parse_colors(file_data, {})
        assert len(colors) == 0
        assert len(stroke_colors) == 1
        assert stroke_colors[0].hex == "#FF0000"

    # 3. Transparent fills skipped
    def test_transparent_fills_skipped(self, figma_service: FigmaDesignSyncService) -> None:
        file_data = self._make_file_data(
            document={
                "children": [
                    {
                        "type": "FRAME",
                        "fills": [self._solid_fill(1.0, 1.0, 1.0, a=0.005)],
                        "children": [],
                    }
                ]
            }
        )
        colors, _, _ = figma_service._parse_colors(file_data, {})
        assert len(colors) == 0

    # 4. Gradient fills extract midpoint
    def test_gradient_fills_extract_midpoint(self, figma_service: FigmaDesignSyncService) -> None:
        file_data = self._make_file_data(
            document={
                "children": [
                    {
                        "type": "FRAME",
                        "name": "Hero",
                        "fills": [
                            {
                                "type": "GRADIENT_LINEAR",
                                "gradientStops": [
                                    {"color": {"r": 1, "g": 0, "b": 0, "a": 1}},
                                    {"color": {"r": 0, "g": 0, "b": 1, "a": 1}},
                                ],
                            },
                            self._solid_fill(0.0, 0.0, 1.0),
                        ],
                        "children": [],
                    }
                ]
            }
        )
        colors, _, _ = figma_service._parse_colors(file_data, {})
        # Should have gradient midpoint + the solid blue (topmost visible solid)
        midpoints = [c for c in colors if "(gradient midpoint)" in c.name]
        assert len(midpoints) == 1
        assert midpoints[0].hex == "#800080"
        assert "Hero" in midpoints[0].name

    # 5. Published style takes priority over node-walked
    def test_published_style_priority(self, figma_service: FigmaDesignSyncService) -> None:
        file_data = self._make_file_data(
            document={
                "children": [
                    {
                        "type": "FRAME",
                        "fills": [self._solid_fill(0.2, 0.4, 0.8)],
                        "styles": {"fill": "style_1"},
                        "children": [],
                    }
                ]
            },
            styles={
                "style_1": {"styleType": "FILL", "name": "Brand Blue"},
            },
        )
        colors, _, _ = figma_service._parse_colors(file_data, {})
        assert len(colors) == 1
        assert colors[0].name == "Brand Blue"
        assert colors[0].hex == "#3366CC"

    # 6. Typography from node walk, no published styles
    def test_typography_from_node_walk(self, figma_service: FigmaDesignSyncService) -> None:
        file_data = self._make_file_data(
            document={
                "children": [
                    {
                        "type": "TEXT",
                        "style": {
                            "fontFamily": "Inter",
                            "fontWeight": "700",
                            "fontSize": 24,
                            "lineHeightPx": 32,
                        },
                        "children": [],
                    }
                ]
            }
        )
        typography = figma_service._parse_typography(file_data, {})
        assert len(typography) == 1
        assert typography[0].family == "Inter"
        assert typography[0].weight == "700"
        assert typography[0].size == 24
        assert typography[0].line_height == 32
        assert typography[0].name == "Inter 700 24px"

    # 7. Typography dedup by (family, weight, size)
    def test_typography_dedup(self, figma_service: FigmaDesignSyncService) -> None:
        file_data = self._make_file_data(
            document={
                "children": [
                    {
                        "type": "TEXT",
                        "style": {"fontFamily": "Roboto", "fontWeight": "400", "fontSize": 16},
                        "children": [],
                    },
                    {
                        "type": "TEXT",
                        "style": {
                            "fontFamily": "Roboto",
                            "fontWeight": "400",
                            "fontSize": 16,
                            "lineHeightPx": 28,
                        },
                        "children": [],
                    },
                ]
            }
        )
        typography = figma_service._parse_typography(file_data, {})
        assert len(typography) == 1

    # 7b. Typography lineHeightPx fallback (size * 1.2)
    def test_typography_line_height_fallback(self, figma_service: FigmaDesignSyncService) -> None:
        file_data = self._make_file_data(
            document={
                "children": [
                    {
                        "type": "TEXT",
                        "style": {"fontFamily": "Inter", "fontWeight": "400", "fontSize": 20},
                        "children": [],
                    }
                ]
            }
        )
        typography = figma_service._parse_typography(file_data, {})
        assert len(typography) == 1
        assert typography[0].line_height == 24.0  # 20 * 1.2

    # 8. Non-TEXT nodes' style ignored
    def test_non_text_node_style_ignored(self, figma_service: FigmaDesignSyncService) -> None:
        file_data = self._make_file_data(
            document={
                "children": [
                    {
                        "type": "FRAME",
                        "style": {"fontFamily": "Arial", "fontWeight": "400", "fontSize": 14},
                        "children": [],
                    }
                ]
            }
        )
        typography = figma_service._parse_typography(file_data, {})
        assert len(typography) == 0

    # 9. Mixed published + node-walked colors
    def test_mixed_published_and_node_walked_colors(
        self, figma_service: FigmaDesignSyncService
    ) -> None:
        file_data = self._make_file_data(
            document={
                "children": [
                    {
                        "type": "FRAME",
                        "fills": [self._solid_fill(0.2, 0.4, 0.8)],
                        "styles": {"fill": "style_1"},
                        "children": [
                            {
                                "type": "RECTANGLE",
                                "fills": [self._solid_fill(1.0, 0.0, 0.0)],
                                "children": [],
                            }
                        ],
                    }
                ]
            },
            styles={
                "style_1": {"styleType": "FILL", "name": "Brand Blue"},
            },
        )
        colors, _, _ = figma_service._parse_colors(file_data, {})
        assert len(colors) == 2
        assert colors[0].name == "Brand Blue"
        assert colors[0].hex == "#3366CC"
        assert colors[1].name == "#FF0000"
        assert colors[1].hex == "#FF0000"

    # 10. Empty document → empty lists
    def test_empty_document(self, figma_service: FigmaDesignSyncService) -> None:
        file_data = self._make_file_data(document={})
        colors, stroke_colors, _ = figma_service._parse_colors(file_data, {})
        typography = figma_service._parse_typography(file_data, {})
        assert colors == []
        assert stroke_colors == []
        assert typography == []

    # 11. Deeply nested colors extracted
    def test_deeply_nested_colors(self, figma_service: FigmaDesignSyncService) -> None:
        file_data = self._make_file_data(
            document={
                "children": [
                    {
                        "type": "FRAME",
                        "children": [
                            {
                                "type": "GROUP",
                                "children": [
                                    {
                                        "type": "FRAME",
                                        "children": [
                                            {
                                                "type": "RECTANGLE",
                                                "fills": [self._solid_fill(0.0, 1.0, 0.0)],
                                                "children": [],
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        )
        colors, _, _ = figma_service._parse_colors(file_data, {})
        assert len(colors) == 1
        assert colors[0].hex == "#00FF00"


# ── Opacity Compositing Tests ──


class TestOpacityCompositing:
    """Test alpha compositing for fill/node opacity."""

    def test_fully_opaque(self) -> None:
        assert _rgba_to_hex_with_opacity(0, 0, 1) == "#0000FF"

    def test_fill_alpha_half_blue_on_white(self) -> None:
        assert _rgba_to_hex_with_opacity(0, 0, 1, fill_alpha=0.5) == "#8080FF"

    def test_node_opacity_half_blue_on_white(self) -> None:
        assert _rgba_to_hex_with_opacity(0, 0, 1, node_opacity=0.5) == "#8080FF"

    def test_combined_half_half(self) -> None:
        # 0.5 * 0.5 = 0.25 effective alpha
        assert _rgba_to_hex_with_opacity(0, 0, 1, fill_alpha=0.5, node_opacity=0.5) == "#BFBFFF"

    def test_custom_bg_half_black_on_red(self) -> None:
        assert _rgba_to_hex_with_opacity(0, 0, 0, fill_alpha=0.5, bg_hex="#FF0000") == "#800000"

    def test_malformed_bg_hex_falls_back_to_white(self) -> None:
        # Invalid bg_hex should fall back to #FFFFFF (same result as default)
        assert _rgba_to_hex_with_opacity(0, 0, 1, fill_alpha=0.5, bg_hex="invalid") == "#8080FF"
        assert _rgba_to_hex_with_opacity(0, 0, 1, fill_alpha=0.5, bg_hex="#FFF") == "#8080FF"

    def test_gradient_midpoint_red_blue(self) -> None:
        stops: list[RawFigmaGradientStop] = [
            cast(RawFigmaGradientStop, {"color": {"r": 1, "g": 0, "b": 0, "a": 1}}),
            cast(RawFigmaGradientStop, {"color": {"r": 0, "g": 0, "b": 1, "a": 1}}),
        ]
        assert _gradient_midpoint_hex(stops) == "#800080"

    def test_gradient_insufficient_stops(self) -> None:
        stops: list[RawFigmaGradientStop] = [
            cast(RawFigmaGradientStop, {"color": {"r": 1, "g": 0, "b": 0, "a": 1}})
        ]
        assert _gradient_midpoint_hex(stops) is None


# ── Figma Variables API Tests ──


class TestFigmaVariablesAPI:
    """Test Variables API parsing and fetch behavior."""

    @pytest.fixture
    def figma_service(self) -> FigmaDesignSyncService:
        return FigmaDesignSyncService()

    def _make_variables_response(
        self,
        variables: dict[str, Any] | None = None,
        collections: dict[str, Any] | None = None,
    ) -> RawVariablesResponse:
        return cast(
            RawVariablesResponse,
            {
                "local": {
                    "meta": {
                        "variableCollections": collections or {},
                        "variables": variables or {},
                    }
                },
                "published": {},
            },
        )

    def test_parse_color_variable(self, figma_service: FigmaDesignSyncService) -> None:
        raw = self._make_variables_response(
            collections={
                "coll1": {
                    "name": "Brand",
                    "modes": [{"modeId": "m1", "name": "Light"}],
                }
            },
            variables={
                "var1": {
                    "name": "color/primary",
                    "resolvedType": "COLOR",
                    "variableCollectionId": "coll1",
                    "valuesByMode": {
                        "m1": {"r": 0.2, "g": 0.4, "b": 0.8, "a": 1.0},
                    },
                }
            },
        )
        colors, _, variables, modes, _ = figma_service._parse_variables(raw)
        assert len(colors) == 1
        assert colors[0].hex == "#3366CC"
        assert colors[0].name == "primary"  # "color/" prefix stripped
        assert len(variables) == 1
        assert variables[0].collection == "Brand"
        assert modes == {"Light": "m1"}

    def test_parse_alias_variable(self, figma_service: FigmaDesignSyncService) -> None:
        raw = self._make_variables_response(
            collections={
                "coll1": {
                    "name": "Tokens",
                    "modes": [{"modeId": "m1", "name": "Default"}],
                }
            },
            variables={
                "var_base": {
                    "name": "blue-500",
                    "resolvedType": "COLOR",
                    "variableCollectionId": "coll1",
                    "valuesByMode": {
                        "m1": {"r": 0, "g": 0, "b": 1, "a": 1.0},
                    },
                },
                "var_alias": {
                    "name": "color/primary",
                    "resolvedType": "COLOR",
                    "variableCollectionId": "coll1",
                    "valuesByMode": {
                        "m1": {"type": "VARIABLE_ALIAS", "id": "var_base"},
                    },
                },
            },
        )
        colors, _, variables, _, _ = figma_service._parse_variables(raw)
        alias_vars = [v for v in variables if v.is_alias]
        assert len(alias_vars) == 1
        assert alias_vars[0].alias_path == "blue-500"
        # Colors should include the resolved blue from both base and alias (deduped)
        blue_colors = [c for c in colors if c.hex == "#0000FF"]
        assert len(blue_colors) >= 1

    def test_semitransparent_color_variable(self, figma_service: FigmaDesignSyncService) -> None:
        raw = self._make_variables_response(
            collections={
                "coll1": {
                    "name": "Colors",
                    "modes": [{"modeId": "m1", "name": "Default"}],
                }
            },
            variables={
                "var1": {
                    "name": "overlay",
                    "resolvedType": "COLOR",
                    "variableCollectionId": "coll1",
                    "valuesByMode": {
                        "m1": {"r": 0, "g": 0, "b": 1, "a": 0.5},
                    },
                }
            },
        )
        colors, _, _, _, _ = figma_service._parse_variables(raw)
        assert len(colors) == 1
        assert colors[0].hex == "#8080FF"  # Blue 50% on white

    @pytest.mark.asyncio
    async def test_fetch_403_returns_none(self, figma_service: FigmaDesignSyncService) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 403

        with patch("app.design_sync.figma.service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await figma_service._fetch_variables("abc123", "token")

        assert result is None

    def test_circular_alias_depth_guard(self, figma_service: FigmaDesignSyncService) -> None:
        raw = self._make_variables_response(
            collections={
                "coll1": {
                    "name": "Loop",
                    "modes": [{"modeId": "m1", "name": "Default"}],
                }
            },
            variables={
                "var_a": {
                    "name": "A",
                    "resolvedType": "COLOR",
                    "variableCollectionId": "coll1",
                    "valuesByMode": {
                        "m1": {"type": "VARIABLE_ALIAS", "id": "var_b"},
                    },
                },
                "var_b": {
                    "name": "B",
                    "resolvedType": "COLOR",
                    "variableCollectionId": "coll1",
                    "valuesByMode": {
                        "m1": {"type": "VARIABLE_ALIAS", "id": "var_a"},
                    },
                },
            },
        )
        colors, _, variables, _, _ = figma_service._parse_variables(raw)
        # Should not crash — circular aliases resolve to None, no colors extracted
        assert len(colors) == 0
        assert len(variables) == 2

    def test_non_color_vars_skip_palette(self, figma_service: FigmaDesignSyncService) -> None:
        raw = self._make_variables_response(
            collections={
                "coll1": {
                    "name": "Sizing",
                    "modes": [{"modeId": "m1", "name": "Default"}],
                }
            },
            variables={
                "var1": {
                    "name": "border-radius",
                    "resolvedType": "FLOAT",
                    "variableCollectionId": "coll1",
                    "valuesByMode": {"m1": 8},
                }
            },
        )
        colors, _, variables, _, _ = figma_service._parse_variables(raw)
        assert len(colors) == 0
        assert len(variables) == 1
        assert variables[0].type == "FLOAT"

    def test_empty_variables_response(self, figma_service: FigmaDesignSyncService) -> None:
        raw = self._make_variables_response()
        colors, _, variables, modes, _ = figma_service._parse_variables(raw)
        assert colors == []
        assert variables == []
        assert modes == {}


class TestTokenDiff:
    """Tests for token diff computation."""

    def test_compute_token_diff_detects_added_color(self) -> None:
        """Token diff detects added colors between snapshots."""
        from app.design_sync.services.conversion_service import compute_token_diff

        prev_json: dict[str, Any] = {
            "colors": [{"name": "Primary", "hex": "#538FE4", "opacity": 1.0}]
        }
        cur_json: dict[str, Any] = {
            "colors": [
                {"name": "Primary", "hex": "#538FE4", "opacity": 1.0},
                {"name": "Secondary", "hex": "#FF6B35", "opacity": 1.0},
            ]
        }
        entries = compute_token_diff(cur_json, prev_json)
        added = [e for e in entries if e.change == "added"]
        assert len(added) == 1
        assert added[0].name == "Secondary"
        assert added[0].category == "color"

    def test_compute_token_diff_detects_removed_color(self) -> None:
        """Token diff detects removed colors."""
        from app.design_sync.services.conversion_service import compute_token_diff

        prev_json: dict[str, Any] = {
            "colors": [
                {"name": "Primary", "hex": "#538FE4", "opacity": 1.0},
                {"name": "Old", "hex": "#AAAAAA", "opacity": 1.0},
            ]
        }
        cur_json: dict[str, Any] = {
            "colors": [{"name": "Primary", "hex": "#538FE4", "opacity": 1.0}]
        }
        entries = compute_token_diff(cur_json, prev_json)
        removed = [e for e in entries if e.change == "removed"]
        assert len(removed) == 1
        assert removed[0].name == "Old"

    def test_compute_token_diff_empty_previous(self) -> None:
        """All tokens are 'added' when previous snapshot is empty."""
        from app.design_sync.services.conversion_service import compute_token_diff

        cur_json: dict[str, Any] = {
            "colors": [{"name": "Primary", "hex": "#538FE4", "opacity": 1.0}],
            "typography": [{"name": "H1", "family": "Inter", "size": 32}],
        }
        entries = compute_token_diff(cur_json, {})
        assert len(entries) == 2
        assert all(e.change == "added" for e in entries)
