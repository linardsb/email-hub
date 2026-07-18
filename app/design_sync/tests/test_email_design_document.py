"""Tests for EmailDesignDocument v1 — schema validation, roundtrip, bridges, API."""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.design_sync.email_design_document import (
    CompatibilityHint,
    DocumentButton,
    DocumentColor,
    DocumentColumn,
    DocumentGradient,
    DocumentGradientStop,
    DocumentImage,
    DocumentLayout,
    DocumentPadding,
    DocumentSection,
    DocumentSource,
    DocumentSpacing,
    DocumentText,
    DocumentTokens,
    DocumentTypography,
    DocumentVariable,
    EmailDesignDocument,
    TokenWarning,
)
from app.design_sync.figma.layout_analyzer import (
    ColumnLayout,
    EmailSectionType,
)
from app.design_sync.protocol import ExtractedGradient, ExtractedTokens

# ── Factories ──


def _make_document(**overrides: Any) -> EmailDesignDocument:
    defaults: dict[str, Any] = {
        "version": "1.0",
        "tokens": DocumentTokens(),
        "sections": [],
        "layout": DocumentLayout(container_width=600),
    }
    defaults.update(overrides)
    return EmailDesignDocument(**defaults)


def _make_full_document() -> EmailDesignDocument:
    return EmailDesignDocument(
        version="1.0",
        source=DocumentSource(
            provider="figma", file_ref="abc123", synced_at="2026-03-27T10:00:00Z"
        ),
        tokens=DocumentTokens(
            colors=[DocumentColor(name="Primary", hex="#538FE4", opacity=0.9)],
            typography=[
                DocumentTypography(
                    name="Heading",
                    family="Inter",
                    weight="700",
                    size=32.0,
                    line_height=40.0,
                    letter_spacing=0.5,
                    text_transform="uppercase",
                    text_decoration="underline",
                )
            ],
            spacing=[DocumentSpacing(name="md", value=16.0)],
            dark_colors=[DocumentColor(name="DarkPrimary", hex="#1A1A2E")],
            gradients=[
                DocumentGradient(
                    name="bg",
                    type="linear",
                    angle=90.0,
                    stops=(
                        DocumentGradientStop(hex="#FF0000", position=0.0),
                        DocumentGradientStop(hex="#0000FF", position=1.0),
                    ),
                    fallback_hex="#800080",
                )
            ],
            variables=[
                DocumentVariable(
                    name="brand-color",
                    collection="Brand",
                    type="COLOR",
                    values_by_mode={"light": "#538FE4"},
                    is_alias=True,
                    alias_path="colors/primary",
                )
            ],
            stroke_colors=[DocumentColor(name="Border", hex="#CCCCCC")],
            variables_source=True,
            modes={"mode1": "Light"},
        ),
        sections=[
            DocumentSection(
                id="s1",
                type="hero",
                node_name="Hero Section",
                y_position=0.0,
                width=600.0,
                height=400.0,
                column_layout="two-column",
                column_count=2,
                padding=DocumentPadding(top=20.0, right=16.0, bottom=20.0, left=16.0),
                item_spacing=12.0,
                background_color="#FFFFFF",
                texts=[
                    DocumentText(
                        node_id="t1",
                        content="Hello World",
                        font_size=32.0,
                        is_heading=True,
                        font_family="Inter",
                        font_weight=700,
                        line_height=40.0,
                        letter_spacing=0.5,
                    )
                ],
                images=[
                    DocumentImage(node_id="img1", node_name="Hero Image", width=300.0, height=200.0)
                ],
                buttons=[DocumentButton(node_id="btn1", text="Click Me", width=200.0, height=48.0)],
                columns=[
                    DocumentColumn(
                        column_idx=0,
                        node_id="col1",
                        node_name="Left",
                        width=300.0,
                        texts=[DocumentText(node_id="ct1", content="Col text")],
                        images=[DocumentImage(node_id="ci1", node_name="Col img")],
                        buttons=[DocumentButton(node_id="cb1", text="Col btn")],
                    )
                ],
                content_roles=["logo", "social_links"],
                spacing_after=24.0,
                classification_confidence=0.95,
                element_gaps=[10.0, 20.0],
            )
        ],
        layout=DocumentLayout(container_width=600, naming_convention="mjml", overall_width=640.0),
        compatibility_hints=[
            CompatibilityHint(
                level="warning",
                css_property="border-radius",
                message="Not supported in Outlook",
                affected_clients=["outlook"],
            )
        ],
        token_warnings=[
            TokenWarning(
                level="warning",
                field="colors[0].hex",
                message="Converted from rgba",
                fixed_value="#538FE4",
            )
        ],
    )


# ── Schema Validation Tests ──


class TestSchemaValidation:
    def test_minimal_valid_document(self) -> None:
        data: dict[str, Any] = {
            "version": "1.0",
            "tokens": {},
            "sections": [],
            "layout": {"container_width": 600},
        }
        assert EmailDesignDocument.validate(data) == []

    def test_missing_version(self) -> None:
        data: dict[str, Any] = {"tokens": {}, "sections": [], "layout": {"container_width": 600}}
        errors = EmailDesignDocument.validate(data)
        assert any("version" in e for e in errors)

    def test_missing_tokens(self) -> None:
        data: dict[str, Any] = {
            "version": "1.0",
            "sections": [],
            "layout": {"container_width": 600},
        }
        errors = EmailDesignDocument.validate(data)
        assert any("tokens" in e for e in errors)

    def test_missing_sections(self) -> None:
        data: dict[str, Any] = {"version": "1.0", "tokens": {}, "layout": {"container_width": 600}}
        errors = EmailDesignDocument.validate(data)
        assert any("sections" in e for e in errors)

    def test_missing_layout(self) -> None:
        data: dict[str, Any] = {"version": "1.0", "tokens": {}, "sections": []}
        errors = EmailDesignDocument.validate(data)
        assert any("layout" in e for e in errors)

    def test_wrong_version(self) -> None:
        data: dict[str, Any] = {
            "version": "2.0",
            "tokens": {},
            "sections": [],
            "layout": {"container_width": 600},
        }
        errors = EmailDesignDocument.validate(data)
        assert any("version" in e.lower() or "1.0" in e for e in errors)

    def test_invalid_section_type(self) -> None:
        data: dict[str, Any] = {
            "version": "1.0",
            "tokens": {},
            "sections": [{"id": "s1", "type": "banana"}],
            "layout": {"container_width": 600},
        }
        errors = EmailDesignDocument.validate(data)
        assert len(errors) > 0
        assert any("banana" in e for e in errors)

    def test_invalid_color_hex(self) -> None:
        data: dict[str, Any] = {
            "version": "1.0",
            "tokens": {"colors": [{"name": "Bad", "hex": "not-a-hex"}]},
            "sections": [],
            "layout": {"container_width": 600},
        }
        errors = EmailDesignDocument.validate(data)
        assert len(errors) > 0

    def test_too_many_sections(self) -> None:
        data: dict[str, Any] = {
            "version": "1.0",
            "tokens": {},
            "sections": [{"id": f"s{i}", "type": "content"} for i in range(101)],
            "layout": {"container_width": 600},
        }
        errors = EmailDesignDocument.validate(data)
        assert any("101" in e or "maxItems" in e or "100" in e for e in errors)

    def test_too_many_colors(self) -> None:
        data: dict[str, Any] = {
            "version": "1.0",
            "tokens": {"colors": [{"name": f"c{i}", "hex": "#AABBCC"} for i in range(501)]},
            "sections": [],
            "layout": {"container_width": 600},
        }
        errors = EmailDesignDocument.validate(data)
        assert len(errors) > 0

    def test_unknown_field_on_section_rejected(self) -> None:
        data: dict[str, Any] = {
            "version": "1.0",
            "tokens": {},
            "sections": [{"id": "s1", "type": "header", "bogus_field": 42}],
            "layout": {"container_width": 600},
        }
        errors = EmailDesignDocument.validate(data)
        assert any("bogus_field" in e for e in errors)

    def test_container_width_too_small(self) -> None:
        data: dict[str, Any] = {
            "version": "1.0",
            "tokens": {},
            "sections": [],
            "layout": {"container_width": 399},
        }
        errors = EmailDesignDocument.validate(data)
        assert len(errors) > 0

    def test_container_width_too_large(self) -> None:
        data: dict[str, Any] = {
            "version": "1.0",
            "tokens": {},
            "sections": [],
            "layout": {"container_width": 801},
        }
        errors = EmailDesignDocument.validate(data)
        assert len(errors) > 0

    def test_unknown_root_field_rejected(self) -> None:
        data: dict[str, Any] = {
            "version": "1.0",
            "tokens": {},
            "sections": [],
            "layout": {"container_width": 600},
            "extra_root": True,
        }
        errors = EmailDesignDocument.validate(data)
        assert any("extra_root" in e for e in errors)

    def test_full_valid_document(self) -> None:
        doc = _make_full_document()
        data = doc.to_json()
        assert EmailDesignDocument.validate(data) == []

    def test_schema_returns_dict_with_defs(self) -> None:
        schema = EmailDesignDocument.schema()
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert "$defs" in schema
        assert "section" in schema["$defs"]

    def test_classification_confidence_out_of_range(self) -> None:
        data: dict[str, Any] = {
            "version": "1.0",
            "tokens": {},
            "sections": [{"id": "s1", "type": "content", "classification_confidence": 1.5}],
            "layout": {"container_width": 600},
        }
        errors = EmailDesignDocument.validate(data)
        assert len(errors) > 0


# ── Roundtrip Tests ──


class TestRoundtrip:
    def test_minimal_roundtrip(self) -> None:
        doc = _make_document()
        restored = EmailDesignDocument.from_json(doc.to_json())
        assert restored.version == doc.version
        assert restored.sections == doc.sections
        assert restored.layout.container_width == doc.layout.container_width

    def test_full_roundtrip(self) -> None:
        doc = _make_full_document()
        data = doc.to_json()
        restored = EmailDesignDocument.from_json(data)

        assert restored.version == doc.version
        assert restored.source is not None
        assert restored.source.provider == "figma"
        assert restored.source.file_ref == "abc123"
        assert len(restored.tokens.colors) == 1
        assert restored.tokens.colors[0].hex == "#538FE4"
        assert restored.tokens.colors[0].opacity == 0.9
        assert len(restored.tokens.typography) == 1
        assert restored.tokens.typography[0].text_transform == "uppercase"
        assert len(restored.tokens.spacing) == 1
        assert len(restored.tokens.dark_colors) == 1
        assert len(restored.tokens.gradients) == 1
        assert len(restored.tokens.gradients[0].stops) == 2
        assert len(restored.tokens.variables) == 1
        assert restored.tokens.variables[0].is_alias is True
        assert len(restored.tokens.stroke_colors) == 1
        assert restored.tokens.variables_source is True
        assert restored.tokens.modes == {"mode1": "Light"}

        assert len(restored.sections) == 1
        s = restored.sections[0]
        assert s.type == "hero"
        assert s.column_layout == "two-column"
        assert s.padding is not None
        assert s.padding.top == 20.0
        assert len(s.texts) == 1
        assert s.texts[0].is_heading is True
        assert len(s.images) == 1
        assert len(s.buttons) == 1
        assert len(s.columns) == 1
        assert s.columns[0].column_idx == 0
        assert len(s.columns[0].texts) == 1
        assert s.content_roles == ["logo", "social_links"]
        assert s.classification_confidence == 0.95
        assert s.element_gaps == [10.0, 20.0]

        assert restored.layout.naming_convention == "mjml"
        assert restored.layout.overall_width == 640.0
        assert len(restored.compatibility_hints) == 1
        assert restored.compatibility_hints[0].affected_clients == ["outlook"]
        assert len(restored.token_warnings) == 1
        assert restored.token_warnings[0].fixed_value == "#538FE4"

    def test_empty_optional_fields(self) -> None:
        doc = _make_document()
        restored = EmailDesignDocument.from_json(doc.to_json())
        assert restored.source is None
        assert restored.compatibility_hints == []
        assert restored.token_warnings == []
        assert restored.tokens.colors == []
        assert restored.tokens.dark_colors == []
        assert restored.tokens.modes is None
        assert restored.tokens.variables_source is False

    def test_malformed_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Malformed EmailDesignDocument"):
            EmailDesignDocument.from_json({"version": "1.0", "tokens": {"colors": [{"bad": True}]}})

    def test_json_serializable(self) -> None:
        doc = _make_full_document()
        json_str = json.dumps(doc.to_json())
        parsed = json.loads(json_str)
        assert parsed["version"] == "1.0"


# ── Bridge Method Tests ──


class TestBridgeMethods:
    def test_to_extracted_tokens_colors(self) -> None:
        doc = _make_full_document()
        tokens = doc.to_extracted_tokens()
        assert len(tokens.colors) == 1
        assert tokens.colors[0].name == "Primary"
        assert tokens.colors[0].hex == "#538FE4"
        assert tokens.colors[0].opacity == 0.9

    def test_to_extracted_tokens_typography(self) -> None:
        doc = _make_full_document()
        tokens = doc.to_extracted_tokens()
        assert len(tokens.typography) == 1
        t = tokens.typography[0]
        assert t.family == "Inter"
        assert t.weight == "700"
        assert t.size == 32.0
        assert t.line_height == 40.0
        assert t.letter_spacing == 0.5
        assert t.text_transform == "uppercase"
        assert t.text_decoration == "underline"

    def test_to_extracted_tokens_spacing(self) -> None:
        doc = _make_full_document()
        tokens = doc.to_extracted_tokens()
        assert len(tokens.spacing) == 1
        assert tokens.spacing[0].name == "md"
        assert tokens.spacing[0].value == 16.0

    def test_to_extracted_tokens_dark_colors(self) -> None:
        doc = _make_full_document()
        tokens = doc.to_extracted_tokens()
        assert len(tokens.dark_colors) == 1
        assert tokens.dark_colors[0].hex == "#1A1A2E"

    def test_to_extracted_tokens_gradients(self) -> None:
        doc = _make_full_document()
        tokens = doc.to_extracted_tokens()
        assert len(tokens.gradients) == 1
        g = tokens.gradients[0]
        assert g.name == "bg"
        assert g.type == "linear"
        assert g.angle == 90.0
        assert g.stops == (("#FF0000", 0.0), ("#0000FF", 1.0))
        assert g.fallback_hex == "#800080"

    def test_to_extracted_tokens_variables(self) -> None:
        doc = _make_full_document()
        tokens = doc.to_extracted_tokens()
        assert len(tokens.variables) == 1
        v = tokens.variables[0]
        assert v.name == "brand-color"
        assert v.collection == "Brand"
        assert v.type == "COLOR"
        assert v.is_alias is True
        assert v.alias_path == "colors/primary"

    def test_to_extracted_tokens_stroke_colors(self) -> None:
        doc = _make_full_document()
        tokens = doc.to_extracted_tokens()
        assert len(tokens.stroke_colors) == 1
        assert tokens.stroke_colors[0].hex == "#CCCCCC"

    def test_to_extracted_tokens_metadata(self) -> None:
        doc = _make_full_document()
        tokens = doc.to_extracted_tokens()
        assert tokens.variables_source is True
        assert tokens.modes == {"mode1": "Light"}

    def test_to_email_sections(self) -> None:
        doc = _make_full_document()
        sections = doc.to_email_sections()
        assert len(sections) == 1
        s = sections[0]
        assert s.section_type == EmailSectionType.HERO
        assert s.node_id == "s1"
        assert s.node_name == "Hero Section"
        assert s.column_layout == ColumnLayout.TWO_COLUMN
        assert s.column_count == 2
        assert s.width == 600.0
        assert s.height == 400.0
        assert s.padding_top == 20.0
        assert s.padding_right == 16.0
        assert s.padding_bottom == 20.0
        assert s.padding_left == 16.0
        assert s.item_spacing == 12.0
        assert s.bg_color == "#FFFFFF"
        assert len(s.texts) == 1
        assert s.texts[0].content == "Hello World"
        assert s.texts[0].is_heading is True
        assert len(s.images) == 1
        assert len(s.buttons) == 1
        assert len(s.column_groups) == 1
        assert s.column_groups[0].column_idx == 0
        assert len(s.column_groups[0].texts) == 1
        assert s.spacing_after == 24.0
        assert s.classification_confidence == 0.95
        assert s.content_roles == ("logo", "social_links")
        assert s.element_gaps == (10.0, 20.0)

    def test_to_email_sections_no_padding(self) -> None:
        doc = _make_document(sections=[DocumentSection(id="s1", type="content")])
        sections = doc.to_email_sections()
        assert sections[0].padding_top is None

    def test_to_layout_description(self) -> None:
        doc = _make_full_document()
        layout = doc.to_layout_description(file_name="test.fig")
        assert layout.file_name == "test.fig"
        assert layout.overall_width == 640.0
        assert len(layout.sections) == 1
        assert layout.total_text_blocks == 1
        assert layout.total_images == 1

    def test_to_layout_description_empty(self) -> None:
        doc = _make_document()
        layout = doc.to_layout_description()
        assert layout.file_name == ""
        assert layout.overall_width is None
        assert layout.sections == []
        assert layout.total_text_blocks == 0
        assert layout.total_images == 0


# ── API Endpoint Tests ──


def _make_user(role: str = "admin") -> Any:
    from unittest.mock import MagicMock

    user = MagicMock()
    user.id = 1
    user.role = role
    return user


class TestDocumentEndpoints:
    @pytest.fixture(autouse=True)
    def _disable_rate_limit(self) -> Generator[None]:
        from app.core.rate_limit import limiter

        limiter.enabled = False
        yield
        limiter.enabled = True

    @pytest.fixture()
    def _auth_admin(self) -> Generator[None]:
        from app.auth.dependencies import get_current_user
        from app.main import app

        user = _make_user("admin")
        app.dependency_overrides[get_current_user] = lambda: user
        yield
        app.dependency_overrides.pop(get_current_user, None)

    @pytest.fixture()
    def client(self) -> TestClient:
        from app.main import app

        return TestClient(app)

    @pytest.mark.usefixtures("_auth_admin")
    def test_get_schema_v1(self, client: TestClient) -> None:
        resp = client.get("/api/v1/design-sync/schema/v1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert "$defs" in body
        assert resp.headers.get("cache-control") == "public, max-age=86400"

    @pytest.mark.usefixtures("_auth_admin")
    def test_validate_document_valid(self, client: TestClient) -> None:
        data: dict[str, Any] = {
            "version": "1.0",
            "tokens": {},
            "sections": [],
            "layout": {"container_width": 600},
        }
        resp = client.post("/api/v1/design-sync/validate-document", json=data)
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True
        assert body["errors"] == []

    @pytest.mark.usefixtures("_auth_admin")
    def test_validate_document_invalid(self, client: TestClient) -> None:
        data: dict[str, Any] = {"version": "2.0"}
        resp = client.post("/api/v1/design-sync/validate-document", json=data)
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False
        assert len(body["errors"]) > 0

    @pytest.mark.usefixtures("_auth_admin")
    def test_validate_document_not_json(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/design-sync/validate-document",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False
        assert any("not valid JSON" in e for e in body["errors"])

    @pytest.mark.usefixtures("_auth_admin")
    def test_validate_document_not_object(self, client: TestClient) -> None:
        resp = client.post("/api/v1/design-sync/validate-document", json=[1, 2, 3])
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False
        assert any("object" in e.lower() for e in body["errors"])

    def test_validate_document_requires_auth(self, client: TestClient) -> None:
        data: dict[str, Any] = {
            "version": "1.0",
            "tokens": {},
            "sections": [],
            "layout": {"container_width": 600},
        }
        resp = client.post("/api/v1/design-sync/validate-document", json=data)
        assert resp.status_code in (401, 403)

    @pytest.mark.usefixtures("_auth_admin")
    def test_validate_document_oversized_content_length(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/design-sync/validate-document",
            content=b"{}",
            headers={"content-type": "application/json", "content-length": "6000000"},
        )
        assert resp.status_code == 413

    @pytest.mark.usefixtures("_auth_admin")
    def test_validate_document_malformed_content_length(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/design-sync/validate-document",
            content=b'{"version":"1.0","tokens":{},"sections":[],"layout":{"container_width":600}}',
            headers={"content-type": "application/json", "content-length": "not-a-number"},
        )
        # Starlette rejects malformed Content-Length at ASGI layer
        assert resp.status_code == 400

    def test_schema_endpoint_public_access(self, client: TestClient) -> None:
        resp = client.get("/api/v1/design-sync/schema/v1")
        assert resp.status_code == 200
        assert "$schema" in resp.json()

    def test_from_json_empty_dict_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Malformed EmailDesignDocument"):
            EmailDesignDocument.from_json({})


# ── Lossless Capture Tests (Phase 52.5) ──


class TestLosslessCapture:
    """Phase 52.5 — stroke + gradient node_id survive JSON round-trip and bridges."""

    def test_section_and_image_stroke_roundtrip(self) -> None:
        section = DocumentSection(
            id="s1",
            type="content",
            stroke_color="#112233",
            stroke_weight=2.0,
            images=[
                DocumentImage(
                    node_id="i1", node_name="img", stroke_color="#445566", stroke_weight=1.0
                )
            ],
        )
        restored = DocumentSection.from_json(section.to_json())
        assert restored.stroke_color == "#112233"
        assert restored.stroke_weight == 2.0
        assert restored.images[0].stroke_color == "#445566"
        assert restored.images[0].stroke_weight == 1.0

    def test_section_stroke_bridges_email_section(self) -> None:
        section = DocumentSection(
            id="s1",
            type="content",
            stroke_color="#112233",
            stroke_weight=2.0,
            images=[
                DocumentImage(
                    node_id="i1", node_name="img", stroke_color="#445566", stroke_weight=1.0
                )
            ],
        )
        email = section.to_email_section()
        assert email.stroke_color == "#112233"
        assert email.stroke_weight == 2.0
        assert email.images[0].stroke_color == "#445566"
        back = DocumentSection.from_email_section(email)
        assert back.stroke_color == "#112233"
        assert back.stroke_weight == 2.0
        assert back.images[0].stroke_weight == 1.0

    def test_button_padding_roundtrip_and_bridges(self) -> None:
        """Track G · G3 — the four padding fields survive JSON round-trip AND
        both ButtonElement bridges; a designed 0.0 padding is preserved (the
        #327 falsy-zero trap). Missing any one bridge drops padding silently.
        """
        button = DocumentButton(
            node_id="b1",
            text="Shop now",
            border_radius=0.0,
            padding_top=0.0,  # a real designed 0 — must survive, not be dropped
            padding_right=20.0,
            padding_bottom=12.0,
            padding_left=20.0,
        )
        # is-not-None guard (not truthiness) → the real 0.0 is emitted.
        assert button.to_json()["padding_top"] == 0.0
        # JSON round-trip
        restored = DocumentButton.from_json(button.to_json())
        assert (
            restored.padding_top,
            restored.padding_right,
            restored.padding_bottom,
            restored.padding_left,
        ) == (0.0, 20.0, 12.0, 20.0)
        # DocumentButton -> ButtonElement bridge
        be = button.to_button_element()
        assert (be.padding_top, be.padding_right, be.padding_bottom, be.padding_left) == (
            0.0,
            20.0,
            12.0,
            20.0,
        )
        # ButtonElement -> DocumentButton bridge
        back = DocumentButton.from_button_element(be)
        assert (back.padding_top, back.padding_right, back.padding_bottom, back.padding_left) == (
            0.0,
            20.0,
            12.0,
            20.0,
        )

    def test_button_padding_passes_schema(self) -> None:
        """The new flat padding props are declared, so a padded button's
        ``to_json`` validates against the ``additionalProperties: false`` schema.
        """
        doc = _make_document(
            sections=[
                DocumentSection(
                    id="s1",
                    type="hero",
                    buttons=[
                        DocumentButton(
                            node_id="b1",
                            text="Go",
                            padding_top=5.0,
                            padding_right=10.0,
                            padding_bottom=5.0,
                            padding_left=10.0,
                        )
                    ],
                )
            ],
        )
        assert EmailDesignDocument.validate(doc.to_json()) == []

    def test_peel_row_fields_roundtrip_and_bridge(self) -> None:
        """D3 follow-up — x_position + peel_row_id survive JSON and both bridges."""
        section = DocumentSection(
            id="s1",
            type="content",
            x_position=293.0,
            peel_row_id="2833:1641:r0",
        )
        restored = DocumentSection.from_json(section.to_json())
        assert restored.x_position == 293.0
        assert restored.peel_row_id == "2833:1641:r0"
        email = restored.to_email_section()
        assert email.x_position == 293.0
        assert email.peel_row_id == "2833:1641:r0"
        back = DocumentSection.from_email_section(email)
        assert back.x_position == 293.0
        assert back.peel_row_id == "2833:1641:r0"

    def test_gradient_node_id_roundtrip(self) -> None:
        gradient = DocumentGradient(
            name="hero-grad",
            type="linear",
            angle=180.0,
            stops=(
                DocumentGradientStop(hex="#FF0000", position=0.0),
                DocumentGradientStop(hex="#0000FF", position=1.0),
            ),
            fallback_hex="#800080",
            node_id="5:99",
        )
        restored = DocumentGradient.from_json(gradient.to_json())
        assert restored.node_id == "5:99"

    def test_gradient_node_id_bridges_extracted_tokens(self) -> None:
        extracted = ExtractedTokens(
            gradients=[
                ExtractedGradient(
                    name="hero-grad",
                    type="linear",
                    angle=180.0,
                    stops=(("#FF0000", 0.0), ("#0000FF", 1.0)),
                    fallback_hex="#800080",
                    node_id="5:99",
                )
            ]
        )
        doc_tokens = DocumentTokens.from_extracted_tokens(extracted)
        assert doc_tokens.gradients[0].node_id == "5:99"
        assert doc_tokens.to_extracted_tokens().gradients[0].node_id == "5:99"
