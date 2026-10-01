"""Unsubscribe pass over converter output (CE-2 #420, Tasks 6 and 9).

``link_unsubscribe_text`` runs last on every output path (default, MJML,
tree). These tests cover it three ways:

- minimal Figma node trees through the real converter (design-agnostic,
  multi-language);
- the real debug cases, converted with the pass switched off and then run
  through the real function (exact per-case behaviour, comment safety,
  nesting, idempotence);
- a literal-string table for ``has_unsubscribe_phrase``.
"""

from __future__ import annotations

import functools
import re
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from lxml import html as lxml_html

from app.core.config import get_settings
from app.design_sync.converter_service import (
    ConversionResult,
    DesignConverterService,
    MjmlCompileResult,
)
from app.design_sync.email_design_document import EmailDesignDocument
from app.design_sync.protocol import (
    DesignFileStructure,
    DesignNode,
    DesignNodeType,
    ExtractedColor,
    ExtractedTokens,
    ExtractedTypography,
)
from app.design_sync.tests.regression_runner import run_case_conversion
from app.design_sync.unsubscribe_links import has_unsubscribe_phrase, link_unsubscribe_text

_REPO = Path(__file__).resolve().parents[3]
_DEBUG_DIR = _REPO / "data" / "debug"
_CASES = ["5", "6", "7", "8", "9", "10"]
_UNSUB_HREF = "{{unsubscribeUrl}}"
_UNSUB_ANCHOR_RE = re.compile(
    r'<a\b[^>]*href="\{\{unsubscribeUrl\}\}"[^>]*>(.*?)</a\s*>', re.DOTALL
)
_ANCHOR_RE = re.compile(r"<a\b([^>]*)>(.*?)</a\s*>", re.DOTALL | re.IGNORECASE)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_MSO_OPEN = "<!--[if mso]>"


def _unsub_anchors(html: str) -> list[str]:
    return [m.group(0) for m in _UNSUB_ANCHOR_RE.finditer(html)]


def _max_anchor_depth(html: str) -> int:
    """Deepest ``<a>`` nesting outside comments (lxml would repair ``<a><a>``)."""
    depth = deepest = 0
    for tag in re.findall(r"<a\b|</a\s*>", _COMMENT_RE.sub("", html), re.IGNORECASE):
        depth = depth + 1 if tag.lower().startswith("<a") else max(0, depth - 1)
        deepest = max(deepest, depth)
    return deepest


# ── Minimal node trees through convert_document ─────────────────────


def _tokens() -> ExtractedTokens:
    return ExtractedTokens(
        colors=[
            ExtractedColor(name="Background", hex="#FFFFFF"),
            ExtractedColor(name="Text Color", hex="#333333"),
        ],
        typography=[
            ExtractedTypography(
                name="Body", family="Arial", weight="400", size=16.0, line_height=24.0
            ),
        ],
    )


def _document(text: str, *, text_color: str = "#F9F9F9") -> EmailDesignDocument:
    """Hero + one text section holding *text* (mirrors test_convert_document.py).

    The text frame is named "Content Section" on purpose: it matches the
    ``text-block`` component. A frame named "Footer" or "Legal" matches
    ``email-footer``, whose template ships its own ``{{unsubscribeUrl}}``
    anchor, so it would prove nothing about the phrase in the design text.
    """
    hero = DesignNode(
        id="hero",
        name="Hero Section",
        type=DesignNodeType.FRAME,
        width=600,
        height=200,
        children=[
            DesignNode(
                id="hero_heading",
                name="Hero Title",
                type=DesignNodeType.TEXT,
                text_content="Welcome",
                font_size=32.0,
                font_weight=700,
                y=0,
            ),
        ],
    )
    content = DesignNode(
        id="content",
        name="Content Section",
        type=DesignNodeType.FRAME,
        width=600,
        height=60,
        y=200,
        children=[
            DesignNode(
                id="legal_text",
                name="Legal",
                type=DesignNodeType.TEXT,
                text_content=text,
                font_size=12.0,
                text_color=text_color,
                y=0,
            ),
        ],
    )
    page = DesignNode(id="page1", name="Page", type=DesignNodeType.PAGE, children=[hero, content])
    structure = DesignFileStructure(file_name="Test.fig", pages=[page])
    return EmailDesignDocument.from_legacy(structure, _tokens())


class TestMinimalTrees:
    # Matched slugs (observed on the CE-2 spike): hero-block, text-block.

    def test_english_phrase_gets_one_anchor_in_text_colour(self) -> None:
        html = (
            DesignConverterService()
            .convert_document(_document("Privacy Policy | Unsubscribe"))
            .html
        )
        anchors = _unsub_anchors(html)
        assert len(anchors) == 1
        assert anchors[0] == (
            f'<a href="{_UNSUB_HREF}" style="color:#F9F9F9;text-decoration:underline;">'
            "Unsubscribe</a>"
        )

    def test_word_bounded_non_phrase_gets_no_anchor(self) -> None:
        html = DesignConverterService().convert_document(_document("adopt outdoor gear")).html
        assert _UNSUB_HREF not in html
        assert "<a " not in html

    def test_german_phrase_gets_one_anchor(self) -> None:
        html = DesignConverterService().convert_document(_document("Hier abmelden")).html
        anchors = _unsub_anchors(html)
        assert len(anchors) == 1
        assert anchors[0].endswith(">abmelden</a>")


# ── Task 9: MJML and tree output paths ──────────────────────────────


class TestOutputPaths:
    @pytest.mark.asyncio
    async def test_mjml_path_links_phrase(self) -> None:
        """Sidecar mocked as identity (mirrors test_e2e_mjml_pipeline.py): the
        rendered MJML stands in for the compiled HTML, so the phrase reaching
        ``link_unsubscribe_text`` is the real template output, not fixture HTML.
        """
        service = DesignConverterService()

        async def _identity_compile(
            mjml: str, *, target_clients: list[str] | None = None
        ) -> MjmlCompileResult:
            return MjmlCompileResult(html=mjml, errors=[], build_time_ms=0.0)

        with patch.object(
            service, "compile_mjml", new=AsyncMock(side_effect=_identity_compile)
        ) as mock_compile:
            result = await service.convert_document_mjml(_document("Privacy Policy | Unsubscribe"))
        mock_compile.assert_called_once()
        # mj-text carries its colour as an attribute, so the anchor colour is
        # ``inherit`` here; only the count is asserted.
        assert len(_unsub_anchors(result.html)) == 1

    def test_tree_path_links_phrase(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(get_settings().design_sync, "tree_bridge_enabled", True)
        result = DesignConverterService().convert_document(
            _document("Privacy Policy | Unsubscribe"), output_format="tree"
        )
        # The tree compiled (no fallback to the legacy renderer): only the
        # tree branch populates ``result.tree``.
        assert result.tree is not None
        assert len(_unsub_anchors(result.html)) == 1


# ── Real cases: the pass on pre-pass converter output ───────────────


def _identity(html: str) -> str:
    return html


def _convert(case: str) -> ConversionResult:
    result = run_case_conversion(_DEBUG_DIR / case)
    if result is None:
        pytest.skip(f"case {case}: structure.json/tokens.json not present")
    return result


@functools.cache
def _pre_pass_html(case: str) -> str:
    """Converted case HTML with the unsubscribe pass switched off."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.design_sync.converter_service.link_unsubscribe_text", _identity)
        return _convert(case).html


@functools.cache
def _converted_html(case: str) -> str:
    return _convert(case).html


class TestRealCases:
    @pytest.mark.parametrize("case", _CASES)
    def test_pass_is_the_last_step(self, case: str) -> None:
        """The pass is the only difference between pre-pass and shipped output."""
        assert link_unsubscribe_text(_pre_pass_html(case)) == _converted_html(case)

    def test_case_5_unchanged(self) -> None:
        pre = _pre_pass_html("5")
        assert link_unsubscribe_text(pre) == pre

    def test_case_9_gains_one_anchor_in_footer_colour(self) -> None:
        pre = _pre_pass_html("9")
        post = link_unsubscribe_text(pre)
        assert _unsub_anchors(pre) == []
        assert _unsub_anchors(post) == [
            f'<a href="{_UNSUB_HREF}" style="color:#F9F9F9;text-decoration:underline;">'
            "Unsubscribe</a>"
        ]

    def test_case_7_design_anchor_repointed_nothing_wrapped(self) -> None:
        pre = _pre_pass_html("7")
        post = link_unsubscribe_text(pre)
        design = [
            (attrs, inner)
            for attrs, inner in _ANCHOR_RE.findall(pre)
            if inner == "Unsubscribe" and _UNSUB_HREF not in attrs
        ]
        assert len(design) == 1  # Lego's own footer link (design URL)
        design_href = re.search(r'href="([^"]*)"', design[0][0])
        assert design_href is not None
        assert pre.count("<a ") == post.count("<a ")  # nothing wrapped
        assert len(_unsub_anchors(pre)) == 1  # email-footer template link
        assert len(_unsub_anchors(post)) == 2
        # Sibling design links (Privacy Policy, Cookies Policy, ...) keep the URL.
        assert post.count(design_href.group(1)) == pre.count(design_href.group(1)) - 1
        wrap_style = 'text-decoration:underline;">'
        assert post.count(wrap_style) == pre.count(wrap_style)

    @pytest.mark.parametrize("case", _CASES)
    def test_comments_byte_identical(self, case: str) -> None:
        pre = _pre_pass_html(case)
        post = link_unsubscribe_text(pre)
        assert _COMMENT_RE.findall(post) == _COMMENT_RE.findall(pre)

    @pytest.mark.parametrize("case", _CASES)
    def test_no_nested_anchors(self, case: str) -> None:
        post = link_unsubscribe_text(_pre_pass_html(case))
        assert _max_anchor_depth(post) == 1

    def test_nested_anchor_detector_can_fail(self) -> None:
        """Guard for the check above: nesting a real anchor is detected."""
        post = link_unsubscribe_text(_pre_pass_html("9"))
        anchor = _unsub_anchors(post)[0]
        nested = post.replace(anchor, anchor.replace(">Unsubscribe<", f">{anchor}<"), 1)
        assert _max_anchor_depth(nested) == 2

    @pytest.mark.parametrize("case", _CASES)
    def test_output_parses_with_lxml(self, case: str) -> None:
        post = link_unsubscribe_text(_pre_pass_html(case))
        doc = lxml_html.document_fromstring(post)
        assert doc.find("body") is not None
        assert len(doc.xpath("//a")) == len(re.findall(r"<a\b", _COMMENT_RE.sub("", post)))

    @pytest.mark.parametrize("case", _CASES)
    def test_idempotent(self, case: str) -> None:
        once = link_unsubscribe_text(_pre_pass_html(case))
        assert link_unsubscribe_text(once) == once

    def test_repoint_skips_anchor_inside_mso_comment(self) -> None:
        """Step 1 never edits comments: Lego's design anchor copied into one of
        its own MSO blocks keeps its design href there."""
        pre = _pre_pass_html("7")
        design = next(
            m.group(0)
            for m in _ANCHOR_RE.finditer(pre)
            if m.group(2) == "Unsubscribe" and _UNSUB_HREF not in m.group(1)
        )
        assert _MSO_OPEN in pre
        mutated = pre.replace(_MSO_OPEN, _MSO_OPEN + design, 1)
        post = link_unsubscribe_text(mutated)
        assert _COMMENT_RE.findall(post) == _COMMENT_RE.findall(mutated)
        assert design not in _COMMENT_RE.sub("", post)  # the visible one moved

    def test_wrap_skips_phrase_inside_mso_comment(self) -> None:
        """Step 3 never edits comments: slate's footer cell copied into one of
        its own MSO blocks in ``<body>`` stays unlinked there (the first MSO
        block sits in ``<head>``, which the walk skips anyway)."""
        pre = _pre_pass_html("9")
        cell = re.search(r"<td\b[^>]*>\s*Unsubscribe\s*</td>", pre)
        assert cell is not None
        at = pre.find(_MSO_OPEN, pre.find("<body"))
        assert at > pre.find("<body") > 0
        k = at + len(_MSO_OPEN)
        mutated = pre[:k] + cell.group(0) + pre[k:]
        post = link_unsubscribe_text(mutated)
        assert _COMMENT_RE.findall(post) == _COMMENT_RE.findall(mutated)
        assert len(_unsub_anchors(post)) == 1

    def test_repoint_anchor_with_mso_comments_inside(self) -> None:
        """The ``button`` seed puts MSO comments inside its anchor; an
        "Unsubscribe" label there is still repointed, comments untouched."""
        seed = (_REPO / "email-templates" / "components" / "button.html").read_text()
        label = '<span data-slot="cta_text">Button</span>'
        assert label in seed
        mutated = seed.replace(label, '<span data-slot="cta_text">Unsubscribe</span>')
        post = link_unsubscribe_text(mutated)
        assert 'href="https://example.com/link"' not in post
        assert f'data-slot="cta_url" href="{_UNSUB_HREF}"' in post
        assert _COMMENT_RE.findall(post) == _COMMENT_RE.findall(mutated)
        assert post.count("<a ") == mutated.count("<a ")  # nothing wrapped

    def test_merge_tag_href_is_not_repointed(self) -> None:
        """Case 5's footer anchor pointed at its other ESP merge tag keeps it."""
        pre = _pre_pass_html("5")
        assert "{{preferencesUrl}}" in pre
        mutated = pre.replace(f'href="{_UNSUB_HREF}"', 'href="{{preferencesUrl}}"')
        assert _UNSUB_HREF not in mutated
        assert link_unsubscribe_text(mutated) == mutated

    def test_every_phrase_in_a_text_node_is_wrapped(self) -> None:
        """Slate's footer cell with its phrase doubled gains two anchors."""
        pre = _pre_pass_html("9")
        cell = re.search(r"<td\b[^>]*>\s*Unsubscribe\s*</td>", pre)
        assert cell is not None
        doubled = cell.group(0).replace("Unsubscribe", "Unsubscribe Unsubscribe")
        post = link_unsubscribe_text(pre.replace(cell.group(0), doubled, 1))
        assert len(_unsub_anchors(post)) == 2

    def test_colour_inherit_without_enclosing_colour(self) -> None:
        """Slate's footer text without its cell has no colour to copy."""
        cell = re.search(r"<td\b[^>]*>(\s*Unsubscribe\s*)</td>", _pre_pass_html("9"))
        assert cell is not None
        out = link_unsubscribe_text(cell.group(1))
        assert f'<a href="{_UNSUB_HREF}" style="color:inherit;text-decoration:underline;">' in out


# ── Phrase literal table (plan E8; privacy rows: PR #450 review M1) ──

_MATCHES = [
    "Unsubscribe",
    "You can unsubscribe here.",
    "Opt out",
    "opt-out",
    "optout",
    "Opt out of these emails",
    "opt-out of marketing emails",
    # "Opt out of … emails" is an unsubscribe even with a privacy word in it.
    "Opt out of all emails",
    "Opt out of future mailings",
    "opt out of the newsletter",
    "Opt-out of data emails",
    "Opt out of sharing emails",
    "Opt out of ads emails",
    "opt out of tracking emails",
    "Opt out of all promotional email",
    "Opt out of personalised emails",
    "Opt out of data and promotional emails",
    "Opt out of the sale emails",
    # A privacy link in a sibling footer segment does not disqualify the opt-out.
    "Privacy Policy | Opt out",
    "Cookies Policy | Opt out",
    "Do Not Sell My Personal Information\nOpt out",
    "Hier abmelden",
    "Newsletter abbestellen",
    "Se désabonner",
    "se desinscrire",
    "désinscription",
    "Darse de baja",
    "date de baja",
    "Cancelar la suscripción",
    "disiscriviti",
    "Annulla l\u2019iscrizione",
    "annulla l'iscrizione",
    "Afmelden",
    "uitschrijven",
    "descadastrar",
    "cancelar a inscrição",
    "avregistrera",
    "avsluta prenumerationen",
    "afmeld",
    "wypisz się",
]

_NON_MATCHES = [
    "adopt outdoor gear",
    "subscribe now",
    "Subscribe",
    "Manage Preferences",
    # Privacy opt-outs (review M1): not unsubscribe links.
    "Do Not Sell or Share / Opt-out of sale",
    "Opt out of the sale of my personal information",
    "Opt out of targeted advertising",
    "Cookie opt-out",
    "https://brand.com/opt-out-of-sale",
    "Do Not Sell My Personal Information - Opt Out",
    "Do not sell my info - opt out",
    "Your Privacy Choices (opt out)",
    "Opt-Out Preference Signal",
    "Ad Choices opt out",
    "GPC opt out",
    "Manage cookie preferences opt out",
    "Opt-out of cookies",
    "Cookies opt out",
    "Opt out of sale/share",
    "Opt out of interest based ads",
    "Opt out of analytics",
    "Opt out of tracking",
    "Opt out of third-party sharing",
    "Opt out of profiling",
    "Opt out of data collection",
    "Opt out of cross-context behavioral advertising",
    "Opt out of sharing my email address",
]


@pytest.mark.parametrize("text", _MATCHES)
def test_phrase_matches(text: str) -> None:
    assert has_unsubscribe_phrase(text)


@pytest.mark.parametrize("text", _NON_MATCHES)
def test_phrase_rejects(text: str) -> None:
    assert not has_unsubscribe_phrase(text)


def test_privacy_opt_out_link_keeps_its_href() -> None:
    """Review M1, verbatim: a CCPA link is neither repointed nor wrapped."""
    html = '<td><a href="https://brand.com/ccpa">Do Not Sell or Share / Opt-out of sale</a></td>'
    assert link_unsubscribe_text(html) == html


def test_privacy_opt_out_does_not_block_wrapping() -> None:
    """A CCPA link does not count as the unsubscribe link, so the bare phrase
    in the same footer is still wrapped; bare privacy text is not."""
    ccpa = '<a href="https://brand.com/ccpa">Do Not Sell or Share / Opt-out of sale</a>'
    html = f"<td>{ccpa} | Cookie opt-out | Unsubscribe</td>"
    out = link_unsubscribe_text(html)
    assert ccpa in out
    assert _unsub_anchors(out) == [
        f'<a href="{_UNSUB_HREF}" style="color:inherit;text-decoration:underline;">Unsubscribe</a>'
    ]


def test_canonical_ccpa_text_is_not_wrapped() -> None:
    """Review round 2: the standard CCPA wording as bare footer text gets no
    unsubscribe anchor, while the real phrase in the next segment does."""
    html = "<td>Do Not Sell My Personal Information - Opt Out | Unsubscribe</td>"
    out = link_unsubscribe_text(html)
    assert _unsub_anchors(out) == [
        f'<a href="{_UNSUB_HREF}" style="color:inherit;text-decoration:underline;">Unsubscribe</a>'
    ]
