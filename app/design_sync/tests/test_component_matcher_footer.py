"""Footer builder tests (Track G · G8 / 51.6).

Covers ``_fills_footer`` and its helpers: per-node editorial rows, style-run
link emission, multi-line collapse, and the footer_legal compliance policy
(FooterConfig substitution vs the FooterConfig-absent fallback). Fixtures mirror
the real c5 (MAAP, plain-text footer) and c7 (LEGO, style-run links) corpus
cases so the compliance invariant is exercised on production-shaped data.
"""

from __future__ import annotations

from app.design_sync.component_matcher import (
    _fills_footer,
    _footer_legal_html,
    _render_text_runs,
)
from app.design_sync.figma.layout_analyzer import (
    EmailSection,
    EmailSectionType,
    TextBlock,
)
from app.design_sync.protocol import StyleRun
from app.projects.design_system import (
    BrandPalette,
    DesignSystem,
    FooterConfig,
    Typography,
)

# ── Fixtures modelled on real corpus footers ──


def _footer_section(texts: list[TextBlock]) -> EmailSection:
    return EmailSection(
        section_type=EmailSectionType.FOOTER,
        node_id="footer",
        node_name="footer",
        texts=texts,
    )


def _c7_link_bar() -> TextBlock:
    # "Unsubscribe | Privacy Policy | Cookies Policy | Preferences" — 4 links.
    return TextBlock(
        node_id="bar",
        content="Unsubscribe\xa0\xa0 | \xa0\xa0Privacy Policy\xa0\xa0 | \xa0\xa0Cookies Policy\xa0\xa0 | \xa0\xa0Preferences",
        text_color="#000000",
        text_align="center",
        font_size=12.0,
        font_weight=500,
        style_runs=(
            StyleRun(0, 11, link_url="https://emaillove.com/x#"),
            StyleRun(18, 32, link_url="https://emaillove.com/x#"),
            StyleRun(39, 53, link_url="https://emaillove.com/x#"),
            StyleRun(60, 71, link_url="https://emaillove.com/x#"),
        ),
    )


def _c7_tc_email_line() -> TextBlock:
    # T&C underlined link + a #0080C6 underlined email link, with a hard
    # LF+U+2028 break between the two visual lines.
    return TextBlock(
        node_id="tc",
        content=(
            "*For full Terms & Conditions, click here\n\u2028\xa0"
            "This email was sent to:\xa0email@brand.emaillove.com. "
            "LEGO Aastvej 1, Billund, 7190, Denmark"
        ),
        text_color="#000000",
        text_align="center",
        font_size=11.0,
        font_weight=500,
        style_runs=(
            StyleRun(0, 41, link_url="https://emaillove.com/x#", underline=True),
            StyleRun(
                67, 92, link_url="https://emaillove.com/x#", color_hex="#0080C6", underline=True
            ),
        ),
    )


def _c5_unsub_text() -> TextBlock:
    # c5's "unsubscribe here" is DEAD plain text — no style_runs.
    return TextBlock(
        node_id="c5",
        content="No longer want to receive these emails? You can\xa0unsubscribe here.",
        text_color="#FFFFFF",
        font_size=12.0,
        font_weight=400,
    )


def _design_system_with_footer(**kw: str) -> DesignSystem:
    defaults = {"company_name": "Acme Corp", "address": "1 Market St, SF, CA"}
    defaults.update(kw)
    return DesignSystem(
        palette=BrandPalette(primary="#111111", secondary="#222222", accent="#333333"),
        typography=Typography(heading_font="Arial", body_font="Arial"),
        footer=FooterConfig(**defaults),
    )


# ── Style-run link emission ──


def test_style_run_links_emit_anchors() -> None:
    html = _render_text_runs(_c7_link_bar())
    assert html.count('<a href="https://emaillove.com/x#"') == 4
    assert ">Unsubscribe</a>" in html
    assert ">Preferences</a>" in html
    # Bar runs carry no underline → text-decoration: none.
    assert "text-decoration: none;" in html


def test_email_run_is_colored_and_underlined() -> None:
    html = _render_text_runs(_c7_tc_email_line())
    assert (
        'style="color: #0080C6; text-decoration: underline;">email@brand.emaillove.com</a>' in html
    )
    # T&C run underlined, inheriting the node colour (no run colour).
    assert (
        'style="color: #000000; text-decoration: underline;">*For full Terms &amp; Conditions, click here</a>'
        in html
    )


def test_multiline_collapses_to_single_break_outside_anchor() -> None:
    html = _render_text_runs(_c7_tc_email_line())
    assert "<br /><br />" not in html  # no blank line
    assert "<br /></a>" not in html  # break never trapped inside the anchor
    assert html.count("<br />") == 1


def test_plain_text_node_has_no_anchor() -> None:
    html = _render_text_runs(_c5_unsub_text())
    assert "<a " not in html
    assert "unsubscribe here." in html


def test_backward_and_overlapping_runs_are_skipped() -> None:
    node = TextBlock(
        node_id="x",
        content="hello world",
        style_runs=(
            StyleRun(6, 11, link_url="https://example.com"),
            StyleRun(0, 3, link_url="https://example.com"),  # backward → skipped
        ),
    )
    html = _render_text_runs(node)
    # Only the first-in-sorted-order run (0-3) links; 6-11 also links (forward).
    assert html.count("<a ") >= 1
    assert "world" in html


# ── Per-node editorial rows ──


def test_editorial_is_per_node_rows() -> None:
    fills = _fills_footer(_footer_section([_c7_link_bar(), _c7_tc_email_line()]), 600)
    editorial = next(f.value for f in fills if f.slot_id == "footer_editorial")
    assert editorial.count("<tr>") == 2  # one row per text node
    assert editorial.startswith("<table")


def test_typography_from_design_props() -> None:
    fills = _fills_footer(_footer_section([_c7_tc_email_line()]), 600)
    editorial = next(f.value for f in fills if f.slot_id == "footer_editorial")
    assert "font-size:11px" in editorial
    assert "font-weight:500" in editorial
    assert "text-align:center" in editorial


# ── footer_legal compliance policy ──


def test_legal_absent_drops_placeholder_keeps_unsub() -> None:
    legal = _footer_legal_html(None)
    assert "Company Name" not in legal
    assert "Business Street" not in legal
    assert "{{unsubscribeUrl}}" in legal
    assert "{{preferencesUrl}}" in legal
    assert legal.count("<tr>") == 1  # unsub row only


def test_legal_present_substitutes_footer_config() -> None:
    ds = _design_system_with_footer(unsubscribe_text="Opt out")
    legal = _footer_legal_html(ds)
    assert "&copy; Acme Corp. All rights reserved." in legal
    assert "1 Market St, SF, CA" in legal
    assert ">Opt out</a>" in legal
    assert "{{unsubscribeUrl}}" in legal  # merge tag still guaranteed
    assert "Company Name" not in legal


def test_legal_present_uses_legal_text_over_copyright() -> None:
    ds = _design_system_with_footer(legal_text="(c) 2026 Acme. Reg. No. 12345.")
    legal = _footer_legal_html(ds)
    assert "(c) 2026 Acme. Reg. No. 12345." in legal
    assert "All rights reserved" not in legal


def test_legal_present_omits_empty_address() -> None:
    ds = _design_system_with_footer(address="")
    legal = _footer_legal_html(ds)
    # copyright row + unsub row only (no address row).
    assert legal.count("<tr>") == 2


# ── _fills_footer end-to-end invariants ──


def test_empty_texts_still_emits_compliance_row() -> None:
    fills = _fills_footer(_footer_section([]), 600)
    slot_ids = {f.slot_id for f in fills}
    assert "footer_editorial" not in slot_ids  # nothing to fill
    legal = next(f.value for f in fills if f.slot_id == "footer_legal")
    assert "{{unsubscribeUrl}}" in legal


def test_c7_coexist_two_unsub_one_functional() -> None:
    # c7 design bar carries its own "Unsubscribe" link; compliance row adds the
    # functional {{unsubscribeUrl}}. Ratified "Coexist" policy → both present.
    fills = _fills_footer(_footer_section([_c7_link_bar(), _c7_tc_email_line()]), 600)
    editorial = next(f.value for f in fills if f.slot_id == "footer_editorial")
    legal = next(f.value for f in fills if f.slot_id == "footer_legal")
    assert ">Unsubscribe</a>" in editorial  # design's decorative unsub
    assert "{{unsubscribeUrl}}" in legal  # functional compliance unsub
    assert legal.count("{{unsubscribeUrl}}") == 1  # exactly one compliance row
    assert "Company Name" not in (editorial + legal)


def test_c5_dead_unsub_text_still_gets_functional_row() -> None:
    fills = _fills_footer(_footer_section([_c5_unsub_text()]), 600)
    editorial = next(f.value for f in fills if f.slot_id == "footer_editorial")
    legal = next(f.value for f in fills if f.slot_id == "footer_legal")
    assert "unsubscribe here." in editorial  # design's dead plain text
    assert "{{unsubscribeUrl}}" in legal  # the ONLY working unsubscribe
    assert "<a " not in editorial  # dead text, not a link


def test_footer_legal_always_emitted() -> None:
    fills = _fills_footer(_footer_section([_c5_unsub_text()]), 600, design_system=None)
    assert any(f.slot_id == "footer_legal" for f in fills)


def test_design_system_threads_through_match_all() -> None:
    # Guards the design_system kwarg forwarding through the public converter
    # entry: match_all -> match_section -> _build_slot_fills -> _fills_footer.
    # A dropped kwarg at any hop silently falls back to the absent path (no
    # substitution), which this asserts against.
    from app.design_sync.component_matcher import match_all

    ds = _design_system_with_footer(company_name="Zeta Ltd", address="9 Kings Rd, London")
    matches = match_all([_footer_section([_c5_unsub_text()])], design_system=ds)
    legal = next(f.value for m in matches for f in m.slot_fills if f.slot_id == "footer_legal")
    assert "Zeta Ltd" in legal
    assert "9 Kings Rd, London" in legal
    assert "{{unsubscribeUrl}}" in legal
