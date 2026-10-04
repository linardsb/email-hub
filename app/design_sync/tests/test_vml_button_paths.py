"""CE-11 (#429): every converter CTA carries a design-driven VML twin.

Matcher paths (text-block composite, column CTA rows), the template path (every
seed with a CTA ``data-slot``) and an invariant over the real corpus. Node trees
are minimal Figma input built here (generality rule).
"""

from __future__ import annotations

import functools
import html
import re
from collections.abc import Callable
from pathlib import Path

import pytest

from app.design_sync import component_renderer
from app.design_sync.component_matcher import (
    ComponentMatch,
    SlotFill,
    TokenOverride,
    _build_column_fill_html,
    match_section,
)
from app.design_sync.component_renderer import ComponentRenderer
from app.design_sync.figma.layout_analyzer import (
    ButtonElement,
    ColumnGroup,
    EmailSection,
    EmailSectionType,
)
from app.design_sync.frame_rules import CornerRadiusSpec
from app.design_sync.protocol import DesignNode, DesignNodeType
from app.design_sync.tests.content_checks import strip_mso
from app.design_sync.tests.regression_runner import discover_cases, run_case_conversion
from app.design_sync.tests.test_button_icon_exclusion import _mj_single, _text
from app.qa_engine.mso_parser import validate_mso_conditionals

# ── Pairing and view helpers ──

# The pipeline's formatter may put whitespace between the two conditionals.
PAIR_RE = re.compile(
    r"<!--\[if mso\]>\s*(<v:roundrect\b.*?</v:roundrect>)\s*<!\[endif\]-->\s*"
    r"<!--\[if !mso\]><!-->(.*?)<!--<!\[endif\]-->",
    re.DOTALL,
)
_NON_MSO_RE = re.compile(r"<!--\[if\s+!mso\]><!-->(.*?)<!--<!\[endif\]-->", re.DOTALL)
_MSO_RE = re.compile(r"<!--\[if[^\]]*\]>(.*?)<!\[endif\]-->", re.DOTALL)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def _text_of(fragment: str) -> str:
    return " ".join(html.unescape(_TAG_RE.sub(" ", fragment)).split())


def outlook_view(markup: str) -> str:
    """What classic Outlook parses: ``!mso`` blocks dropped, ``mso`` blocks opened."""
    return _MSO_RE.sub(r"\1", _NON_MSO_RE.sub("", markup))


def browser_view(markup: str) -> str:
    """What every other client parses: ``!mso`` blocks opened, ``mso`` blocks dropped."""
    return _MSO_RE.sub("", _NON_MSO_RE.sub(r"\1", markup))


def balanced(markup: str, tags: tuple[str, ...] = ("table", "tr", "td", "a", "center")) -> bool:
    """True when every listed tag opens and closes in order (comments ignored)."""
    body = _COMMENT_RE.sub("", markup)
    for tag in tags:
        depth = 0
        for m in re.finditer(rf"<(/?){tag}\b[^>]*>", body, flags=re.IGNORECASE):
            depth += -1 if m.group(1) else 1
            if depth < 0:
                return False
        if depth:
            return False
    return True


def _roundrect_tags(markup: str) -> list[str]:
    return re.findall(r"<v:roundrect\b[^>]*>", markup)


def assert_paired(markup: str) -> int:
    """Each VML's href and label equal its twin anchor's; returns the pair count."""
    pairs = PAIR_RE.findall(markup)
    assert len(pairs) == len(_roundrect_tags(markup)), "a v:roundrect sits outside a pair"
    for roundrect, twin in pairs:
        anchor = re.search(r'<a\b[^>]*\bhref="([^"]*)"[^>]*>(.*?)</a>', twin, re.DOTALL)
        assert anchor is not None, twin
        vml_href = re.search(r'\bhref="([^"]*)"', roundrect)
        center = re.search(r"<center[^>]*>(.*?)</center>", roundrect, re.DOTALL)
        assert vml_href is not None
        assert center is not None
        assert html.unescape(vml_href.group(1)) == html.unescape(anchor.group(1))
        assert _text_of(center.group(1)) == _text_of(anchor.group(2))
    return len(pairs)


def _attr(tag: str, name: str) -> str | None:
    m = re.search(rf'\b{name}="([^"]*)"', tag)
    return m.group(1) if m else None


def _center_color(roundrect: str) -> str | None:
    m = re.search(r'<center style="color:([^;"]+)', roundrect)
    return m.group(1) if m else None


@pytest.fixture(scope="module")
def renderer() -> ComponentRenderer:
    r = ComponentRenderer()
    r.load()
    return r


def _render(renderer: ComponentRenderer, match: ComponentMatch) -> str:
    return renderer.render_section(match).html


# ── Figma input ──


def _button_node(
    node_id: str,
    label: str,
    *,
    fill: str | None = "#123456",
    stroke: str | None = None,
    weight: float | None = None,
    radius: float | None = 8,
    radii: tuple[float, ...] | None = None,
    width: float = 200,
    height: float = 48,
    text_color: str | None = "#FFFFFF",
) -> DesignNode:
    label_node = DesignNode(
        id=f"{node_id}:label",
        name="label",
        type=DesignNodeType.TEXT,
        text_content=label,
        font_size=16.0,
        text_color=text_color,
        width=width - 48,
        height=24,
    )
    return DesignNode(
        id=node_id,
        name="mj-button",
        type=DesignNodeType.FRAME,
        fill_color=fill,
        stroke_color=stroke,
        stroke_weight=weight,
        corner_radius=radius,
        corner_radii=radii,
        width=width,
        height=height,
        hyperlink=f"https://example.com/{node_id}",
        children=[label_node],
    )


def _text_block_html(renderer: ComponentRenderer, *buttons: DesignNode) -> str:
    section = _mj_single(
        [
            _text("h", "A designed heading", font_size=28),
            _text("t", "A paragraph of body copy above the buttons."),
            *buttons,
        ]
    )
    match = match_section(section, 0)
    assert match.component_slug == "text-block"
    return _render(renderer, match)


def _column_button(**kw: object) -> ButtonElement:
    base: dict[str, object] = {
        "node_id": "cb",
        "text": "Read more",
        "width": 200.0,
        "height": 48.0,
        "fill_color": "#123456",
        "text_color": "#FFFFFF",
        "url": "https://example.com/col",
        "border_radius": 6.0,
    }
    base.update(kw)
    return ButtonElement(**base)  # type: ignore[arg-type]


# ── Matcher paths ──


class TestMatcherPaths:
    def test_matcher_text_block_filled_button(self, renderer: ComponentRenderer) -> None:
        out = _text_block_html(renderer, _button_node("b1", "Shop the sale", radius=12))
        assert assert_paired(out) == 1
        tag = _roundrect_tags(out)[0]
        assert _attr(tag, "fillcolor") == "#123456"
        assert _attr(tag, "arcsize") == "25%"  # floor(12 / 48 * 100)
        assert 'stroke="f"' in tag

    def test_matcher_text_block_outlined_button_has_no_invented_fill(
        self, renderer: ComponentRenderer
    ) -> None:
        out = _text_block_html(
            renderer,
            _button_node("b1", "Primary action"),
            _button_node(
                "b2", "Outlined action", fill=None, stroke="#FE5219", weight=2, text_color="#FE5219"
            ),
        )
        assert assert_paired(out) == 2
        primary, outlined = PAIR_RE.findall(out)
        tag = _roundrect_tags(outlined[0])[0]
        assert 'fill="f"' in tag
        assert "fillcolor" not in tag
        assert _attr(tag, "strokecolor") == "#FE5219"
        assert _attr(tag, "strokeweight") == "2px"
        anchor_color = re.search(r"(?<!-)color:(#[0-9a-fA-F]{3,6})", outlined[1])
        assert anchor_color is not None
        assert _center_color(outlined[0]) == anchor_color.group(1)
        assert _attr(_roundrect_tags(primary[0])[0], "fillcolor") == "#123456"
        for t in _roundrect_tags(out):
            assert "#0066cc" not in t

    def test_matcher_column_button_wrapped(self) -> None:
        group = ColumnGroup(
            column_idx=1,
            node_id="c1",
            node_name="Column 1",
            buttons=[_column_button()],
            width=280.0,
        )
        out = _build_column_fill_html(group)
        assert assert_paired(out) == 1
        style = _attr(_roundrect_tags(out)[0], "style")
        assert style == "height:48px;v-text-anchor:middle;width:200px;"

    def test_matcher_column_fill_button_clamped_to_column(self) -> None:
        group = ColumnGroup(
            column_idx=1,
            node_id="c1",
            node_name="Column 1",
            buttons=[_column_button(width=400.0)],
            width=280.0,
        )
        out = _build_column_fill_html(group)
        assert "width:280px;" in (_attr(_roundrect_tags(out)[0], "style") or "")

    def test_matcher_stroke_keeps_design_box(self, renderer: ComponentRenderer) -> None:
        out = _text_block_html(
            renderer,
            _button_node("b1", "Bordered", stroke="#000000", weight=2, width=185, height=56),
        )
        assert _attr(_roundrect_tags(out)[0], "style") == (
            "height:56px;v-text-anchor:middle;width:185px;"
        )

    def test_matcher_per_corner_radius_uses_largest(self) -> None:
        group = ColumnGroup(
            column_idx=1,
            node_id="c1",
            node_name="Column 1",
            buttons=[
                _column_button(
                    width=576.0,
                    height=48.0,
                    corner_radius_spec=CornerRadiusSpec(scalar=None, per_corner=(0, 12, 12, 0)),
                )
            ],
            width=600.0,
        )
        out = _build_column_fill_html(group)
        assert _attr(_roundrect_tags(out)[0], "arcsize") == "25%"


def test_text_block_section_has_buttons() -> None:
    """Guard: the Figma tree above yields the button the VML tests rely on."""
    section: EmailSection = _mj_single([_text("t", "Body copy"), _button_node("b1", "Go")])
    assert [b.text for b in section.buttons] == ["Go"]


# ── Template path ──

_CTA_URL_SLOTS = ("cta_url", "primary_url", "secondary_url", "primary_cta_url", "secondary_cta_url")
_CTA_TEXT_SLOTS = (
    "cta_text",
    "primary_text",
    "secondary_text",
    "primary_cta_text",
    "secondary_cta_text",
)
_CTA_SLOT_RE = re.compile(rf'data-slot="({"|".join(_CTA_URL_SLOTS)})"')
_CTA_ANCHOR_RE = re.compile(
    rf'<a\b[^>]*data-slot="(?:{"|".join(_CTA_URL_SLOTS)})"[^>]*>(.*?)</a>', re.DOTALL
)

_PRIMARY = ButtonElement(
    node_id="p1",
    text="Primary Go",
    width=200,
    height=44,
    fill_color="#123456",
    text_color="#FFFFFF",
    border_radius=22,
    url="https://a.example/1",
)
_SECONDARY = ButtonElement(
    node_id="p2",
    text="Second Go",
    width=180,
    height=44,
    text_color="#654321",
    stroke_color="#654321",
    stroke_weight=2,
    border_radius=6,
    url="https://a.example/2",
)


def _cta_slugs() -> list[str]:
    r = ComponentRenderer()
    r.load()
    return sorted(slug for slug, tpl in r._templates.items() if _CTA_SLOT_RE.search(tpl))


def _template_match(
    renderer: ComponentRenderer,
    slug: str,
    buttons: list[ButtonElement],
    *,
    overrides: list[TokenOverride] | None = None,
) -> ComponentMatch:
    """Fill every CTA text/url slot of *slug*: ``secondary*`` from ``_SECONDARY``."""
    fills: list[SlotFill] = []
    for slot in dict.fromkeys(re.findall(r'data-slot="([a-z_]+)"', renderer._templates[slug])):
        btn = _SECONDARY if slot.startswith("secondary") else _PRIMARY
        if slot in _CTA_URL_SLOTS:
            fills.append(SlotFill(slot, btn.url or "", slot_type="cta"))
        elif slot in _CTA_TEXT_SLOTS:
            fills.append(SlotFill(slot, btn.text))
    section = EmailSection(
        section_type=EmailSectionType.CTA, node_id="s", node_name="s", buttons=buttons
    )
    return ComponentMatch(
        section_idx=0,
        section=section,
        component_slug=slug,
        slot_fills=fills,
        token_overrides=overrides or [],
    )


def _filled_ctas(markup: str) -> int:
    return sum(1 for m in _CTA_ANCHOR_RE.finditer(browser_view(markup)) if _text_of(m.group(1)))


def _without_vml(
    renderer: ComponentRenderer, match: ComponentMatch, monkeypatch: pytest.MonkeyPatch
) -> str:
    with monkeypatch.context() as m:
        m.setattr(
            component_renderer.ComponentRenderer,
            "_apply_vml_buttons",
            _identity_vml_step,
        )
        return _render(renderer, match)


def _identity_vml_step(_self: ComponentRenderer, html_str: str, _match: ComponentMatch) -> str:
    return html_str


def _twins(markup: str) -> list[str]:
    return [twin.strip() for _, twin in PAIR_RE.findall(markup)]


class TestTemplatePath:
    @pytest.mark.parametrize("slug", _cta_slugs())
    def test_template_census(
        self, renderer: ComponentRenderer, slug: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        match = _template_match(renderer, slug, [_PRIMARY, _SECONDARY])
        on = _render(renderer, match)
        off = _without_vml(renderer, match, monkeypatch)
        # Image-only CTA anchors (video play buttons) have no label: no VML.
        assert len(_roundrect_tags(on)) == _filled_ctas(off)
        assert_paired(on)
        assert "Shop Now" not in on
        for view in (outlook_view, browser_view):
            if balanced(view(off)):
                assert balanced(view(on)), view.__name__
        assert " ".join(browser_view(on).split()) == " ".join(browser_view(off).split())

    def test_template_census_covers_known_ctas(self) -> None:
        slugs = _cta_slugs()
        assert len(slugs) >= 42
        for slug in ("survey-scale", "video-placeholder-inline", "video-placeholder-overlay"):
            assert slug in slugs

    @pytest.mark.parametrize(
        ("slug", "kind"),
        [
            ("cta-button", "table"),
            ("button", "table"),
            ("button-filled", "table"),
            ("cta", "table"),
            ("cta-pair", "table"),
            ("hero-2cta", "table"),
            ("event-card", "a"),
            ("hero-block", "a"),
            ("article-card", "a"),
            ("product-card", "a"),
        ],
    )
    def test_template_chrome_kind(self, renderer: ComponentRenderer, slug: str, kind: str) -> None:
        out = _render(renderer, _template_match(renderer, slug, [_PRIMARY, _SECONDARY]))
        twins = _twins(out)
        assert twins
        for twin in twins:
            assert twin.startswith(f"<{kind}"), twin[:80]

    def test_template_cta_pair_per_button_values(self, renderer: ComponentRenderer) -> None:
        out = _render(renderer, _template_match(renderer, "cta-pair", [_PRIMARY, _SECONDARY]))
        first, second = _roundrect_tags(out)
        assert _attr(first, "fillcolor") == "#123456"
        # No design stroke: the stroke falls back to the twin's own border (D3).
        primary_twin = _twins(out)[0]
        border = re.search(r"border:\s*(\d+)px\s+solid\s+(#[0-9a-fA-F]{3,6})", primary_twin)
        assert border is not None
        assert _attr(first, "strokecolor") == border.group(2)
        assert 'fill="f"' in second
        assert _attr(second, "strokecolor") == "#654321"
        assert _attr(second, "strokeweight") == "2px"
        assert _attr(first, "href") == "https://a.example/1"
        assert _attr(second, "href") == "https://a.example/2"

    def test_template_button_twin_has_no_nested_conditional(
        self, renderer: ComponentRenderer
    ) -> None:
        out = _render(renderer, _template_match(renderer, "button", [_PRIMARY]))
        twins = _twins(out)
        assert len(twins) == 1
        assert "<!--[if" not in twins[0]

    def test_template_pruned_cta_gets_no_vml(self, renderer: ComponentRenderer) -> None:
        section = EmailSection(
            section_type=EmailSectionType.CTA, node_id="s", node_name="s", buttons=[_PRIMARY]
        )
        match = ComponentMatch(
            section_idx=0,
            section=section,
            component_slug="cta-button",
            slot_fills=[],
            token_overrides=[],
        )
        out = _render(renderer, match)
        assert "v:roundrect" not in out
        assert "Shop Now" not in out

    def test_template_no_design_button_warns(
        self, renderer: ComponentRenderer, capsys: pytest.CaptureFixture[str]
    ) -> None:
        out = _render(renderer, _template_match(renderer, "cta-button", []))
        assert "v:roundrect" not in out
        assert _filled_ctas(out) == 1
        assert "design_sync.vml_button_skipped" in capsys.readouterr().out

    def test_template_cta_override_cannot_repaint_matcher_vml(
        self, renderer: ComponentRenderer
    ) -> None:
        section = _mj_single(
            [_text("t", "Body copy above the button."), _button_node("b1", "Go there")]
        )
        match = match_section(section, 0)
        assert match.component_slug == "text-block"
        repainted = ComponentMatch(
            section_idx=match.section_idx,
            section=match.section,
            component_slug=match.component_slug,
            slot_fills=match.slot_fills,
            token_overrides=[
                *match.token_overrides,
                TokenOverride("color", "_cta", "#00ff00"),
                TokenOverride("background-color", "_cta", "#00ff00"),
                TokenOverride("border-radius", "_cta", "1px"),
            ],
        )
        tag = _roundrect_tags(_render(renderer, repainted))[0]
        out = _render(renderer, repainted)
        assert _center_color(out) == "#FFFFFF"
        assert _attr(tag, "fillcolor") == "#123456"
        assert _attr(tag, "arcsize") == "16%"  # floor(8 / 48 * 100)

    def test_template_routed_from_figma_tree(self, renderer: ComponentRenderer) -> None:
        section = _mj_single([_button_node("b1", "Book a table", radius=24, height=48)])
        match = match_section(section, 0)
        assert match.component_slug == "cta-button"
        out = _render(renderer, match)
        assert assert_paired(out) == 1
        tag = _roundrect_tags(out)[0]
        assert _attr(tag, "arcsize") == "50%"
        assert _attr(tag, "fillcolor") == "#123456"
        assert _attr(tag, "href") == "https://example.com/b1"
        assert "Book a table</center>" in out


# ── PR #471 review hardening: real cta-button seed, one mutation each ──

_CTA_BTN_TABLE_RE = re.compile(r'<table[^>]*class="cta-btn".*?</table>', re.DOTALL)


def _mutated_cta_button(
    renderer: ComponentRenderer, monkeypatch: pytest.MonkeyPatch, mutate: Callable[[str], str]
) -> ComponentMatch:
    """Swap the loaded cta-button template for ``mutate(template)`` (test-scoped)."""
    template = renderer._templates["cta-button"]
    mutated = mutate(template)
    assert mutated != template
    monkeypatch.setitem(renderer._templates, "cta-button", mutated)
    return _template_match(renderer, "cta-button", [_PRIMARY])


def _normalised(markup: str) -> str:
    return " ".join(markup.split())


def _conditional_issues(fragment: str) -> list[str]:
    """MSO issues bar the namespace ones (an ``<html>`` check; a section has none)."""
    issues = validate_mso_conditionals(fragment).issues
    return [i.message for i in issues if i.category != "namespace"]


class TestReviewHardening:
    def test_non_mso_block_in_chrome_stays_browser_visible(
        self, renderer: ComponentRenderer, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # F2: the review's input, <!--[if !mso]><!-->X<!--<![endif]-->, inside CTA chrome.
        match = _mutated_cta_button(
            renderer,
            monkeypatch,
            lambda t: t.replace(
                "</span>\n            </a>",
                "</span><!--[if !mso]><!--><span>X</span><!--<![endif]-->\n            </a>",
            ),
        )
        on = _render(renderer, match)
        off = _without_vml(renderer, match, monkeypatch)
        assert _normalised(browser_view(on)) == _normalised(browser_view(off))
        assert "<span>X</span>" in browser_view(on)
        outlook = outlook_view(on)
        assert "<a" not in outlook
        assert outlook.count("Primary Go") == 1
        assert _conditional_issues(on) == []

    def test_second_pass_does_not_rewrap(
        self, renderer: ComponentRenderer, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # F3 (idempotence): an anchor already inside a VML !mso wrapper is skipped.
        match = _template_match(renderer, "cta-button", [_PRIMARY])
        filled = renderer._fill_slots(
            renderer._templates["cta-button"], match.slot_fills, "cta-button"
        )
        once = renderer._apply_vml_buttons(filled, match)
        assert len(_roundrect_tags(once)) == 1
        assert renderer._apply_vml_buttons(once, match) == once

    def test_cta_in_ghost_cell_keeps_conditionals_intact(
        self, renderer: ComponentRenderer, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # F3 (comment table tags): a CTA directly inside an MSO ghost cell.
        def ghost(t: str) -> str:
            btn = _CTA_BTN_TABLE_RE.search(t)
            assert btn is not None
            anchor = re.search(r"<a\b.*?</a>", btn.group(0), re.DOTALL)
            assert anchor is not None
            cell = (
                '<!--[if mso]><table role="presentation"><tr><td><![endif]-->'
                f"{anchor.group(0)}"
                "<!--[if mso]></td></tr></table><![endif]-->"
            )
            return t[: btn.start()] + cell + t[btn.end() :]

        match = _mutated_cta_button(renderer, monkeypatch, ghost)
        on = _render(renderer, match)
        assert assert_paired(on) == 1
        assert _twins(on)[0].startswith("<a")
        assert _conditional_issues(on) == []
        assert balanced(outlook_view(on))

    def test_spaced_table_close_tag_kept_whole(
        self, renderer: ComponentRenderer, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # F3 (end offset): the chrome table closes with ``</table >``.
        def spaced(t: str) -> str:
            btn = _CTA_BTN_TABLE_RE.search(t)
            assert btn is not None
            return t[: btn.end() - len("</table>")] + "</table >" + t[btn.end() :]

        match = _mutated_cta_button(renderer, monkeypatch, spaced)
        on = _render(renderer, match)
        twin = _twins(on)[0]
        assert twin.startswith("<table")
        assert twin.endswith("</table >")
        assert "<!--<![endif]-->>" not in on

    def test_mso_width_clamp_spares_vml_template_path(self) -> None:
        # F4: a 600px design button in a 640 container stays 600px in Outlook.
        wide = ComponentRenderer(container_width=640)
        wide.load()
        button = ButtonElement(
            node_id="w1",
            text="Wide Go",
            width=600,
            height=44,
            fill_color="#123456",
            text_color="#FFFFFF",
            border_radius=8,
            url="https://a.example/w",
        )
        out = _render(wide, _template_match(wide, "cta-button", [button]))
        style = _attr(_roundrect_tags(out)[0], "style") or ""
        assert "width:600px;" in style

    def test_mso_width_clamp_spares_vml_matcher_path(self) -> None:
        # F4 on the matcher path: VML arrives in a slot fill, before step 3.
        wide = ComponentRenderer(container_width=640)
        wide.load()
        out = _text_block_html(wide, _button_node("b1", "Wide button", width=600))
        style = _attr(_roundrect_tags(out)[0], "style") or ""
        assert "width:600px;" in style
        # The ghost table in the same section is still clamped to the container.
        assert 'width="640"' in out
        assert 'width="600"' not in out


# ── Corpus invariant (local only: structure.json is gitignored) ──

_DEBUG_DIR = Path(__file__).resolve().parents[3] / "data" / "debug"
_CORPUS = [p.name for p in discover_cases(_DEBUG_DIR) if (p / "structure.json").exists()]
_STYLE_RE = re.compile(r'\bstyle="([^"]*)"')


@functools.cache
def _corpus_html(case: str) -> str | None:
    result = run_case_conversion(_DEBUG_DIR / case)
    return None if result is None else result.html


def _corpus_cta_anchors(markup: str) -> int:
    """CE-2 CTA predicate over the non-MSO view, plus CTA ``data-slot`` anchors."""
    count = 0
    for m in re.finditer(r"<a\b([^>]*)>(.*?)</a>", strip_mso(markup), re.DOTALL):
        style = _STYLE_RE.search(m.group(1))
        css = style.group(1).replace(" ", "") if style else ""
        is_button = "display:inline-block" in css and "padding" in css
        if (is_button or _CTA_SLOT_RE.search(m.group(1))) and _text_of(m.group(2)):
            count += 1
    return count


@pytest.mark.skipif(not _CORPUS, reason="data/debug fixtures not present")
@pytest.mark.parametrize("case", _CORPUS)
def test_corpus_every_cta_has_a_paired_vml(case: str) -> None:
    out = _corpus_html(case)
    if out is None:
        pytest.skip(f"{case}: missing converter inputs")
    ctas = _corpus_cta_anchors(out)
    assert ctas > 0
    assert len(_roundrect_tags(out)) == ctas
    assert assert_paired(out) == ctas
    assert validate_mso_conditionals(out).is_valid
    # The cta-button seed literal never reaches Outlook (no design button says it).
    assert not re.search(r"<center[^>]*>\s*Shop Now\s*</center>", out)
    assert balanced(outlook_view(out))
    assert balanced(browser_view(out))
    for tag in _roundrect_tags(out):
        assert "#0066cc" not in tag.lower()
