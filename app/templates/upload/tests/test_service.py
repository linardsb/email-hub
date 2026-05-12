"""Service tests for template upload pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.templates.upload.exceptions import (
    TemplateAlreadyConfirmedError,
    TemplateTooLargeError,
    UploadNotFoundError,
    UploadRateLimitError,
)
from app.templates.upload.schemas import ConfirmRequest
from app.templates.upload.service import TemplateUploadService

SIMPLE_HTML = """
<html><body>
<table width="600">
  <tr><td>
    <h1 style="font-size: 24px; color: #333333;">Hello World</h1>
    <p style="font-size: 14px; color: #666666;">This is a test template with enough content to detect.</p>
    <a href="#" style="background-color: #0066CC; padding: 10px 20px;">Click Here</a>
  </td></tr>
</table>
</body></html>
"""


def _make_upload_model(
    upload_id: int = 1,
    user_id: int = 42,
    status: str = "pending_review",
) -> MagicMock:
    upload = MagicMock()
    upload.id = upload_id
    upload.user_id = user_id
    upload.status = status
    upload.sanitized_html = SIMPLE_HTML
    upload.original_html = SIMPLE_HTML
    upload.analysis_json = {
        "sections": [
            {
                "section_id": "s0",
                "component_name": "content",
                "element_count": 5,
                "layout_type": "single_column",
            }
        ],
        "slots": [
            {
                "slot_id": "s0_headline_1",
                "slot_type": "headline",
                "selector": "s0 h1",
                "required": False,
                "max_chars": None,
                "content_preview": "Hello World",
            }
        ],
        "tokens": {"colors": {}, "fonts": {}, "font_sizes": {}, "spacing": {}},
        "esp_platform": None,
        "layout_type": "promotional",
        "column_count": 1,
        "complexity_score": 10,
        "suggested_name": "uploaded_promotional_abc123",
        "suggested_description": "Test template",
        "images": [],
    }
    upload.file_size_bytes = len(SIMPLE_HTML.encode())
    upload.esp_platform = None
    upload.created_at = datetime.now(UTC)
    return upload


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture
def service(mock_db: AsyncMock) -> TemplateUploadService:
    return TemplateUploadService(mock_db)


class TestUploadAndAnalyze:
    @pytest.mark.asyncio
    async def test_successful_upload(
        self, service: TemplateUploadService, mock_db: AsyncMock
    ) -> None:
        with (
            patch.object(service._repo, "count_recent_by_user", return_value=0),
            patch.object(service._repo, "create") as mock_create,
        ):
            upload_model = _make_upload_model()
            mock_create.return_value = upload_model

            result = await service.upload_and_analyze(SIMPLE_HTML, user_id=42)
            assert result.upload_id == 1
            assert result.layout_type in ("newsletter", "promotional", "transactional", "retention")
            assert len(result.sections) >= 1
            mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_file_too_large(self, service: TemplateUploadService) -> None:
        huge_html = "x" * (3 * 1024 * 1024)  # 3MB
        with pytest.raises(TemplateTooLargeError):
            await service.upload_and_analyze(huge_html, user_id=42)

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(self, service: TemplateUploadService) -> None:
        with patch.object(service._repo, "count_recent_by_user", return_value=10):
            with pytest.raises(UploadRateLimitError):
                await service.upload_and_analyze(SIMPLE_HTML, user_id=42)


class TestConfirm:
    @pytest.mark.asyncio
    async def test_successful_confirm(
        self, service: TemplateUploadService, mock_db: AsyncMock, tmp_path: Path
    ) -> None:
        upload = _make_upload_model()
        with (
            patch.object(service._repo, "get", return_value=upload),
            patch.object(service._repo, "update_status", new_callable=AsyncMock),
            patch("app.ai.templates.registry.get_template_registry") as mock_registry,
            patch(
                "app.ai.agents.evals.template_eval_generator.UPLOADED_GOLDEN_DIR",
                tmp_path,
            ),
        ):
            mock_registry.return_value = MagicMock()

            result = await service.confirm(1, user_id=42, overrides=ConfirmRequest())
            assert result.status.value == "confirmed"
            assert result.template_name.startswith("uploaded_")
            mock_db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_confirm_already_confirmed(self, service: TemplateUploadService) -> None:
        upload = _make_upload_model(status="confirmed")
        with patch.object(service._repo, "get", return_value=upload):
            with pytest.raises(TemplateAlreadyConfirmedError):
                await service.confirm(1, user_id=42, overrides=ConfirmRequest())


class TestReject:
    @pytest.mark.asyncio
    async def test_successful_reject(
        self, service: TemplateUploadService, mock_db: AsyncMock
    ) -> None:
        upload = _make_upload_model()
        with (
            patch.object(service._repo, "get", return_value=upload),
            patch.object(service._repo, "delete", new_callable=AsyncMock),
        ):
            await service.reject(1, user_id=42)
            mock_db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_reject_wrong_user(self, service: TemplateUploadService) -> None:
        upload = _make_upload_model(user_id=99)
        with patch.object(service._repo, "get", return_value=upload):
            with pytest.raises(UploadNotFoundError):
                await service.reject(1, user_id=42)


class TestOwnership:
    @pytest.mark.asyncio
    async def test_get_preview_wrong_user(self, service: TemplateUploadService) -> None:
        upload = _make_upload_model(user_id=99)
        with patch.object(service._repo, "get", return_value=upload):
            with pytest.raises(UploadNotFoundError):
                await service.get_preview(1, user_id=42)

    @pytest.mark.asyncio
    async def test_not_found(self, service: TemplateUploadService) -> None:
        with patch.object(service._repo, "get", return_value=None):
            with pytest.raises(UploadNotFoundError):
                await service.get_preview(999, user_id=42)


class TestConfirmIntegration:
    """Tests for eval generation + knowledge injection during confirm."""

    @pytest.mark.asyncio
    async def test_confirm_triggers_eval_generation(
        self, service: TemplateUploadService, mock_db: AsyncMock, tmp_path: Path
    ) -> None:
        """Confirm calls eval generator with GoldenTemplate."""
        upload = _make_upload_model()
        with (
            patch.object(service._repo, "get", return_value=upload),
            patch.object(service._repo, "update_status", new_callable=AsyncMock),
            patch("app.ai.templates.registry.get_template_registry") as mock_reg,
            patch.object(service._eval_gen, "generate", return_value=[]) as mock_gen,
            patch.object(service._eval_gen, "save"),
            patch(
                "app.ai.agents.evals.template_eval_generator.UPLOADED_GOLDEN_DIR",
                tmp_path,
            ),
        ):
            mock_reg.return_value = MagicMock()
            service._settings.auto_eval_generate = True
            service._settings.auto_knowledge_inject = False

            await service.confirm(1, user_id=42, overrides=ConfirmRequest())
            mock_gen.assert_called_once()

    @pytest.mark.asyncio
    async def test_confirm_triggers_knowledge_injection(
        self, service: TemplateUploadService, mock_db: AsyncMock, tmp_path: Path
    ) -> None:
        """Confirm calls knowledge injector."""
        upload = _make_upload_model()
        with (
            patch.object(service._repo, "get", return_value=upload),
            patch.object(service._repo, "update_status", new_callable=AsyncMock),
            patch("app.ai.templates.registry.get_template_registry") as mock_reg,
            patch(
                "app.ai.agents.evals.template_eval_generator.UPLOADED_GOLDEN_DIR",
                tmp_path,
            ),
            patch("app.knowledge.services.ingestion.IngestionService"),
            patch("app.templates.upload.knowledge_injector.KnowledgeInjector") as mock_inj_cls,
        ):
            mock_reg.return_value = MagicMock()
            service._settings.auto_eval_generate = False
            service._settings.auto_knowledge_inject = True
            mock_inj_cls.return_value.inject = AsyncMock(return_value=42)

            await service.confirm(1, user_id=42, overrides=ConfirmRequest())
            mock_inj_cls.return_value.inject.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_confirm_eval_failure_non_blocking(
        self, service: TemplateUploadService, mock_db: AsyncMock, tmp_path: Path
    ) -> None:
        """Eval generation failure does not block confirm."""
        upload = _make_upload_model()
        with (
            patch.object(service._repo, "get", return_value=upload),
            patch.object(service._repo, "update_status", new_callable=AsyncMock),
            patch("app.ai.templates.registry.get_template_registry") as mock_reg,
            patch.object(service._eval_gen, "generate", side_effect=RuntimeError("eval boom")),
            patch(
                "app.ai.agents.evals.template_eval_generator.UPLOADED_GOLDEN_DIR",
                tmp_path,
            ),
        ):
            mock_reg.return_value = MagicMock()
            service._settings.auto_eval_generate = True
            service._settings.auto_knowledge_inject = False

            result = await service.confirm(1, user_id=42, overrides=ConfirmRequest())
            assert result.status.value == "confirmed"

    @pytest.mark.asyncio
    async def test_confirm_knowledge_failure_non_blocking(
        self, service: TemplateUploadService, mock_db: AsyncMock, tmp_path: Path
    ) -> None:
        """Knowledge injection failure does not block confirm."""
        upload = _make_upload_model()
        with (
            patch.object(service._repo, "get", return_value=upload),
            patch.object(service._repo, "update_status", new_callable=AsyncMock),
            patch("app.ai.templates.registry.get_template_registry") as mock_reg,
            patch(
                "app.ai.agents.evals.template_eval_generator.UPLOADED_GOLDEN_DIR",
                tmp_path,
            ),
            patch(
                "app.knowledge.services.ingestion.IngestionService",
                side_effect=RuntimeError("DB down"),
            ),
        ):
            mock_reg.return_value = MagicMock()
            service._settings.auto_eval_generate = False
            service._settings.auto_knowledge_inject = True

            result = await service.confirm(1, user_id=42, overrides=ConfirmRequest())
            assert result.status.value == "confirmed"

    @pytest.mark.asyncio
    async def test_confirm_with_name_override(
        self, service: TemplateUploadService, mock_db: AsyncMock, tmp_path: Path
    ) -> None:
        """Name/description overrides applied to GoldenTemplate."""
        upload = _make_upload_model()
        with (
            patch.object(service._repo, "get", return_value=upload),
            patch.object(service._repo, "update_status", new_callable=AsyncMock),
            patch("app.ai.templates.registry.get_template_registry") as mock_reg,
            patch(
                "app.ai.agents.evals.template_eval_generator.UPLOADED_GOLDEN_DIR",
                tmp_path,
            ),
        ):
            mock_reg.return_value = MagicMock()
            service._settings.auto_eval_generate = False
            service._settings.auto_knowledge_inject = False

            overrides = ConfirmRequest(name="my_custom", description="Custom description")
            result = await service.confirm(1, user_id=42, overrides=overrides)
            assert "my_custom" in result.template_name
            mock_db.commit.assert_awaited()
