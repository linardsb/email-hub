"""Capture the component matches a real conversion shipped (Jev shadow runner + tests).

Shared by ``scripts/jev_shadow_report.py`` and the Jev shadow tests so both see
exactly the ``match_all`` result ``convert_document`` used, including
``_match_phase`` grouping and ``container_width``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

from app.design_sync import component_matcher
from app.design_sync.component_matcher import ComponentMatch
from app.design_sync.diagnose.report import load_structure_from_json, load_tokens_from_json
from app.design_sync.email_design_document import EmailDesignDocument
from app.design_sync.figma.tree_normalizer import normalize_tree
from app.design_sync.protocol import DesignFileStructure, ExtractedTokens

DEBUG_DIR = Path(__file__).resolve().parents[3] / "data" / "debug"


@dataclass(frozen=True)
class CapturedCase:
    """One case's normalised structure, shipped matches and rendered HTML."""

    case_id: str
    structure: DesignFileStructure
    matches: list[ComponentMatch]
    html: str


def capture_case(case_id: str, debug_dir: Path = DEBUG_DIR) -> CapturedCase:
    """Convert a ``data/debug`` case and capture the one ``match_all`` result."""
    from app.design_sync.converter_service import DesignConverterService

    case_dir = debug_dir / case_id
    structure = load_structure_from_json(case_dir / "structure.json")
    tokens_path = case_dir / "tokens.json"
    tokens = load_tokens_from_json(tokens_path) if tokens_path.exists() else ExtractedTokens()
    structure_norm, _stats = normalize_tree(structure)
    document = EmailDesignDocument.from_legacy(structure_norm, tokens, _pre_normalized=True)

    real_match_all = component_matcher.match_all  # bound before patching: no recursion
    captured: list[list[ComponentMatch]] = []

    def _capture(*args: Any, **kwargs: Any) -> list[ComponentMatch]:
        result = real_match_all(*args, **kwargs)
        captured.append(result)
        return result

    with patch("app.design_sync.component_matcher.match_all", side_effect=_capture):
        conversion = DesignConverterService().convert_document(document)
    if len(captured) != 1:
        msg = f"case {case_id}: expected 1 match_all call, got {len(captured)}"
        raise RuntimeError(msg)
    return CapturedCase(case_id, structure_norm, captured[0], conversion.html)
