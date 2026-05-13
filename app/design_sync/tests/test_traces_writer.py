"""F060 — TraceWriter round-trip tests."""

from __future__ import annotations

from pathlib import Path

from app.design_sync.traces.writer import TraceWriter


def _make_writer(tmp_path: Path) -> TraceWriter:
    return TraceWriter(
        traces_jsonl_path=tmp_path / "traces.jsonl",
        correction_log_path=tmp_path / "corrections.jsonl",
        correction_rules_path=tmp_path / "rules.json",
        baseline_path=tmp_path / "baseline.json",
    )


def test_append_and_read_jsonl(tmp_path: Path) -> None:
    writer = _make_writer(tmp_path)
    writer.append_jsonl("converter_trace", {"id": "a", "n": 1})
    writer.append_jsonl("converter_trace", {"id": "b", "n": 2})
    writer.append_jsonl("converter_trace", {"id": "c", "n": 3})

    records = writer.read_jsonl("converter_trace")
    assert [r["id"] for r in records] == ["a", "b", "c"]


def test_read_jsonl_last_n(tmp_path: Path) -> None:
    writer = _make_writer(tmp_path)
    for i in range(5):
        writer.append_jsonl("converter_trace", {"i": i})
    last_two = writer.read_jsonl("converter_trace", last_n=2)
    assert [r["i"] for r in last_two] == [3, 4]


def test_read_jsonl_empty_when_no_file(tmp_path: Path) -> None:
    writer = _make_writer(tmp_path)
    assert writer.read_jsonl("converter_trace") == []
    assert list(writer.iter_jsonl("converter_trace")) == []


def test_json_round_trip(tmp_path: Path) -> None:
    writer = _make_writer(tmp_path)
    assert writer.read_json("baseline") is None
    writer.write_json("baseline", {"avg_quality_score": 0.82})
    assert writer.read_json("baseline") == {"avg_quality_score": 0.82}


def test_path_for_returns_configured_paths(tmp_path: Path) -> None:
    writer = _make_writer(tmp_path)
    assert writer.path_for("converter_trace") == tmp_path / "traces.jsonl"
    assert writer.path_for("correction_log") == tmp_path / "corrections.jsonl"
    assert writer.path_for("correction_rules") == tmp_path / "rules.json"
    assert writer.path_for("baseline") == tmp_path / "baseline.json"
