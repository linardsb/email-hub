"""EmailDesignDocument v2 — version dispatch, v1/v2 schema parity, real-case corpus."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from app.design_sync.diagnose.report import load_structure_from_json, load_tokens_from_json
from app.design_sync.dsl.nodes import (
    NODE_CLASSES,
    AnyNode,
    BodyNode,
    ButtonNode,
    ColumnNode,
    ContainerStyle,
    DividerNode,
    DividerStyle,
    HorizontalAlign,
    ImageNode,
    NodeType,
    RawNode,
    SectionNode,
    Sizing,
    SpacerNode,
    TextNode,
    TextRole,
    VerticalAlign,
    WrapperNode,
)
from app.design_sync.email_design_document import (
    DocumentButton,
    DocumentImage,
    DocumentText,
    EmailDesignDocument,
)
from app.design_sync.tests.regression_runner import discover_cases

_CASES = discover_cases()
_SCHEMA_DIR = Path(__file__).resolve().parents[3] / "data" / "schemas"
_V1 = json.loads((_SCHEMA_DIR / "email-design-document-v1.json").read_text())
_V2 = json.loads((_SCHEMA_DIR / "email-design-document-v2.json").read_text())


def _case_document(case_dir: Path) -> EmailDesignDocument:
    structure_path = case_dir / "structure.json"
    tokens_path = case_dir / "tokens.json"
    if not structure_path.exists() or not tokens_path.exists():
        pytest.skip(f"{case_dir.name}: missing structure.json/tokens.json")
    return EmailDesignDocument.from_legacy(
        load_structure_from_json(structure_path), load_tokens_from_json(tokens_path)
    )


# ── Real-case corpus (v1) ──


@pytest.mark.parametrize("case_dir", _CASES, ids=[c.name for c in _CASES])
def test_case_v1_round_trip_byte_identical(case_dir: Path) -> None:
    data = _case_document(case_dir).to_json()
    restored = EmailDesignDocument.from_json(json.loads(json.dumps(data)))
    assert json.dumps(restored.to_json()) == json.dumps(data)


@pytest.mark.parametrize("case_dir", _CASES, ids=[c.name for c in _CASES])
def test_case_v1_document_validates(case_dir: Path) -> None:
    assert EmailDesignDocument.validate(_case_document(case_dir).to_json()) == []


# ── v2 documents built on case 5 ──


def _case5_document() -> EmailDesignDocument:
    case_dir = next((c for c in _CASES if c.name == "5"), None)
    if case_dir is None:
        pytest.skip("case 5 not present")
    return _case_document(case_dir)


def _leaf_payloads(
    doc: EmailDesignDocument,
) -> tuple[DocumentText, DocumentImage, DocumentButton]:
    """First text, image and button in case 5, so the fixture carries real payloads."""
    texts = [t for s in doc.sections for t in [*s.texts, *(t for c in s.columns for t in c.texts)]]
    images = [
        i for s in doc.sections for i in [*s.images, *(i for c in s.columns for i in c.images)]
    ]
    buttons = [
        b for s in doc.sections for b in [*s.buttons, *(b for c in s.columns for b in c.buttons)]
    ]
    return texts[0], images[0], buttons[0]


def _all_nine_body(doc: EmailDesignDocument) -> tuple[BodyNode, ...]:
    text, image, button = _leaf_payloads(doc)
    column = ColumnNode(
        id="c:1",
        name="column",
        style=ContainerStyle(background_color="#f4f4f4", radius=(8, 8, 0, 0), sizing=Sizing.FILL),
        children=(
            TextNode(
                id="t:1",
                name="heading",
                text=text,
                role=TextRole.HEADING,
                font_stack=("Inter", "Helvetica", "sans-serif"),
            ),
            ImageNode(id="i:1", name="hero", image=image, alt="Hero", sizing=Sizing.FIXED),
            ButtonNode(
                id="b:1", name="cta", button=button, align=HorizontalAlign.CENTER, sizing=Sizing.HUG
            ),
            DividerNode(
                id="d:1", name="rule", thickness=1, color="#cccccc", style=DividerStyle.SOLID
            ),
            SpacerNode(id="s:1", name="gap", height=24),
            RawNode(
                id="r:1",
                name="legal",
                html="<table><tr><td>x</td></tr></table>",
                reason="dsl.overlap",
            ),
        ),
    )
    section = SectionNode(
        id="sec:1",
        name="card",
        style=ContainerStyle(radius=12, padding=(16, 24, 16, 24), vertical_align=VerticalAlign.TOP),
        children=(column,),
    )
    wrapper = WrapperNode(
        id="w:1",
        name="band",
        style=ContainerStyle(background_color="#ffffff", full_width=True, background_image=image),
        children=(section,),
    )
    bare = SectionNode(
        id="sec:2", name="footer", children=(ColumnNode(id="c:2", name="col", children=()),)
    )
    return (
        wrapper,
        RawNode(id="r:2", name="preheader", html="<table></table>", reason="dsl.overlap"),
        bare,
    )


def _v2_document() -> EmailDesignDocument:
    doc = _case5_document()
    return replace(doc, version="2.0", body=_all_nine_body(doc))


def v2_case5_json() -> dict[str, Any]:
    """A valid v2 document using all nine node types (also used by the endpoint test)."""
    return _v2_document().to_json()


def _walk(nodes: tuple[AnyNode, ...]) -> Iterator[AnyNode]:
    for node in nodes:
        yield node
        if isinstance(node, WrapperNode | SectionNode | ColumnNode):
            yield from _walk(node.children)


def _error_paths(errors: list[str]) -> set[str]:
    return {e.split(": ", 1)[0] for e in errors}


def test_v2_all_nine_round_trip_and_validate() -> None:
    doc = _v2_document()
    j = doc.to_json()
    assert EmailDesignDocument.validate(j) == []
    restored = EmailDesignDocument.from_json(json.loads(json.dumps(j)))
    assert json.dumps(restored.to_json()) == json.dumps(j)
    assert restored.body == doc.body
    assert {n.type for n in _walk(doc.body)} == set(NodeType)


def test_v2_empty_body_validates() -> None:
    j = replace(_case5_document(), version="2.0").to_json()
    assert j["body"] == []
    assert EmailDesignDocument.validate(j) == []


def test_v2_unknown_node_type_fails_validation() -> None:
    j = v2_case5_json()
    j["body"][0]["children"][0]["children"][0]["children"][0]["type"] = "carousel"
    errors = EmailDesignDocument.validate(j)
    assert errors != []
    # A nested oneOf failure surfaces at the outermost body item.
    assert _error_paths(errors) == {"body.0"}
    with pytest.raises(ValueError, match="carousel"):
        EmailDesignDocument.from_json(j)


def test_v2_illegal_nesting_fails() -> None:
    j = v2_case5_json()
    column_children = j["body"][0]["children"][0]["children"][0]["children"]
    j["body"].append(column_children[0])  # a text node directly under body
    errors = EmailDesignDocument.validate(j)
    assert _error_paths(errors) == {f"body.{len(j['body']) - 1}"}
    with pytest.raises(ValueError, match="not allowed in a body"):
        EmailDesignDocument.from_json(j)


def test_v2_missing_body_fails_validation() -> None:
    j = v2_case5_json()
    del j["body"]
    errors = EmailDesignDocument.validate(j)
    assert any(e.startswith("(root)") and "'body' is a required property" in e for e in errors)


# ── Schema parity ──


class TestSchemaParity:
    def test_shared_defs_identical(self) -> None:
        for key, value in _V1["$defs"].items():
            assert _V2["$defs"][key] == value, key

    def test_root_properties_v1_plus_body(self) -> None:
        v1_props = {k: v for k, v in _V1["properties"].items() if k != "version"}
        v2_props = {k: v for k, v in _V2["properties"].items() if k not in ("version", "body")}
        assert v2_props == v1_props
        assert _V2["properties"]["version"]["const"] == "2.0"
        assert set(_V2["required"]) == set(_V1["required"]) | {"body"}
        assert _V2["additionalProperties"] is False

    def test_new_defs(self) -> None:
        assert set(_V2["$defs"]) - set(_V1["$defs"]) == {f"node_{t.value}" for t in NodeType} | {
            "container_style",
            "hex6",
            "sizing",
        }

    def test_node_type_consts(self) -> None:
        for t in NodeType:
            assert _V2["$defs"][f"node_{t.value}"]["properties"]["type"] == {"const": t.value}

    def test_enum_parity(self) -> None:
        defs = _V2["$defs"]
        assert set(NODE_CLASSES) == set(NodeType)
        assert all(NODE_CLASSES[t].type is t for t in NodeType)
        assert set(defs["sizing"]["enum"]) == {s.value for s in Sizing}
        assert set(defs["node_text"]["properties"]["role"]["enum"]) == {r.value for r in TextRole}
        assert set(defs["node_divider"]["properties"]["style"]["enum"]) == {
            s.value for s in DividerStyle
        }
        assert set(defs["node_button"]["properties"]["align"]["enum"]) == {
            a.value for a in HorizontalAlign
        }
        assert set(defs["container_style"]["properties"]["vertical_align"]["enum"]) == {
            v.value for v in VerticalAlign
        }
