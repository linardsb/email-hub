"""CE-2 (#420) content checks: design readers, output readers, allow-list rules.

Reader tests mutate real converted output (never hand-written email HTML).
``test_content_checks_hold_allowlist`` runs every case against the committed
``data/debug/content_check_allowlist.yaml``.
"""

from __future__ import annotations

import copy
import re
from typing import Any

import pytest
from pydantic import ValidationError

from app.design_sync.tests.content_checks import (
    ALLOWLIST_PATH,
    CASES,
    CHECKS,
    AllowEntry,
    Allowlist,
    CheckResult,
    ContentCheck,
    check_case,
    convert_case,
    design_cta_count,
    design_has_default_blue,
    design_has_unsubscribe,
    evaluate,
    font_family_values,
    is_bare_font,
    iter_visible_nodes,
    load_allowlist,
    load_structure,
    output_bare_fonts,
    output_cta_count,
    output_unsubscribe_links,
    run_all,
)

_UNSUB_ANCHOR_RE = re.compile(r'<a\b[^>]*href="\{\{unsubscribeUrl\}\}"[^>]*>(.*?)</a>', re.DOTALL)
_CTA_ANCHOR_RE = re.compile(r"<a\b[^>]*display:\s*inline-block[^>]*padding[^>]*>.*?</a>", re.DOTALL)
_SECTION_MARKER_RE = re.compile(r"<!-- section:\S+ -->")
_GEIST = "font-family:Geist Mono;"
_MSO_OPEN = "<!--[if mso]>"
_MSO_CLOSE = "<![endif]-->"
_NON_MSO_OPEN = "<!--[if !mso]><!-->"
_NON_MSO_CLOSE = "<!--<![endif]-->"
_COND_BLOCK_RE = re.compile(r"<!--\[if[^\]]*\]>.*?<!\[endif\]-->", re.DOTALL)


def _html(case: str) -> str:
    result = convert_case(case)
    if result is None:
        pytest.skip(f"case {case}: structure.json/tokens.json not present")
    return result.html


def _structure(case: str) -> dict[str, Any]:
    _html(case)  # skip when inputs are absent
    return load_structure(case)


def test_checks_cover_enum() -> None:
    assert set(CHECKS) == set(ContentCheck)


# ── Design readers ───────────────────────────────────────────────

_DESIGN_CTAS = {"5": 8, "6": 2, "7": 9, "8": 2, "9": 2, "10": 2}


@pytest.mark.parametrize("case", CASES)
class TestDesignReaders:
    def test_cta_count_pinned(self, case: str) -> None:
        assert design_cta_count(_structure(case)) == _DESIGN_CTAS[case]

    def test_cta_walker_matches_layout_buttons(self, case: str) -> None:
        result = convert_case(case)
        assert result is not None and result.layout is not None
        layout_buttons = sum(len(s.buttons) for s in result.layout.sections)
        assert design_cta_count(_structure(case)) == layout_buttons

    def test_design_has_unsubscribe(self, case: str) -> None:
        assert design_has_unsubscribe(_structure(case))

    def test_design_has_no_default_blue(self, case: str) -> None:
        assert not design_has_default_blue(_structure(case))


def _ids(node: dict[str, Any]) -> set[str]:
    return {str(n["id"]) for n in iter_visible_nodes(node)}


def test_iter_visible_nodes_skips_hidden_subtree() -> None:
    page = copy.deepcopy(_structure("10")["pages"][0])
    target = next(n for n in iter_visible_nodes(page) if n is not page and n.get("children"))
    hidden = _ids(target)
    before = _ids(page)
    assert len(hidden) > 1
    assert hidden <= before

    target["visible"] = False
    after = _ids(page)
    assert after == before - hidden


def test_hidden_section_drops_its_design_ctas() -> None:
    structure = copy.deepcopy(_structure("5"))
    total = design_cta_count(structure)
    section = next(
        s for s in structure["pages"][0]["children"] if design_cta_count({"pages": [s]}) > 0
    )
    in_section = design_cta_count({"pages": [section]})
    section["visible"] = False
    assert design_cta_count(structure) == total - in_section


def _filled_buttons(structure: dict[str, Any]) -> list[dict[str, Any]]:
    """Case 5's ``mj-button`` frames with a dark fill (one TEXT child each)."""
    return [
        n
        for page in structure["pages"]
        for n in iter_visible_nodes(page)
        if n.get("name") == "mj-button" and n.get("fill_color") == "#222222"
    ]


def test_tall_button_is_not_a_cta() -> None:
    structure = copy.deepcopy(_structure("5"))
    total = design_cta_count(structure)
    _filled_buttons(structure)[0]["height"] = 81
    assert design_cta_count(structure) == total - 1


def test_long_label_is_not_a_cta() -> None:
    structure = copy.deepcopy(_structure("5"))
    total = design_cta_count(structure)
    label = next(c for c in _filled_buttons(structure)[0]["children"] if c.get("type") == "TEXT")
    label["text_content"] = (f"{label['text_content']} " * 4)[:31]
    assert len(label["text_content"]) == 31
    assert design_cta_count(structure) == total - 1


def test_fill_decides_a_button_without_a_hint_name() -> None:
    structure = copy.deepcopy(_structure("5"))
    total = design_cta_count(structure)
    button = _filled_buttons(structure)[0]
    assert any(n.get("name") == "mj-column" for n in iter_visible_nodes(structure["pages"][0]))
    button["name"] = "mj-column"  # a real non-hint name from the same design
    assert design_cta_count(structure) == total  # dark fill still counts it
    button["fill_color"] = "#FFFFFF"
    assert design_cta_count(structure) == total - 1


def test_counted_button_is_not_recursed() -> None:
    structure = copy.deepcopy(_structure("5"))
    total = design_cta_count(structure)
    first, second = _filled_buttons(structure)[:2]
    first["children"].append(copy.deepcopy(second))
    assert design_cta_count(structure) == total


# ── Output readers on mutated real output ───────────────────────


def test_unsubscribe_reader_drops_when_anchor_removed() -> None:
    html = _html("5")
    before = output_unsubscribe_links(html)
    mutated, removed = _UNSUB_ANCHOR_RE.subn(r"\1", html)
    assert removed >= 1
    assert output_unsubscribe_links(mutated) == before - removed

    unsub = {r.check: r for r in check_case("5", _structure("5"), mutated)}
    assert unsub[ContentCheck.UNSUBSCRIBE_LINK].passed is (before - removed >= 1)


def test_unsubscribe_check_fails_without_any_link() -> None:
    html = _UNSUB_ANCHOR_RE.sub(r"\1", _html("5"))
    assert output_unsubscribe_links(html) == 0
    result = {r.check: r for r in check_case("5", _structure("5"), html)}
    assert result[ContentCheck.UNSUBSCRIBE_LINK] == CheckResult(
        "5", ContentCheck.UNSUBSCRIBE_LINK, False, "links=0"
    )


def test_hash_href_is_not_an_unsubscribe_link() -> None:
    html = _html("5")
    mutated, n = re.subn(r'href="\{\{unsubscribeUrl\}\}"', 'href="#"', html)
    assert n == 1
    assert output_unsubscribe_links(mutated) == output_unsubscribe_links(html) - 1


def test_unsubscribe_check_fails_when_repoint_regresses() -> None:
    """Review L1: with the repoint undone (case 6's design emaillove URL left
    in place) the check fails; a design URL is not an unsubscribe link."""
    html = _html("6")
    design_url = "https://emaillove.com/email-inspiration-from-starbucks-18?action=email-cleaned"
    assert f'href="{design_url}"' in html  # case 6's sibling footer links
    assert _UNSUB_ANCHOR_RE.search(html) is not None
    reverted = _UNSUB_ANCHOR_RE.sub(
        lambda m: m.group(0).replace("{{unsubscribeUrl}}", design_url), html
    )
    assert "{{unsubscribeUrl}}" not in reverted
    result = {r.check: r for r in check_case("6", _structure("6"), reverted)}
    assert result[ContentCheck.UNSUBSCRIBE_LINK] == CheckResult(
        "6", ContentCheck.UNSUBSCRIBE_LINK, False, "links=0"
    )


def _bare_geist(html: str) -> int:
    return sum(1 for v in font_family_values(html) if "Geist Mono" in v and is_bare_font(v))


def test_quoted_font_is_still_bare() -> None:
    html = _html("10")
    assert _GEIST in html
    mutated = html.replace(_GEIST, "font-family:&quot;Geist Mono&quot;;", 1)
    assert '"Geist Mono"' in font_family_values(mutated)
    assert _bare_geist(mutated) == _bare_geist(html)
    assert "Geist Mono" in output_bare_fonts(mutated)


def test_generic_fallback_with_important_is_accepted() -> None:
    html = _html("10")
    assert _GEIST in html
    value = "'Geist Mono', monospace !important"
    mutated = html.replace(_GEIST, f"font-family:{value};", 1)
    assert value in font_family_values(mutated)
    assert not is_bare_font(value)
    assert _bare_geist(mutated) < _bare_geist(html)


def _in_cond_block(html: str, pos: int) -> bool:
    return any(m.start() <= pos < m.end() for m in _COND_BLOCK_RE.finditer(html))


# Each test moves one of case 10's bare ``font-family:Geist Mono;`` out of its
# inline style into another place the reader must cover; the count holds.


def test_bare_font_moved_into_style_block_is_read() -> None:
    html = _html("10")
    assert _GEIST in html
    removed = html.replace(_GEIST, "", 1)
    style = next(
        m for m in re.finditer(r"<style\b[^>]*>", removed) if not _in_cond_block(removed, m.start())
    )
    brace = removed.index("{", style.end()) + 1
    mutated = removed[:brace] + _GEIST + removed[brace:]
    assert _bare_geist(mutated) == _bare_geist(html)


def test_bare_font_moved_into_mso_block_is_read() -> None:
    html = _html("10")
    assert _GEIST in html
    removed = html.replace(_GEIST, "", 1)
    block = removed.find(_MSO_OPEN, removed.find("<body"))
    attr = removed.index('style="', block) + len('style="')
    assert block > 0 and attr < removed.index(_MSO_CLOSE, block)
    mutated = removed[:attr] + _GEIST + removed[attr:]
    assert _bare_geist(mutated) == _bare_geist(html)


def test_bare_font_moved_into_face_attribute_is_read() -> None:
    html = _html("10")
    at = html.index(_GEIST)
    tag = html.rfind("<", 0, at)
    name = re.match(r"<\w+", html[tag:])
    assert name is not None
    head = name.group(0)
    mutated = (
        f'{html[:tag]}{head} face="Geist Mono"{html[tag + len(head) : at]}'
        f"{html[at + len(_GEIST) :]}"
    )
    assert _bare_geist(mutated) == _bare_geist(html)


def test_mso_duplicate_cta_does_not_count() -> None:
    """A CTA copy in an MSO block does not count, even where a parser sees it:
    case 5's own section-marker comment inside the block ends the HTML comment
    early, so only ``strip_mso`` hides the copy."""
    html = _html("5")
    match = _CTA_ANCHOR_RE.search(html)
    marker = _SECTION_MARKER_RE.search(html)
    assert match is not None and marker is not None
    assert _MSO_OPEN in html and _MSO_CLOSE in html
    before = output_cta_count(html)
    end = match.end()

    in_mso = f"{html[:end]}{_MSO_OPEN}{marker.group(0)}{match.group(0)}{_MSO_CLOSE}{html[end:]}"
    assert output_cta_count(in_mso) == before

    outside = f"{html[:end]}{match.group(0)}{html[end:]}"
    assert output_cta_count(outside) == before + 1


def test_non_mso_wrapped_cta_still_counts() -> None:
    """Case 5's own ``<!--[if !mso]><!-->`` wrapper around one of its CTAs
    keeps the CTA: wrapper content is what non-MSO clients render."""
    html = _html("5")
    match = _CTA_ANCHOR_RE.search(html)
    assert match is not None
    assert _NON_MSO_OPEN in html and _NON_MSO_CLOSE in html
    cta = match.group(0)
    wrapped = html.replace(cta, f"{_NON_MSO_OPEN}{cta}{_NON_MSO_CLOSE}", 1)
    assert output_cta_count(wrapped) == output_cta_count(html)


# ── evaluate rules ───────────────────────────────────────────────


def _r(case: str, check: ContentCheck, passed: bool, detail: str) -> CheckResult:
    return CheckResult(case, check, passed, detail)


def _allow(*entries: tuple[str, ContentCheck, str]) -> Allowlist:
    return Allowlist(
        entries=[AllowEntry(case=c, check=k, owner="#425", detail=d) for c, k, d in entries]
    )


_FONT = ContentCheck.FONT_GENERIC


def test_evaluate_clean() -> None:
    results = [_r("10", _FONT, False, "Geist Mono"), _r("5", _FONT, True, "")]
    assert evaluate(results, _allow(("10", _FONT, "Geist Mono"))) == []


def test_evaluate_rule1_new_failure() -> None:
    problems = evaluate([_r("10", _FONT, False, "Geist Mono")], Allowlist())
    assert len(problems) == 1 and "new failure" in problems[0]


def test_evaluate_rule2_changed_failure() -> None:
    results = [_r("10", _FONT, False, "Geist Mono|Helvetica")]
    problems = evaluate(results, _allow(("10", _FONT, "Geist Mono")))
    assert len(problems) == 1 and "failure changed; update the entry" in problems[0]


def test_evaluate_rule3_now_passes() -> None:
    problems = evaluate([_r("10", _FONT, True, "")], _allow(("10", _FONT, "Geist Mono")))
    assert len(problems) == 1 and "now passes; retire the entry (owner #425)" in problems[0]


def test_evaluate_rule4_stale_entry() -> None:
    problems = evaluate([_r("5", _FONT, True, "")], _allow(("11", _FONT, "Arial")))
    assert len(problems) == 1 and "stale entry" in problems[0]


# ── Allow-list schema ────────────────────────────────────────────


def test_allowlist_rejects_duplicates() -> None:
    entry = {"case": "10", "check": "font_generic", "owner": "#425", "detail": "Geist Mono"}
    with pytest.raises(ValidationError, match="duplicate"):
        Allowlist.model_validate({"entries": [entry, {**entry, "detail": "Arial"}]})


@pytest.mark.parametrize("owner", ["425", "#", "#42a", "CE-7", " #425"])
def test_allowlist_rejects_bad_owner(owner: str) -> None:
    with pytest.raises(ValidationError):
        AllowEntry.model_validate(
            {"case": "10", "check": "font_generic", "owner": owner, "detail": "x"}
        )


def test_allowlist_rejects_unknown_fields_and_checks() -> None:
    base = {"case": "10", "check": "font_generic", "owner": "#425", "detail": "x"}
    with pytest.raises(ValidationError):
        AllowEntry.model_validate({**base, "ticket": "#425"})
    with pytest.raises(ValidationError):
        AllowEntry.model_validate({**base, "check": "font"})
    with pytest.raises(ValidationError):
        Allowlist.model_validate({"entries": [], "extra": 1})


def test_committed_allowlist_parses() -> None:
    assert ALLOWLIST_PATH.exists()
    load_allowlist()


# ── The gate ─────────────────────────────────────────────────────


def test_content_checks_hold_allowlist() -> None:
    for case in CASES:
        _html(case)
    problems = evaluate(run_all(), load_allowlist())
    assert not problems, "content checks vs allow-list:\n" + "\n".join(problems)
