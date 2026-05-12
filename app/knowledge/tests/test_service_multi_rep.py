"""Integration tests for multi-representation indexing in knowledge service."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.knowledge.summarizer import ChunkSummary

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def _mock_settings_multi_rep_enabled():
    """Settings with multi_rep_enabled=True."""
    with patch("app.knowledge.services.ingestion.get_settings") as mock:
        settings = mock.return_value
        settings.knowledge.html_chunking_enabled = True
        settings.knowledge.html_chunk_size = 1024
        settings.knowledge.html_chunk_overlap = 100
        settings.knowledge.multi_rep_enabled = True
        settings.knowledge.document_storage_path = "/tmp/test-docs"
        settings.knowledge.auto_tag_enabled = False
        yield settings


@pytest.fixture
def _mock_settings_multi_rep_disabled():
    """Settings with multi_rep_enabled=False."""
    with patch("app.knowledge.services.ingestion.get_settings") as mock:
        settings = mock.return_value
        settings.knowledge.html_chunking_enabled = True
        settings.knowledge.html_chunk_size = 1024
        settings.knowledge.html_chunk_overlap = 100
        settings.knowledge.multi_rep_enabled = False
        settings.knowledge.document_storage_path = "/tmp/test-docs"
        settings.knowledge.auto_tag_enabled = False
        yield settings


def _make_html_chunk_result(
    *, content: str, chunk_index: int, section_type: str | None, summary: str | None = None
) -> MagicMock:
    """Create a mock HTMLChunkResult."""
    mock = MagicMock()
    mock.content = content
    mock.chunk_index = chunk_index
    mock.section_type = section_type
    mock.summary = summary
    return mock


class TestIngestHtmlMultiRepEnabled:
    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_mock_settings_multi_rep_enabled")
    async def test_summaries_generated_and_embedded(self) -> None:
        """When multi_rep_enabled, summaries are generated and used for embedding."""
        html_results = [
            _make_html_chunk_result(
                content=".header { color: red; }",
                chunk_index=0,
                section_type="style",
            ),
            _make_html_chunk_result(
                content="<div>Hero section</div>",
                chunk_index=1,
                section_type="section",
            ),
        ]

        mock_summarizer = AsyncMock()
        mock_summarizer.summarize.return_value = [
            ChunkSummary(index=0, summary="CSS rules: .header (color)"),
            ChunkSummary(index=1, summary="A hero section with centered content."),
        ]

        mock_embed = AsyncMock(return_value=[[0.1, 0.2], [0.3, 0.4]])

        with (
            patch(
                "app.knowledge.services.ingestion.chunking_html.is_html_content", return_value=True
            ),
            patch(
                "app.knowledge.services.ingestion.chunking_html.chunk_html",
                return_value=html_results,
            ),
            patch(
                "app.knowledge.services.ingestion.processing.extract_text",
                new_callable=AsyncMock,
                return_value=("<html>test</html>", False),
            ),
            patch("app.knowledge._providers._get_embedding") as mock_get_embed,
            patch("app.knowledge.summarizer.ChunkSummarizer", return_value=mock_summarizer),
            patch("pathlib.Path.mkdir"),
            patch("shutil.copy2"),
        ):
            mock_get_embed.return_value.embed = mock_embed

            from app.knowledge.services.ingestion import IngestionService

            db = AsyncMock()
            service = IngestionService(db)
            service.repository = AsyncMock()
            service.repository.get_tags_for_document.return_value = []
            service.repository.create_document.return_value = MagicMock(id=1)
            service.repository.get_document.return_value = MagicMock(
                id=1,
                filename="test.html",
                domain="test",
                language="en",
                title="Test",
                source_type="text",
                status="completed",
                chunk_count=2,
                file_size_bytes=100,
                description=None,
                metadata_json=None,
                error_message=None,
                created_at=_NOW,
                updated_at=_NOW,
                ocr_applied=False,
                file_path="/tmp/test.html",
            )

            from app.knowledge.schemas import DocumentUpload

            await service.ingest_document(
                file_path="/tmp/test.html",
                upload=DocumentUpload(
                    domain="test", metadata_json=None, title=None, description=None
                ),
                filename="test.html",
                source_type="text",
                file_size=100,
            )

            # Verify embedding was called with summaries, not raw content
            embed_call_args = mock_embed.call_args[0][0]
            assert embed_call_args[0] == "CSS rules: .header (color)"
            assert embed_call_args[1] == "A hero section with centered content."

            # Verify chunks stored with summaries
            bulk_call = service.repository.bulk_create_chunks.call_args[0][0]
            assert bulk_call[0].summary == "CSS rules: .header (color)"
            assert bulk_call[1].summary == "A hero section with centered content."
            # But content is still original
            assert bulk_call[0].content == ".header { color: red; }"
            assert bulk_call[1].content == "<div>Hero section</div>"


class TestIngestHtmlMultiRepDisabled:
    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_mock_settings_multi_rep_disabled")
    async def test_existing_behavior_unchanged(self) -> None:
        """When multi_rep_enabled=False, raw content is embedded directly."""
        html_results = [
            _make_html_chunk_result(
                content="<div>Hero section</div>",
                chunk_index=0,
                section_type="section",
                summary="Basic 16.3 summary",
            ),
        ]

        mock_embed = AsyncMock(return_value=[[0.1, 0.2]])

        with (
            patch(
                "app.knowledge.services.ingestion.chunking_html.is_html_content", return_value=True
            ),
            patch(
                "app.knowledge.services.ingestion.chunking_html.chunk_html",
                return_value=html_results,
            ),
            patch(
                "app.knowledge.services.ingestion.processing.extract_text",
                new_callable=AsyncMock,
                return_value=("<html>test</html>", False),
            ),
            patch("app.knowledge._providers._get_embedding") as mock_get_embed,
            patch("pathlib.Path.mkdir"),
            patch("shutil.copy2"),
        ):
            mock_get_embed.return_value.embed = mock_embed

            from app.knowledge.services.ingestion import IngestionService

            db = AsyncMock()
            service = IngestionService(db)
            service.repository = AsyncMock()
            service.repository.get_tags_for_document.return_value = []
            service.repository.create_document.return_value = MagicMock(id=1)
            service.repository.get_document.return_value = MagicMock(
                id=1,
                filename="test.html",
                domain="test",
                language="en",
                title="Test",
                source_type="text",
                status="completed",
                chunk_count=1,
                file_size_bytes=100,
                description=None,
                metadata_json=None,
                error_message=None,
                created_at=_NOW,
                updated_at=_NOW,
                ocr_applied=False,
                file_path="/tmp/test.html",
            )

            from app.knowledge.schemas import DocumentUpload

            await service.ingest_document(
                file_path="/tmp/test.html",
                upload=DocumentUpload(
                    domain="test", metadata_json=None, title=None, description=None
                ),
                filename="test.html",
                source_type="text",
                file_size=100,
            )

            # When multi_rep disabled, raw content is embedded (not 16.3 summary)
            embed_call_args = mock_embed.call_args[0][0]
            assert embed_call_args[0] == "<div>Hero section</div>"


class TestIngestTextMultiRepEnabled:
    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_mock_settings_multi_rep_enabled")
    async def test_plain_text_unaffected(self) -> None:
        """Plain text documents are not affected by multi_rep even when enabled."""
        mock_embed = AsyncMock(return_value=[[0.1, 0.2]])

        with (
            patch(
                "app.knowledge.services.ingestion.chunking_html.is_html_content", return_value=False
            ),
            patch("app.knowledge.services.ingestion.chunking.chunk_text") as mock_chunk,
            patch(
                "app.knowledge.services.ingestion.processing.extract_text",
                new_callable=AsyncMock,
                return_value=("Just plain text content.", False),
            ),
            patch("app.knowledge._providers._get_embedding") as mock_get_embed,
            patch("pathlib.Path.mkdir"),
            patch("shutil.copy2"),
        ):
            mock_get_embed.return_value.embed = mock_embed
            mock_chunk_result = MagicMock()
            mock_chunk_result.content = "Just plain text content."
            mock_chunk_result.chunk_index = 0
            mock_chunk.return_value = [mock_chunk_result]

            from app.knowledge.services.ingestion import IngestionService

            db = AsyncMock()
            service = IngestionService(db)
            service.repository = AsyncMock()
            service.repository.get_tags_for_document.return_value = []
            service.repository.create_document.return_value = MagicMock(id=1)
            service.repository.get_document.return_value = MagicMock(
                id=1,
                filename="test.txt",
                domain="test",
                language="en",
                title="Test",
                source_type="text",
                status="completed",
                chunk_count=1,
                file_size_bytes=100,
                description=None,
                metadata_json=None,
                error_message=None,
                created_at=_NOW,
                updated_at=_NOW,
                ocr_applied=False,
                file_path="/tmp/test.txt",
            )

            from app.knowledge.schemas import DocumentUpload

            await service.ingest_document(
                file_path="/tmp/test.txt",
                upload=DocumentUpload(
                    domain="test", metadata_json=None, title=None, description=None
                ),
                filename="test.txt",
                source_type="text",
                file_size=100,
            )

            # Raw text content embedded directly
            embed_call_args = mock_embed.call_args[0][0]
            assert embed_call_args[0] == "Just plain text content."


class TestSearchReturnsFullContent:
    @pytest.mark.asyncio
    async def test_search_returns_original_content(self) -> None:
        """Search returns original chunk content, not the summary."""
        from app.knowledge.models import DocumentChunk

        # The DocumentChunk model stores both content and summary
        chunk = DocumentChunk(
            document_id=1,
            content="<div class='hero'>Original HTML</div>",
            chunk_index=0,
            embedding=[0.1, 0.2],
            section_type="section",
            summary="A hero section with original HTML content.",
        )
        # Search always returns .content (the original), not .summary
        assert chunk.content == "<div class='hero'>Original HTML</div>"
        assert chunk.summary == "A hero section with original HTML content."
