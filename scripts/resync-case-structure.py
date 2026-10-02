"""Re-parse a case's local ``raw_figma.json`` into ``structure.json`` with the current parser.

Offline twin of ``python -m app.design_sync.diagnose.extract`` per-campaign mode
(``app/design_sync/diagnose/extract.py``): same ``_parse_node`` call, same page
wrapper, no Figma API call. ``raw_figma.json`` is gitignored, so this runs only
where the raw node response is on disk.

Usage (from repo root):

    uv run python scripts/resync-case-structure.py 5
    uv run python scripts/resync-case-structure.py reframe --out /tmp/structure.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.design_sync.diagnose.report import dump_structure_to_json  # noqa: E402
from app.design_sync.figma.service import FigmaDesignSyncService  # noqa: E402
from app.design_sync.protocol import (  # noqa: E402
    DesignFileStructure,
    DesignNode,
    DesignNodeType,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", help="case id under data/debug/")
    parser.add_argument("--node-id", help="Figma node id (default: the raw response's only node)")
    parser.add_argument("--out", type=Path, help="output path (default: the case's structure.json)")
    args = parser.parse_args()

    case_dir = REPO / "data/debug" / args.case
    raw = json.loads((case_dir / "raw_figma.json").read_text())
    nodes: dict[str, Any] = raw.get("nodes", {})
    node_id = args.node_id.replace("-", ":") if args.node_id else None
    if node_id is None:
        if len(nodes) != 1:
            raise SystemExit(f"case {args.case}: {len(nodes)} nodes in raw; pass --node-id")
        node_id = next(iter(nodes))
    doc = nodes[node_id]["document"]

    parsed = FigmaDesignSyncService()._parse_node(doc, current_depth=0, max_depth=None)
    page = DesignNode(id="0:1", name="Email", type=DesignNodeType.PAGE, children=[parsed])
    structure = DesignFileStructure(file_name=raw.get("name", "Untitled"), pages=[page])

    out: Path = args.out or case_dir / "structure.json"
    dump_structure_to_json(structure, out)
    with out.open("a") as f:  # end-of-file-fixer hook wants a final newline
        f.write("\n")
    print(
        f"case {args.case}: node {node_id}, Figma version {raw.get('version')} "
        f"({raw.get('lastModified')}) -> {out}"
    )


if __name__ == "__main__":
    main()
