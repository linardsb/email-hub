# pyright: reportArgumentType=false
"""Tests for the design import conversion pipeline (12.5)."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agents.scaffolder.prompt import build_design_context_section
from app.ai.agents.scaffolder.schemas import ScaffolderRequest, ScaffolderResponse
from app.design_sync.exceptions import ImportNotFoundError, ImportStateError
from app.design_sync.import_service import DesignImportService
from app.design_sync.protocol import DesignNodeType
from app.design_sync.repository import DesignSyncRepository
from app.design_sync.schemas import (
    AnalyzedSectionResponse,
    ConvertImportRequest,
    DesignContextSchema,
    DesignTokensResponse,
    DesignTypographyResponse,
    LayoutAnalysisResponse,
    StartImportRequest,
    TextBlockResponse,
)
from app.design_sync.services._context import DesignSyncContext
from app.design_sync.services.import_service import ImportRequestService


def _make_user(user_id: int = 1, role: str = "developer") -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.role = role
    return user


def _make_connection(conn_id: int = 1, project_id: int = 10, provider: str = "figma") -> MagicMock:
    conn = MagicMock()
    conn.id = conn_id
    conn.project_id = project_id
    conn.provider = provider
    conn.file_ref = "abc123"
    conn.encrypted_token = "encrypted_token_value"
    return conn


def _make_import(
    import_id: int = 1,
    connection_id: int = 1,
    project_id: int = 10,
    status: str = "pending",
    brief: str | None = "Test brief for email campaign with hero section",
    selected_node_ids: list[str] | None = None,
    structure_json: dict[str, object] | None = None,
    created_by_id: int = 1,
) -> MagicMock:
    imp = MagicMock()
    imp.id = import_id
    imp.connection_id = connection_id
    imp.project_id = project_id
    imp.status = status
    imp.generated_brief = brief
    imp.selected_node_ids = selected_node_ids or ["1:1", "1:2"]
    imp.structure_json = structure_json
    imp.created_by_id = created_by_id
    imp.result_template_id = None
    imp.error_message = None
    imp.assets = []
    imp.created_at = "2026-03-15T00:00:00"
    imp.updated_at = "2026-03-15T00:00:00"
    return imp


# ── Schema Validation Tests ──


class TestSchemas:
    def test_start_import_request_validation(self) -> None:
        req = StartImportRequest(
            connection_id=1,
            brief="A test brief that is long enough to pass validation",
        )
        assert req.connection_id == 1
        assert req.selected_node_ids == []
        assert req.template_name is None

    def test_start_import_request_short_brief_rejected(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="brief"):
            StartImportRequest(connection_id=1, brief="short")

    def test_convert_import_request_defaults(self) -> None:
        req = ConvertImportRequest()
        assert req.run_qa is True
        assert req.output_mode == "structured"

    def test_convert_import_request_invalid_mode(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ConvertImportRequest(output_mode="invalid")

    def test_design_context_schema_defaults(self) -> None:
        ctx = DesignContextSchema()
        assert ctx.image_urls == {}
        assert ctx.layout_summary is None
        assert ctx.sections == []
        assert ctx.design_tokens is None
        assert ctx.source_file is None

    def test_scaffolder_request_design_context(self) -> None:
        req = ScaffolderRequest(
            brief="Test brief for an email campaign",
            design_context={
                "image_urls": {"1:1": "/assets/1/img.png"},
                "layout_summary": "hero, cta",
            },
        )
        assert req.design_context is not None
        assert req.design_context["layout_summary"] == "hero, cta"


# ── Prompt Injection Tests ──


class TestDesignContextPrompt:
    def test_build_design_context_section_basic(self) -> None:
        ctx: dict[str, object] = {
            "layout_summary": "header, hero, content, footer",
            "image_urls": {"1:1": "/assets/1/hero.png"},
            "source_file": "My Design.fig",
        }
        result = build_design_context_section(ctx)
        assert "Design Reference" in result
        assert "header, hero, content, footer" in result
        assert "`1:1`" in result
        assert "/assets/1/hero.png" in result
        assert "My Design.fig" in result

    def test_build_design_context_section_with_tokens(self) -> None:
        ctx: dict[str, object] = {
            "design_tokens": {
                "colors": [{"name": "Primary", "hex": "#538FE4"}],
                "typography": [{"name": "H1", "family": "Inter", "size": 32}],
            },
        }
        result = build_design_context_section(ctx)
        assert "Primary: #538FE4" in result
        assert "Inter" in result

    def test_build_design_context_section_empty(self) -> None:
        result = build_design_context_section({})
        assert "Design Reference" in result


# ── Service Method Tests ──


class TestImportRequestService:
    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def mock_repo(self) -> AsyncMock:
        return AsyncMock(spec=DesignSyncRepository)

    @pytest.fixture
    def ctx(self, mock_db: AsyncMock, mock_repo: AsyncMock) -> DesignSyncContext:
        ctx = DesignSyncContext(mock_db)
        ctx._repo_default = mock_repo
        ctx.verify_access = AsyncMock()  # type: ignore[method-assign]
        return ctx

    @pytest.fixture
    def service(self, ctx: DesignSyncContext) -> ImportRequestService:
        return ImportRequestService(ctx)

    @pytest.mark.asyncio
    async def test_create_design_import(
        self, mock_repo: AsyncMock, service: ImportRequestService
    ) -> None:
        user = _make_user()
        conn = _make_connection()
        design_import = _make_import()

        mock_repo.get_connection.return_value = conn
        mock_repo.create_import.return_value = design_import
        mock_repo.get_import.return_value = design_import

        data = StartImportRequest(
            connection_id=1,
            brief="Test brief for email campaign with hero section",
        )
        result = await service.create_design_import(data, user)

        assert result.id == 1
        assert result.status == "pending"
        mock_repo.create_import.assert_awaited_once()
        mock_repo.update_import_status.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_design_import(
        self, mock_repo: AsyncMock, service: ImportRequestService
    ) -> None:
        user = _make_user()
        design_import = _make_import()

        mock_repo.get_import_with_assets.return_value = design_import

        result = await service.get_design_import(1, user)
        assert result.id == 1

    @pytest.mark.asyncio
    async def test_get_design_import_not_found(
        self, mock_repo: AsyncMock, service: ImportRequestService
    ) -> None:
        user = _make_user()
        mock_repo.get_import_with_assets.return_value = None

        with pytest.raises(ImportNotFoundError):
            await service.get_design_import(999, user)

    @pytest.mark.asyncio
    async def test_update_import_brief_pending(
        self, mock_repo: AsyncMock, service: ImportRequestService
    ) -> None:
        user = _make_user()
        design_import = _make_import(status="pending")

        mock_repo.get_import.return_value = design_import

        result = await service.update_import_brief(
            1, "Updated brief content for the campaign", user
        )
        assert result.id == 1
        mock_repo.update_import_status.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_import_brief_converting_rejected(
        self, mock_repo: AsyncMock, service: ImportRequestService
    ) -> None:
        user = _make_user()
        design_import = _make_import(status="converting")

        mock_repo.get_import.return_value = design_import

        with pytest.raises(ImportStateError, match="converting"):
            await service.update_import_brief(1, "Updated brief", user)

    @pytest.mark.asyncio
    async def test_start_conversion_pending(
        self, mock_repo: AsyncMock, service: ImportRequestService
    ) -> None:
        user = _make_user()
        design_import = _make_import(status="pending")

        async def _update_status(imp: object, status: str, **kwargs: object) -> None:
            imp.status = status  # type: ignore[attr-defined]

        mock_repo.get_import.return_value = design_import
        mock_repo.update_import_status.side_effect = _update_status

        with patch("app.design_sync.services.import_service.asyncio.create_task"):
            result = await service.start_conversion(1, user)

        assert result.status == "converting"

    @pytest.mark.asyncio
    async def test_start_conversion_already_converting_rejected(
        self, mock_repo: AsyncMock, service: ImportRequestService
    ) -> None:
        user = _make_user()
        design_import = _make_import(status="converting")

        mock_repo.get_import.return_value = design_import

        with pytest.raises(ImportStateError, match="converting"):
            await service.start_conversion(1, user)

    @pytest.mark.asyncio
    async def test_start_conversion_failed_allowed(
        self, mock_repo: AsyncMock, service: ImportRequestService
    ) -> None:
        """Failed imports can be re-converted."""
        user = _make_user()
        design_import = _make_import(status="failed")

        mock_repo.get_import.return_value = design_import

        with patch("app.design_sync.services.import_service.asyncio.create_task"):
            result = await service.start_conversion(1, user)

        # Should succeed (not raise ImportStateError)
        assert result.id == 1

    @pytest.mark.asyncio
    async def test_start_conversion_no_brief_rejected(
        self, mock_repo: AsyncMock, service: ImportRequestService
    ) -> None:
        user = _make_user()
        design_import = _make_import(status="pending", brief=None)

        mock_repo.get_import.return_value = design_import

        from app.core.exceptions import DomainValidationError

        with pytest.raises(DomainValidationError, match="no brief"):
            await service.start_conversion(1, user)


# ── DesignImportService (Orchestrator) Tests ──


class TestDesignImportServiceOrchestrator:
    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def mock_repo(self) -> AsyncMock:
        return AsyncMock(spec=DesignSyncRepository)

    @pytest.fixture
    def mock_design_service(self) -> AsyncMock:
        return AsyncMock()

    def test_derive_template_name_from_brief(self) -> None:
        assert DesignImportService._derive_template_name("# My Campaign\nDetails") == "My Campaign"
        assert DesignImportService._derive_template_name("Simple line") == "Simple line"
        assert DesignImportService._derive_template_name("") == "Imported from Figma"
        assert DesignImportService._derive_template_name("   \n  \n  ") == "Imported from Figma"

    def test_collect_image_node_ids(self) -> None:
        svc = DesignImportService(user=_make_user())

        layout = MagicMock(spec=["sections"])
        img1 = MagicMock()
        img1.node_id = "1:1"
        img1.export_node_id = None
        img2 = MagicMock()
        img2.node_id = "2:1"
        img2.export_node_id = None
        section = MagicMock()
        section.images = [img1, img2]
        layout.sections = [section]

        node_ids, mapping = svc._collect_image_node_ids(layout)
        assert node_ids == ["1:1", "2:1"]
        assert mapping == {}

    def test_collect_image_node_ids_fallback_to_section_frames(self) -> None:
        """When no IMAGE nodes exist, fall back to section frame node IDs."""
        svc = DesignImportService(user=_make_user())

        layout = MagicMock(spec=["sections"])
        section = MagicMock()
        section.images = []
        section.node_id = "frame:1"
        layout.sections = [section]

        node_ids, mapping = svc._collect_image_node_ids(layout)
        assert node_ids == ["frame:1"]
        assert mapping == {}

    def test_collect_image_node_ids_appends_selected(self) -> None:
        """Selected top-level nodes are appended (deduped) for full-email renders."""
        svc = DesignImportService(user=_make_user())

        layout = MagicMock(spec=["sections"])
        img = MagicMock()
        img.node_id = "1:1"
        img.export_node_id = None
        section = MagicMock()
        section.images = [img]
        layout.sections = [section]

        node_ids, mapping = svc._collect_image_node_ids(layout, selected_node_ids=["1:1", "top:1"])
        assert node_ids == ["1:1", "top:1"]  # "1:1" not duplicated
        assert mapping == {}

    def test_fill_image_urls_single(self) -> None:
        html = '<img src="" alt="Logo" data-node-id="1:2" width="200" style="display:block;" />'
        filled = DesignImportService._fill_image_urls(
            html, {"1:2": "/api/v1/design-sync/assets/5/1_2.png"}
        )
        assert 'src="/api/v1/design-sync/assets/5/1_2.png"' in filled
        assert 'src=""' not in filled

    def test_fill_image_urls_multiple(self) -> None:
        html = (
            '<img src="" alt="Logo" data-node-id="1:2" width="200" />\n'
            '<img src="" alt="Hero" data-node-id="3:4" width="600" />'
        )
        urls = {"1:2": "/assets/1_2.png", "3:4": "/assets/3_4.png"}
        filled = DesignImportService._fill_image_urls(html, urls)
        assert 'src="/assets/1_2.png"' in filled
        assert 'src="/assets/3_4.png"' in filled
        assert 'src=""' not in filled

    def test_fill_image_urls_unmatched_preserved(self) -> None:
        """Images without a matching node_id in the map keep src=""."""
        html = '<img src="" alt="Unknown" data-node-id="9:9" width="100" />'
        filled = DesignImportService._fill_image_urls(html, {"1:2": "/assets/1_2.png"})
        assert 'src=""' in filled

    def test_fill_image_urls_non_self_closing(self) -> None:
        """img tags without trailing slash should also be matched."""
        html = '<img src="" alt="Logo" data-node-id="1:2" width="200">'
        filled = DesignImportService._fill_image_urls(
            html, {"1:2": "/api/v1/design-sync/assets/5/1_2.png"}
        )
        assert 'src="/api/v1/design-sync/assets/5/1_2.png"' in filled
        assert 'src=""' not in filled

    def test_fill_image_urls_empty_map(self) -> None:
        html = '<img src="" alt="Logo" data-node-id="1:2" width="200" />'
        filled = DesignImportService._fill_image_urls(html, {})
        assert filled == html

    def test_fix_orphaned_footer_moves_content_inside(self) -> None:
        """Footer content after </table> should be moved inside the wrapper."""
        html = (
            "<html><body>"
            '<table role="presentation" style="margin:0 auto;max-width:600px;">'
            "<tr><td>Content</td></tr>"
            "</table>"
            '\n<div style="text-align:center;">'
            '<a href="#">Unsubscribe</a>'
            "</div>\n"
            "<!--[if mso]>\n</td></tr></table>\n<![endif]-->"
            "</div></body></html>"
        )
        response = ScaffolderResponse(html=html, model="test", confidence=0.9, qa_passed=True)
        fixed = DesignImportService._fix_orphaned_footer(response)
        # Footer should now be inside the table
        assert fixed.html.index("Unsubscribe") < fixed.html.index("</table>")

    def test_fix_orphaned_footer_indented_mso(self) -> None:
        """MSO conditional with indentation should still be detected."""
        html = (
            "<html><body>"
            '<table role="presentation">'
            "<tr><td>Content</td></tr>"
            "</table>"
            '\n<p style="text-align:center;">Footer</p>\n'
            "<!--[if mso]>\n  </td>\n  </tr>\n  </table>\n<![endif]-->"
            "</div></body></html>"
        )
        response = ScaffolderResponse(html=html, model="test", confidence=0.9, qa_passed=True)
        fixed = DesignImportService._fix_orphaned_footer(response)
        assert fixed.html.index("Footer") < fixed.html.index("</table>")

    def test_fix_orphaned_footer_noop_when_correct(self) -> None:
        """Properly structured HTML should not be modified."""
        html = (
            "<html><body>"
            '<table role="presentation">'
            "<tr><td>Content</td></tr>"
            '<tr><td><a href="#">Unsubscribe</a></td></tr>'
            "</table>\n"
            "<!--[if mso]>\n</td></tr></table>\n<![endif]-->"
            "</div></body></html>"
        )
        response = ScaffolderResponse(html=html, model="test", confidence=0.9, qa_passed=True)
        fixed = DesignImportService._fix_orphaned_footer(response)
        assert fixed.html == html

    def test_build_design_context(self) -> None:
        svc = DesignImportService(user=_make_user())
        conn = _make_connection(conn_id=5)

        layout = MagicMock()
        section = MagicMock()
        section.section_type = "hero"
        layout.sections = [section]
        layout.file_name = "Test.fig"

        asset_response = MagicMock()
        asset = MagicMock()
        asset.node_id = "1:1"
        asset.filename = "hero.png"
        asset_response.assets = [asset]

        tokens = MagicMock()
        color = MagicMock()
        color.name = "Primary"
        color.hex = "#538FE4"
        color.opacity = 1.0
        tokens.colors = [color]
        typo = MagicMock()
        typo.name = "H1"
        typo.family = "Inter"
        typo.weight = "700"
        typo.size = 32
        tokens.typography = [typo]

        ctx = svc._build_design_context(layout, asset_response, tokens, conn)
        assert ctx["source_file"] == "Test.fig"
        assert ctx["layout_summary"] == "hero"
        assert ctx["image_urls"] == {"1:1": "/api/v1/design-sync/assets/5/hero.png"}
        assert ctx["design_tokens"] is not None

    @pytest.mark.asyncio
    async def test_run_conversion_success(
        self,
        mock_db: AsyncMock,
        mock_repo: AsyncMock,
        mock_design_service: AsyncMock,
    ) -> None:
        """End-to-end conversion pipeline with mocked dependencies."""
        user = _make_user()
        design_import = _make_import(
            status="converting",
            brief="Test brief for email conversion pipeline",
        )
        conn = _make_connection()

        mock_repo.get_import_with_assets.return_value = design_import
        mock_repo.get_connection.return_value = conn
        mock_repo.get_import.return_value = design_import
        mock_repo.update_import_status = AsyncMock()

        # Layout analysis returns sections with images
        layout = MagicMock()
        section = MagicMock()
        section.section_type = "hero"
        img = MagicMock()
        img.node_id = "1:1"
        section.images = [img]
        layout.sections = [section]
        layout.file_name = "Design.fig"
        mock_design_service.analyze_layout.return_value = layout

        # Assets downloaded
        asset = MagicMock()
        asset.node_id = "1:1"
        asset.filename = "hero.png"
        asset_resp = MagicMock()
        asset_resp.assets = [asset]
        mock_design_service.download_assets.return_value = asset_resp

        # Tokens
        token_resp = MagicMock()
        color = MagicMock()
        color.name = "Primary"
        color.hex = "#000"
        color.opacity = 1.0
        token_resp.colors = [color]
        token_resp.typography = []
        mock_design_service.get_tokens.return_value = token_resp

        # Scaffolder response
        scaffolder_resp = ScaffolderResponse(
            html="<html>generated</html>",
            model="claude:test",
            confidence=0.95,
            qa_passed=True,
        )

        svc = DesignImportService(user=user)

        # Mock get_db_context to yield our mock session
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.design_sync.import_service.get_scoped_db_context", return_value=mock_ctx),
            patch(
                "app.design_sync.import_service.DesignSyncRepository",
                return_value=mock_repo,
            ),
            patch(
                "app.design_sync.import_service.TokenConversionService",
                return_value=mock_design_service,
            ),
            patch(
                "app.design_sync.import_service.AssetsService",
                return_value=mock_design_service,
            ),
            patch.object(svc, "_call_scaffolder", return_value=scaffolder_resp),
            patch.object(svc, "_create_template", return_value=42),
        ):
            await svc.run_conversion(design_import.id)

        # Should have marked as completed
        calls = mock_repo.update_import_status.call_args_list
        last_call = calls[-1]
        assert last_call.args[1] == "completed"
        assert last_call.kwargs.get("result_template_id") == 42

    @pytest.mark.asyncio
    async def test_run_conversion_failure_marks_failed(
        self,
        mock_db: AsyncMock,
        mock_repo: AsyncMock,
        mock_design_service: AsyncMock,
    ) -> None:
        """Pipeline failure should mark import as failed."""
        user = _make_user()
        design_import = _make_import(status="converting")

        mock_repo.get_import_with_assets.return_value = design_import
        mock_repo.get_connection.return_value = _make_connection()
        mock_repo.get_import.return_value = design_import
        mock_repo.update_import_status = AsyncMock()

        # Layout analysis throws
        mock_design_service.analyze_layout.side_effect = RuntimeError("API down")

        svc = DesignImportService(user=user)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.design_sync.import_service.get_scoped_db_context", return_value=mock_ctx),
            patch(
                "app.design_sync.import_service.DesignSyncRepository",
                return_value=mock_repo,
            ),
            patch(
                "app.design_sync.import_service.TokenConversionService",
                return_value=mock_design_service,
            ),
            patch(
                "app.design_sync.import_service.AssetsService",
                return_value=mock_design_service,
            ),
        ):
            await svc.run_conversion(design_import.id)

        # Should have marked as failed
        calls = mock_repo.update_import_status.call_args_list
        last_call = calls[-1]
        assert last_call.args[1] == "failed"
        assert last_call.kwargs.get("error_message") == "Conversion pipeline failed"

    @pytest.mark.asyncio
    async def test_run_conversion_not_found(
        self,
        mock_db: AsyncMock,
        mock_repo: AsyncMock,
        mock_design_service: AsyncMock,
    ) -> None:
        """Missing import should return early without error."""
        mock_repo.get_import_with_assets.return_value = None

        svc = DesignImportService(user=_make_user())

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.design_sync.import_service.get_scoped_db_context", return_value=mock_ctx),
            patch(
                "app.design_sync.import_service.DesignSyncRepository",
                return_value=mock_repo,
            ),
        ):
            # Should not raise
            await svc.run_conversion(999)

    @pytest.mark.asyncio
    async def test_run_conversion_selected_nodes_skip_document_path(
        self,
        mock_db: AsyncMock,
        mock_repo: AsyncMock,
        mock_design_service: AsyncMock,
    ) -> None:
        """A selected-nodes import must NOT convert the whole-file snapshot document.

        Guards phase-53f-document-path-ignores-node-selection: the snapshot
        document has no node filtering, so imports with selected_node_ids go
        through the legacy path (get_design_structure + _filter_structure).
        """
        user = _make_user()
        design_import = _make_import(status="converting")  # selected_node_ids non-empty
        snap = MagicMock()
        snap.document_json = {"schema": "email-design-document-v1"}

        mock_repo.get_import_with_assets.return_value = design_import
        mock_repo.get_connection.return_value = _make_connection()
        mock_repo.get_import.return_value = design_import
        mock_repo.update_import_status = AsyncMock()
        mock_repo.get_latest_snapshot.return_value = snap

        layout = MagicMock()
        layout.sections = []
        layout.file_name = "Design.fig"
        mock_design_service.analyze_layout.return_value = layout
        mock_design_service.get_tokens.return_value = MagicMock(colors=[], typography=[])
        # Short-circuit the legacy branch after proving it was entered.
        mock_design_service.get_design_structure.side_effect = RuntimeError("stop-legacy")

        scaffolder_resp = ScaffolderResponse(
            html="<html>generated</html>", model="test", confidence=0.9, qa_passed=True
        )
        svc = DesignImportService(user=user)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.design_sync.import_service.get_scoped_db_context", return_value=mock_ctx),
            patch(
                "app.design_sync.import_service.DesignSyncRepository",
                return_value=mock_repo,
            ),
            patch(
                "app.design_sync.import_service.TokenConversionService",
                return_value=mock_design_service,
            ),
            patch(
                "app.design_sync.import_service.AssetsService",
                return_value=mock_design_service,
            ),
            patch(
                "app.design_sync.email_design_document.EmailDesignDocument.from_json"
            ) as from_json_mock,
            patch.object(svc, "_call_scaffolder", return_value=scaffolder_resp),
            patch.object(svc, "_create_template", return_value=42),
        ):
            await svc.run_conversion(design_import.id)

        from_json_mock.assert_not_called()
        mock_design_service.get_design_structure.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_conversion_whole_file_import_uses_document_path(
        self,
        mock_db: AsyncMock,
        mock_repo: AsyncMock,
        mock_design_service: AsyncMock,
    ) -> None:
        """With no node selection, the snapshot document path is still preferred."""
        user = _make_user()
        design_import = _make_import(status="converting")
        design_import.selected_node_ids = []  # whole-file import
        snap = MagicMock()
        snap.document_json = {"schema": "email-design-document-v1"}

        mock_repo.get_import_with_assets.return_value = design_import
        mock_repo.get_connection.return_value = _make_connection()
        mock_repo.get_import.return_value = design_import
        mock_repo.update_import_status = AsyncMock()
        mock_repo.get_latest_snapshot.return_value = snap

        layout = MagicMock()
        layout.sections = []
        layout.file_name = "Design.fig"
        mock_design_service.analyze_layout.return_value = layout
        mock_design_service.get_tokens.return_value = MagicMock(colors=[], typography=[])
        mock_design_service.get_design_structure.side_effect = RuntimeError("stop-legacy")

        scaffolder_resp = ScaffolderResponse(
            html="<html>generated</html>", model="test", confidence=0.9, qa_passed=True
        )
        svc = DesignImportService(user=user)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.design_sync.import_service.get_scoped_db_context", return_value=mock_ctx),
            patch(
                "app.design_sync.import_service.DesignSyncRepository",
                return_value=mock_repo,
            ),
            patch(
                "app.design_sync.import_service.TokenConversionService",
                return_value=mock_design_service,
            ),
            patch(
                "app.design_sync.import_service.AssetsService",
                return_value=mock_design_service,
            ),
            patch(
                "app.design_sync.email_design_document.EmailDesignDocument.from_json",
                side_effect=ValueError("stub document"),
            ) as from_json_mock,
            patch.object(svc, "_call_scaffolder", return_value=scaffolder_resp),
            patch.object(svc, "_create_template", return_value=42),
        ):
            await svc.run_conversion(design_import.id)

        from_json_mock.assert_called_once()
        assert from_json_mock.call_args.args[-1] == snap.document_json

    def test_placeholder_images_replaced_broad(self) -> None:
        """images.placeholder.com URL should be replaced by asset URL."""
        html = '<img src="https://images.placeholder.com/600x400" alt="Hero" />'
        response = ScaffolderResponse(html=html, model="test", confidence=0.9, qa_passed=True)
        fixed = DesignImportService._inject_asset_urls(response, {"1:1": "/assets/hero.png"})
        assert "images.placeholder.com" not in fixed.html
        assert 'src="/assets/hero.png"' in fixed.html

    def test_bg_color_in_response_schema(self) -> None:
        """AnalyzedSectionResponse with bg_color serializes correctly."""
        section = AnalyzedSectionResponse(
            section_type="hero",
            node_id="1:1",
            node_name="Hero",
            bg_color="#1a1a2e",
        )
        assert section.bg_color == "#1a1a2e"
        data = section.model_dump()
        assert data["bg_color"] == "#1a1a2e"

    def test_contrast_fix_dark_bg(self) -> None:
        """HTML with dark bgcolor + dark text color should be fixed to white."""
        html = '<table bgcolor="#1a1a2e"><tr><td style="color:#000000;">text</td></tr></table>'
        fixed = DesignImportService._fix_text_contrast(html)
        assert "color:#ffffff" in fixed
        assert "color:#000000" not in fixed.lower()

    def test_contrast_fix_light_bg_unchanged(self) -> None:
        """HTML with light bgcolor + dark text should remain unchanged."""
        html = '<table bgcolor="#ffffff"><tr><td style="color:#000000;">text</td></tr></table>'
        fixed = DesignImportService._fix_text_contrast(html)
        assert "color:#000000" in fixed

    def test_contrast_fix_mixed_layout_scoped(self) -> None:
        """Dark-bg fix must NOT bleed into light-bg sections."""
        html = (
            '<table bgcolor="#1a1a2e"><tr><td style="color:#000000;">dark section</td></tr></table>'
            '<table bgcolor="#ffffff"><tr><td style="color:#000000;">light section</td></tr></table>'
        )
        fixed = DesignImportService._fix_text_contrast(html)
        # Dark section: black text → white
        assert 'color:#ffffff;">dark section' in fixed
        # Light section: black text stays black
        assert 'color:#000000;">light section' in fixed

    def test_contrast_fix_nested_light_card_preserved(self) -> None:
        """Readable text on a nested LIGHT card inside a dark wrapper is kept.

        Regression for the first-close-tag scan: the dark outer wrapper's
        range used to over-extend across the inner light card, recolouring
        already-readable ``#333333`` text to invisible white-on-white.
        """
        html = (
            '<table bgcolor="#1a1a2e"><tr><td bgcolor="#1a1a2e">'
            '<table><tr><td style="background:#ffffff;">'
            '<span style="color:#333333;">readable body</span>'
            "</td></tr></table>"
            "</td></tr></table>"
        )
        fixed = DesignImportService._fix_text_contrast(html)
        # Innermost background of the span is white → text must stay #333333.
        assert "color:#333333" in fixed
        # Pin the negative to the span so a future shorthand→longhand fixture
        # swap (which would surface ``color:#ffffff`` in the cell bg) can't mask
        # a real regression of the span colour.
        assert 'color:#ffffff;">readable body' not in fixed

    def test_contrast_fix_nested_dark_still_corrected(self) -> None:
        """Genuine dark-on-dark text inside a nested dark card is still fixed."""
        html = (
            '<table bgcolor="#1a1a2e"><tr><td bgcolor="#1a1a2e">'
            '<table><tr><td style="background:#0d0d1a;">'
            '<span style="color:#000000;">on dark card</span>'
            "</td></tr></table>"
            "</td></tr></table>"
        )
        fixed = DesignImportService._fix_text_contrast(html)
        # Innermost background is dark → black text must become white.
        assert "color:#ffffff" in fixed
        assert "color:#000000" not in fixed

    def test_contrast_fix_outlined_button_own_light_bg_preserved(self) -> None:
        """An inline CTA carrying its own light background keeps its dark label.

        Regression for phase-53f-app-snapshot-serializer-drops-render-fields'
        last mechanism: the LEGO 'Explore now' outlined pill (white fill, black
        label, on a dark purple band) was repainted white-on-white because the
        anchor's own background-color was invisible to the bg-range scan.
        """
        html = (
            '<table style="background-color:#4E3092;"><tr><td style="color:#FFFFFF;">'
            "Conjure up even more joy"
            '<a href="#" style="background-color:#FFFFFF;color:#000000;'
            'border:2px solid #000000;border-radius:25px;">Explore now</a>'
            "</td></tr></table>"
        )
        fixed = DesignImportService._fix_text_contrast(html)
        assert "color:#000000;border:2px solid #000000" in fixed
        assert "color:#ffffff;border" not in fixed.lower()

    def test_contrast_fix_dark_button_own_bg_still_corrected(self) -> None:
        """Dark-on-dark text inside a button's OWN dark background is fixed."""
        html = (
            '<table bgcolor="#ffffff"><tr><td>'
            '<a href="#" style="background-color:#0d0d1a;color:#000000;">Shop</a>'
            "</td></tr></table>"
        )
        fixed = DesignImportService._fix_text_contrast(html)
        assert "color:#ffffff" in fixed
        assert "color:#000000" not in fixed

    def test_inject_asset_urls_placeholder_uses_full_pool(self) -> None:
        """Strategy 3 replaces placeholder URLs even when Strategy 2 consumed pool."""
        # Strategy 2 will consume the pool on empty src="" tags
        # Strategy 3 should still replace via.placeholder using the FULL url list
        html = '<img src="" alt="A" /><img src="https://via.placeholder.com/600x400" alt="B" />'
        response = ScaffolderResponse(html=html, model="test", confidence=0.9, qa_passed=True)
        fixed = DesignImportService._inject_asset_urls(response, {"1:1": "/assets/hero.png"})
        assert "via.placeholder.com" not in fixed.html
        assert 'src="/assets/hero.png"' in fixed.html

    def test_placeholder_cycling(self) -> None:
        """Multiple placeholder URLs cycle through available assets."""
        html = (
            '<img src="https://via.placeholder.com/600x400" alt="A" />'
            '<img src="https://placehold.co/300x200" alt="B" />'
        )
        response = ScaffolderResponse(html=html, model="test", confidence=0.9, qa_passed=True)
        fixed = DesignImportService._inject_asset_urls(
            response, {"1:1": "/assets/hero.png", "2:1": "/assets/logo.png"}
        )
        assert "via.placeholder.com" not in fixed.html
        assert "placehold.co" not in fixed.html
        assert "/assets/hero.png" in fixed.html
        assert "/assets/logo.png" in fixed.html

    def test_build_design_context_includes_typography_fields(self) -> None:
        """Typography entries include line_height, letter_spacing, text_transform."""
        svc = DesignImportService(user=_make_user())
        conn = _make_connection(conn_id=5)

        layout = MagicMock()
        layout.sections = [MagicMock(section_type="hero")]
        layout.file_name = "Test.fig"

        tokens = MagicMock()
        tokens.colors = []
        typo = MagicMock()
        typo.name = "H1"
        typo.family = "Inter"
        typo.weight = "700"
        typo.size = 32
        typo.lineHeight = 40.0
        typo.letterSpacing = 0.5
        typo.textTransform = "uppercase"
        tokens.typography = [typo]
        tokens.spacing = []
        tokens.dark_colors = []
        tokens.gradients = []
        tokens.warnings = ["Test warning"]

        ctx = svc._build_design_context(layout, None, tokens, conn)
        dt = cast(dict[str, Any], ctx["design_tokens"])
        assert isinstance(dt, dict)
        typo_entry = cast(dict[str, Any], dt["typography"][0])
        assert typo_entry["line_height"] == 40.0
        assert typo_entry["letter_spacing"] == 0.5
        assert typo_entry["text_transform"] == "uppercase"
        assert dt["token_warnings"] == ["Test warning"]

    def test_layout_to_design_nodes_with_text(self) -> None:
        """TEXT children are created from section.texts with typography data."""
        svc = DesignImportService(user=_make_user())
        layout = LayoutAnalysisResponse(
            connection_id=1,
            file_name="Test.fig",
            overall_width=600,
            sections=[
                AnalyzedSectionResponse(
                    section_type="hero",
                    node_id="1:0",
                    node_name="Hero",
                    texts=[
                        TextBlockResponse(
                            node_id="1:1",
                            content="Hello World",
                            font_size=32,
                            is_heading=True,
                            font_family="Inter",
                            font_weight=700,
                            line_height=40,
                            letter_spacing=0.5,
                        )
                    ],
                    images=[],
                    buttons=[],
                ),
            ],
            total_text_blocks=1,
            total_images=0,
        )
        nodes = svc._layout_to_design_nodes(layout)
        text_node = nodes[0].children[0].children[0]  # page > section > text
        assert text_node.type == DesignNodeType.TEXT
        assert text_node.text_content == "Hello World"
        assert text_node.font_family == "Inter"
        assert text_node.font_size == 32.0
        assert text_node.line_height_px == 40.0
        assert text_node.letter_spacing_px == 0.5

    def test_tokens_to_protocol_preserves_typography_fields(self) -> None:
        """Round-trip: letterSpacing, textTransform, textDecoration survive conversion."""
        tokens = DesignTokensResponse(
            connection_id=1,
            colors=[],
            typography=[
                DesignTypographyResponse(
                    name="H1",
                    family="Inter",
                    weight="700",
                    size=32,
                    lineHeight=40,
                    letterSpacing=0.5,
                    textTransform="uppercase",
                    textDecoration="underline",
                ),
            ],
            spacing=[],
            extracted_at="2026-01-01T00:00:00Z",
        )
        result = DesignImportService._tokens_to_protocol(tokens)
        typo = result.typography[0]
        assert typo.letter_spacing == 0.5
        assert typo.text_transform == "uppercase"
        assert typo.text_decoration == "underline"
        assert typo.line_height == 40
