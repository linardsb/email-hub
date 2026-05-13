"""Tests for graph seeding in seed.py."""

from __future__ import annotations

import sys
from collections.abc import Generator
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.knowledge.data.seed_manifest import SeedEntry
from app.knowledge.seed import _seed_graph


def _make_entry(filename: str, domain: str) -> SeedEntry:
    return SeedEntry(
        filename=filename,
        domain=domain,
        title="Test",
        description="Test doc",
        tags=["test"],
    )


def _mock_seed_dir() -> MagicMock:
    """Create a mock SEED_DIR where all files exist and return text."""
    mock_dir = MagicMock()
    mock_file = MagicMock()
    mock_file.is_file.return_value = True
    mock_file.read_text.return_value = "# Test content"
    mock_dir.__truediv__ = MagicMock(return_value=mock_file)
    return mock_dir


@contextmanager
def _fake_cognee_module(mock_provider: AsyncMock) -> Generator[None, None, None]:
    """Patch the cognee_provider module so _seed_graph uses our mock provider."""
    mock_module = MagicMock()
    mock_module.CogneeGraphProvider = MagicMock(return_value=mock_provider)
    with patch("app.knowledge.graph.cognee_provider", mock_module):
        yield


class TestSeedGraph:
    """Tests for _seed_graph helper."""

    @pytest.mark.asyncio
    async def test_skips_when_disabled(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Graph seeding prints skip message when Cognee disabled."""
        with patch("app.knowledge.seed.get_settings") as mock_get:
            mock_get.return_value.cognee.enabled = False
            await _seed_graph([])
        captured = capsys.readouterr()
        assert "skipped" in captured.out.lower()
        assert "COGNEE__ENABLED" in captured.out

    @pytest.mark.asyncio
    async def test_skips_when_not_installed(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Graph seeding skips gracefully when cognee package missing."""
        mock_settings = MagicMock()
        mock_settings.cognee.enabled = True

        # Temporarily remove the module from sys.modules AND the parent attribute
        mod_key = "app.knowledge.graph.cognee_provider"
        saved_mod = sys.modules.get(mod_key)
        import app.knowledge.graph as _graph_pkg

        saved_attr = getattr(_graph_pkg, "cognee_provider", None)

        sys.modules[mod_key] = None  # type: ignore[assignment]
        if hasattr(_graph_pkg, "cognee_provider"):
            delattr(_graph_pkg, "cognee_provider")
        try:
            with patch("app.knowledge.seed.get_settings", return_value=mock_settings):
                await _seed_graph([])
        finally:
            if saved_mod is not None:
                sys.modules[mod_key] = saved_mod
            else:
                sys.modules.pop(mod_key, None)
            if saved_attr is not None:
                _graph_pkg.cognee_provider = saved_attr  # pyright: ignore[reportAttributeAccessIssue]

        captured = capsys.readouterr()
        assert "skipped" in captured.out.lower()
        assert "cognee not installed" in captured.out

    @pytest.mark.asyncio
    async def test_groups_by_domain(self) -> None:
        """Documents are grouped by domain as separate Cognee datasets."""
        mock_settings = MagicMock()
        mock_settings.cognee.enabled = True
        mock_provider = AsyncMock()

        with (
            patch("app.knowledge.seed.get_settings", return_value=mock_settings),
            _fake_cognee_module(mock_provider),
            patch("app.knowledge.seed.SEED_DIR", _mock_seed_dir()),
        ):
            entries = [
                _make_entry("css_support/test.md", "css_support"),
                _make_entry("best_practices/test.md", "best_practices"),
            ]
            await _seed_graph(entries)

            assert mock_provider.add_documents.call_count == 2
            assert mock_provider.build_graph.call_count == 2

    @pytest.mark.asyncio
    async def test_build_runs_foreground(self) -> None:
        """Cognify runs in foreground (background=False) during seeding."""
        mock_settings = MagicMock()
        mock_settings.cognee.enabled = True
        mock_provider = AsyncMock()

        with (
            patch("app.knowledge.seed.get_settings", return_value=mock_settings),
            _fake_cognee_module(mock_provider),
            patch("app.knowledge.seed.SEED_DIR", _mock_seed_dir()),
        ):
            entries = [_make_entry("css_support/a.md", "css_support")]
            await _seed_graph(entries)

            mock_provider.build_graph.assert_called_once_with(
                dataset_name="css_support",
                background=False,
            )

    @pytest.mark.asyncio
    async def test_add_failure_does_not_block_other_domains(self) -> None:
        """If one domain fails add_documents, other domains still proceed."""
        mock_settings = MagicMock()
        mock_settings.cognee.enabled = True
        mock_provider = AsyncMock()
        call_count = 0

        async def side_effect(
            texts: list[str],
            *,
            dataset_name: str = "default",
        ) -> None:
            nonlocal call_count
            call_count += 1
            if dataset_name == "css_support":
                raise RuntimeError("Cognee error")

        mock_provider.add_documents = AsyncMock(side_effect=side_effect)

        with (
            patch("app.knowledge.seed.get_settings", return_value=mock_settings),
            _fake_cognee_module(mock_provider),
            patch("app.knowledge.seed.SEED_DIR", _mock_seed_dir()),
        ):
            entries = [
                _make_entry("css_support/a.md", "css_support"),
                _make_entry("best_practices/b.md", "best_practices"),
            ]
            await _seed_graph(entries)

            assert call_count == 2

    @pytest.mark.asyncio
    async def test_skips_missing_files(self) -> None:
        """Entries with missing files are silently skipped."""
        mock_settings = MagicMock()
        mock_settings.cognee.enabled = True
        mock_provider = AsyncMock()
        mock_dir = MagicMock()
        mock_file = MagicMock()
        mock_file.is_file.return_value = False
        mock_dir.__truediv__ = MagicMock(return_value=mock_file)

        with (
            patch("app.knowledge.seed.get_settings", return_value=mock_settings),
            _fake_cognee_module(mock_provider),
            patch("app.knowledge.seed.SEED_DIR", mock_dir),
        ):
            entries = [_make_entry("missing/file.md", "css_support")]
            await _seed_graph(entries)

            mock_provider.add_documents.assert_not_called()
            mock_provider.build_graph.assert_not_called()
