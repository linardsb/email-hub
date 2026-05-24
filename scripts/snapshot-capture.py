#!/usr/bin/env python3
"""Capture current converter output for a snapshot test case.

Usage:
    python scripts/snapshot-capture.py <case_id>
    python scripts/snapshot-capture.py 5
    python scripts/snapshot-capture.py 5 --overwrite   # Replace existing expected.html

Runs the full converter pipeline on data/debug/<case_id>/ inputs
and saves the output to expected.html for visual verification.

After running:
    1. Open data/debug/<case_id>/expected.html in a browser
    2. Verify the output looks correct visually
    3. Set status: active in data/debug/manifest.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.design_sync.converter_service import DesignConverterService
from app.design_sync.diagnose.report import load_structure_from_json, load_tokens_from_json
from app.design_sync.email_design_document import EmailDesignDocument


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture converter output for snapshot testing")
    parser.add_argument("case_id", help="Case directory name under data/debug/")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing expected.html")
    parser.add_argument(
        "--output",
        default=None,
        help="Custom output path (default: data/debug/<case_id>/expected.html)",
    )
    args = parser.parse_args()

    debug_dir = Path(__file__).resolve().parents[1] / "data" / "debug"
    case_dir = debug_dir / args.case_id

    if not case_dir.exists():
        print(f"Error: Case directory not found: {case_dir}")
        sys.exit(1)

    structure_path = case_dir / "structure.json"
    tokens_path = case_dir / "tokens.json"

    if not structure_path.exists():
        print(f"Error: Missing {structure_path}")
        sys.exit(1)
    if not tokens_path.exists():
        print(f"Error: Missing {tokens_path}")
        sys.exit(1)

    output_path = Path(args.output) if args.output else case_dir / "expected.html"
    if output_path.exists() and not args.overwrite:
        print(f"Error: {output_path} already exists. Use --overwrite to replace.")
        sys.exit(1)

    print(f"Loading case {args.case_id}...")
    structure = load_structure_from_json(structure_path)
    tokens = load_tokens_from_json(tokens_path)

    print(f"  Nodes: {sum(1 for _ in _count_nodes(structure.pages))}")
    print(f"  Colors: {len(tokens.colors)}, Typography: {len(tokens.typography)}")

    print("Running converter...")
    document = EmailDesignDocument.from_legacy(structure, tokens)
    converter = DesignConverterService()
    result = converter.convert_document(document)

    print(f"  Sections: {result.sections_count}")
    print(f"  Warnings: {len(result.warnings)}")
    for w in result.warnings:
        print(f"    - {w}")
    print(f"  HTML length: {len(result.html)} chars")

    output_path.write_text(result.html)
    print(f"\nOutput saved to: {output_path}")
    print("\nNext steps:")
    print(f"  1. Open {output_path} in a browser")
    print("  2. Verify the output looks correct visually")
    print(f"  3. Set status: active for case '{args.case_id}' in data/debug/manifest.yaml")
    print("  4. Run: make snapshot-test")


def _count_nodes(nodes: list) -> list:  # type: ignore[type-arg]
    """Recursively count nodes."""
    result = []
    for n in nodes:
        result.append(n)
        result.extend(_count_nodes(getattr(n, "children", [])))
    return result


if __name__ == "__main__":
    main()
