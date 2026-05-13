"""Single I/O surface for converter trace artefacts (F060)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any


class TraceWriter:
    """Unified read/write surface for JSONL + JSON trace artefacts.

    Holds the file-path conventions so callers reference categories
    (``"converter_trace"``, ``"correction_log"``, ``"baseline"``…) rather
    than path literals scattered across the package.
    """

    def __init__(
        self,
        *,
        traces_jsonl_path: Path,
        correction_log_path: Path,
        correction_rules_path: Path,
        baseline_path: Path,
    ) -> None:
        self._jsonl: dict[str, Path] = {
            "converter_trace": traces_jsonl_path,
            "correction_log": correction_log_path,
        }
        self._json: dict[str, Path] = {
            "correction_rules": correction_rules_path,
            "baseline": baseline_path,
        }

    def append_jsonl(self, category: str, event: dict[str, Any]) -> None:
        """Append ``event`` as a single JSONL line under ``category``."""
        path = self._jsonl[category]
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, default=str) + "\n")

    def read_jsonl(self, category: str, *, last_n: int | None = None) -> list[dict[str, Any]]:
        """Read JSONL records for ``category``; returns last ``last_n`` if set."""
        path = self._jsonl[category]
        if not path.exists():
            return []
        records: list[dict[str, Any]] = []
        with path.open(encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if line:
                    records.append(json.loads(line))
        return records[-last_n:] if last_n is not None else records

    def iter_jsonl(self, category: str) -> Iterator[dict[str, Any]]:
        """Yield JSONL records without loading the whole file into memory."""
        path = self._jsonl[category]
        if not path.exists():
            return
        with path.open(encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if line:
                    yield json.loads(line)

    def read_json(self, category: str) -> dict[str, Any] | None:
        """Read a category's JSON file or return ``None`` if it does not exist."""
        path = self._json[category]
        if not path.exists():
            return None
        with path.open(encoding="utf-8") as f:
            return dict(json.load(f))

    def write_json(self, category: str, data: dict[str, Any]) -> None:
        path = self._json[category]
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def path_for(self, category: str) -> Path:
        """Return the path for a category (jsonl or json)."""
        if category in self._jsonl:
            return self._jsonl[category]
        return self._json[category]
