"""CE-2 (#420) content checks over converter output.

Four per-case checks, each compared to the design file (``structure.json``):

* ``unsubscribe_link``: the design text has an unsubscribe phrase, so the
  output must carry an ``<a>`` for it with a real href.
* ``font_generic``: every ``font-family`` in the output ends in a generic family.
* ``default_blue``: ``#0066cc`` / ``#06c`` is absent unless the design uses it.
* ``cta_count``: non-MSO output CTAs >= design CTAs.

Failures are held by a strict allow-list keyed to the fixing ticket
(``data/debug/content_check_allowlist.yaml``). Run as a CLI::

    python -m app.design_sync.tests.content_checks [--empty-allowlist]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from pathlib import Path
from typing import Any, Self

import yaml
from lxml import html as lxml_html
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.logging import setup_logging
from app.design_sync.converter_service import ConversionResult
from app.design_sync.tests.regression_runner import run_case_conversion
from app.design_sync.unsubscribe_links import UNSUBSCRIBE_RE

DEBUG_DIR = Path(__file__).resolve().parents[3] / "data" / "debug"
ALLOWLIST_PATH = DEBUG_DIR / "content_check_allowlist.yaml"
CASES = ["5", "6", "7", "8", "9", "10"]


class ContentCheck(StrEnum):
    UNSUBSCRIBE_LINK = "unsubscribe_link"
    FONT_GENERIC = "font_generic"
    DEFAULT_BLUE = "default_blue"
    CTA_COUNT = "cta_count"


# ── Design readers (structure.json only) ─────────────────────────

_SPACE_CHARS = str.maketrans({0xA0: " ", 0x2007: " ", 0x202F: " "})  # nbsp, figure, narrow nbsp
_DEFAULT_BLUE_RE = re.compile(r"#0066cc\b|#06c\b", re.IGNORECASE)
_BUTTON_HINTS = ("button", "btn", "cta", "action", "link", "mj-button")
_BUTTON_TYPES = ("FRAME", "COMPONENT", "INSTANCE")


def load_structure(case: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((DEBUG_DIR / case / "structure.json").read_text())
    return data


def _children(node: dict[str, Any]) -> list[dict[str, Any]]:
    children: list[dict[str, Any]] = node.get("children") or []
    return children


def _roots(structure: dict[str, Any]) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = structure.get("pages") or []
    return pages


def iter_visible_nodes(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield ``node`` and its descendants, skipping ``visible is False`` subtrees."""
    if node.get("visible") is False:
        return
    yield node
    for child in _children(node):
        yield from iter_visible_nodes(child)


def _visible(structure: dict[str, Any]) -> Iterator[dict[str, Any]]:
    for page in _roots(structure):
        yield from iter_visible_nodes(page)


def design_text(structure: dict[str, Any]) -> str:
    """All visible TEXT content, joined by newlines, with non-breaking spaces as spaces."""
    texts = [
        str(n["text_content"])
        for n in _visible(structure)
        if n.get("type") == "TEXT" and n.get("text_content")
    ]
    return "\n".join(texts).translate(_SPACE_CHARS)


def design_has_unsubscribe(structure: dict[str, Any]) -> bool:
    return UNSUBSCRIBE_RE.search(design_text(structure)) is not None


def design_has_default_blue(structure: dict[str, Any]) -> bool:
    """True when a visible node's colour field (or a style run colour) is ``#0066cc``/``#06c``."""
    for node in _visible(structure):
        colors: list[Any] = [node.get(k) for k in ("fill_color", "text_color", "stroke_color")]
        runs: list[dict[str, Any]] = node.get("style_runs") or []
        colors += [run.get("color_hex") for run in runs]
        if any(isinstance(c, str) and _DEFAULT_BLUE_RE.search(c) for c in colors):
            return True
    return False


def _is_design_button(node: dict[str, Any]) -> bool:
    """Mirror of ``layout_analyzer._walk_for_buttons`` acceptance."""
    if node.get("type") not in _BUTTON_TYPES:
        return False
    texts = [c for c in _children(node) if c.get("type") == "TEXT" and c.get("text_content")]
    height = node.get("height")
    if len(texts) != 1 or len(str(texts[0]["text_content"])) > 30:
        return False
    if height is None or height > 80:
        return False
    name = str(node.get("name") or "").lower()
    fill = str(node.get("fill_color") or "").upper()
    return any(h in name for h in _BUTTON_HINTS) or fill not in ("#FFFFFF", "#FFF", "")


def _count_buttons(node: dict[str, Any]) -> int:
    if node.get("visible") is False:
        return 0
    if _is_design_button(node):
        return 1  # counted nodes are not recursed
    return sum(_count_buttons(c) for c in _children(node))


def design_cta_count(structure: dict[str, Any]) -> int:
    return sum(_count_buttons(page) for page in _roots(structure))


# ── Output readers ───────────────────────────────────────────────

GENERIC_FAMILIES = frozenset(
    {
        "serif",
        "sans-serif",
        "monospace",
        "cursive",
        "fantasy",
        "system-ui",
        "ui-serif",
        "ui-sans-serif",
        "ui-monospace",
        "ui-rounded",
    }
)
_COND_BLOCK_RE = re.compile(r"<!--\[if[^\]]*\]>(.*?)<!\[endif\]-->", re.DOTALL)
_STYLE_BLOCK_RE = re.compile(r"<style\b[^>]*>(.*?)</style>", re.DOTALL | re.IGNORECASE)
_CSS_FONT_FAMILY_RE = re.compile(r"font-family\s*:\s*([^;}]+)", re.IGNORECASE)
# Copies of test_converter_data_regression.py's MSO regexes.
_MSO_BLOCK_RE = re.compile(r"<!--\[if[^\]]*\]>.*?<!\[endif\]-->", re.DOTALL)
_NON_MSO_WRAPPER_RE = re.compile(r"<!--\[if\s+!mso\]><!-->(.*?)<!--<!\[endif\]-->", re.DOTALL)


def output_unsubscribe_links(html: str) -> int:
    """``<a>`` elements with an unsubscribe phrase in href or text and a real href."""
    doc = lxml_html.document_fromstring(html)
    count = 0
    for a in doc.iter("a"):
        href = a.get("href") or ""
        if href in ("", "#"):
            continue
        if UNSUBSCRIBE_RE.search(href) or UNSUBSCRIBE_RE.search(a.text_content()):
            count += 1
    return count


def _attr_font_families(root: lxml_html.HtmlElement) -> list[str]:
    values: list[str] = []
    for el in root.iter():
        if not isinstance(el.tag, str):  # comments, processing instructions
            continue
        for decl in (el.get("style") or "").split(";"):
            key, _, value = decl.partition(":")
            if key.strip().lower() == "font-family":
                values.append(value.strip())
        face = el.get("face")
        if face:
            values.append(face.strip())
    return values


def _css_font_families(html: str) -> list[str]:
    return [
        v.strip()
        for block in _STYLE_BLOCK_RE.findall(html)
        for v in _CSS_FONT_FAMILY_RE.findall(block)
    ]


def font_family_values(html: str) -> list[str]:
    """Every ``font-family`` value (attrs, ``face``, ``<style>``, conditional blocks), with repeats."""
    values = _attr_font_families(lxml_html.document_fromstring(html)) + _css_font_families(html)
    for body in _COND_BLOCK_RE.findall(html):
        if "<" not in body:
            continue
        values += _attr_font_families(lxml_html.fragment_fromstring(body, create_parent="div"))
        values += _css_font_families(body)
    return values


def is_bare_font(value: str) -> bool:
    """True when the last family of a ``font-family`` value is not generic."""
    last = value.split(",")[-1].replace("!important", "").strip().strip("'\"").strip().lower()
    return last not in GENERIC_FAMILIES


def _unquote(value: str) -> str:
    return value.replace('"', "").replace("'", "").strip()


def output_bare_fonts(html: str) -> list[str]:
    """Sorted distinct bare ``font-family`` values, quotes stripped."""
    return sorted({_unquote(v) for v in font_family_values(html) if is_bare_font(v)})


def output_default_blue(html: str) -> int:
    return len(_DEFAULT_BLUE_RE.findall(html))


def strip_mso(html: str) -> str:
    """Drop MSO conditional blocks; keep the content of ``<!--[if !mso]><!-->`` wrappers.

    Unwrap first: ``_MSO_BLOCK_RE`` also matches a whole ``!mso`` wrapper.
    """
    return _MSO_BLOCK_RE.sub("", _NON_MSO_WRAPPER_RE.sub(r"\1", html))


def output_cta_count(html: str) -> int:
    """Non-MSO ``<a>`` buttons: ``display:inline-block`` plus padding in the inline style."""
    doc = lxml_html.document_fromstring(strip_mso(html))
    count = 0
    for a in doc.iter("a"):
        style = a.get("style") or ""
        if "display:inline-block" in style.replace(" ", "") and "padding" in style:
            count += 1
    return count


# ── Checks ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class CheckResult:
    case: str
    check: ContentCheck
    passed: bool
    detail: str


def _check_unsubscribe(case: str, structure: dict[str, Any], html: str) -> CheckResult:
    if not design_has_unsubscribe(structure):
        return CheckResult(case, ContentCheck.UNSUBSCRIBE_LINK, True, "n/a")
    n = output_unsubscribe_links(html)
    return CheckResult(case, ContentCheck.UNSUBSCRIBE_LINK, n >= 1, f"links={n}")


def _check_fonts(case: str, structure: dict[str, Any], html: str) -> CheckResult:
    del structure  # every family must end generic, whatever the design uses
    bare = output_bare_fonts(html)
    return CheckResult(case, ContentCheck.FONT_GENERIC, not bare, "|".join(bare))


def _check_blue(case: str, structure: dict[str, Any], html: str) -> CheckResult:
    if design_has_default_blue(structure):
        return CheckResult(case, ContentCheck.DEFAULT_BLUE, True, "n/a")
    n = output_default_blue(html)
    return CheckResult(case, ContentCheck.DEFAULT_BLUE, n == 0, f"count={n}")


def _check_ctas(case: str, structure: dict[str, Any], html: str) -> CheckResult:
    out, design = output_cta_count(html), design_cta_count(structure)
    return CheckResult(case, ContentCheck.CTA_COUNT, out >= design, f"output={out} design={design}")


type CheckFn = Callable[[str, dict[str, Any], str], CheckResult]

CHECKS: dict[ContentCheck, CheckFn] = {
    ContentCheck.UNSUBSCRIBE_LINK: _check_unsubscribe,
    ContentCheck.FONT_GENERIC: _check_fonts,
    ContentCheck.DEFAULT_BLUE: _check_blue,
    ContentCheck.CTA_COUNT: _check_ctas,
}


def check_case(case: str, structure: dict[str, Any], html: str) -> list[CheckResult]:
    return [fn(case, structure, html) for fn in CHECKS.values()]


@cache
def convert_case(case: str) -> ConversionResult | None:
    """Default-path conversion of a case (cached); ``None`` when its inputs are absent."""
    return run_case_conversion(DEBUG_DIR / case)


def converted_html(case: str) -> str | None:
    result = convert_case(case)
    return None if result is None else result.html


def run_case(case: str) -> list[CheckResult]:
    html = converted_html(case)
    if html is None:
        msg = f"case {case}: structure.json/tokens.json not present"
        raise FileNotFoundError(msg)
    return check_case(case, load_structure(case), html)


def run_all(cases: list[str] | None = None) -> list[CheckResult]:
    return [r for case in cases or CASES for r in run_case(case)]


# ── Allow-list ───────────────────────────────────────────────────


class AllowEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case: str
    check: ContentCheck
    owner: str = Field(pattern=r"^#\d+$")
    detail: str
    note: str = ""


class Allowlist(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    entries: list[AllowEntry] = []

    @model_validator(mode="after")
    def _unique_keys(self) -> Self:
        seen: set[tuple[str, ContentCheck]] = set()
        for e in self.entries:
            key = (e.case, e.check)
            if key in seen:
                msg = f"duplicate allow-list entry for case {e.case} check {e.check}"
                raise ValueError(msg)
            seen.add(key)
        return self

    def lookup(self, case: str, check: ContentCheck) -> AllowEntry | None:
        return next((e for e in self.entries if e.case == case and e.check == check), None)


def load_allowlist(path: Path = ALLOWLIST_PATH) -> Allowlist:
    data: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
    return Allowlist.model_validate(data)


def evaluate(results: list[CheckResult], allowlist: Allowlist) -> list[str]:
    """Problems: new failure, changed failure, retired-but-listed entry, stale entry."""
    problems: list[str] = []
    for r in results:
        entry = allowlist.lookup(r.case, r.check)
        where = f"case {r.case} {r.check}"
        if not r.passed and entry is None:
            problems.append(f"{where}: new failure ({r.detail})")
        elif not r.passed and entry is not None and entry.detail != r.detail:
            problems.append(
                f"{where}: failure changed; update the entry "
                f"(allow-listed {entry.detail!r}, got {r.detail!r})"
            )
        elif r.passed and entry is not None:
            problems.append(f"{where}: now passes; retire the entry (owner {entry.owner})")
    run_cases = {r.case for r in results}
    problems += [
        f"case {e.case} {e.check}: stale entry (case not run)"
        for e in allowlist.entries
        if e.case not in run_cases
    ]
    return problems


# ── CLI ──────────────────────────────────────────────────────────


def render_table(results: list[CheckResult], allowlist: Allowlist) -> str:
    lines = ["| case | check | result | detail | owner |", "|---|---|---|---|---|"]
    for r in results:
        entry = allowlist.lookup(r.case, r.check)
        result = (
            "pass" if r.passed else ("allowed" if entry and entry.detail == r.detail else "FAIL")
        )
        owner = entry.owner if entry else ""
        detail = r.detail.replace("|", "\\|")  # keep the Markdown columns intact
        lines.append(f"| {r.case} | {r.check} | {result} | {detail} | {owner} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument(
        "--empty-allowlist",
        action="store_true",
        help="evaluate against an empty allow-list (shows every failure)",
    )
    args = parser.parse_args(argv)
    setup_logging("ERROR")  # keep converter logs out of the table
    allowlist = Allowlist() if args.empty_allowlist else load_allowlist()
    results = run_all()
    problems = evaluate(results, allowlist)
    print(render_table(results, allowlist))  # noqa: T201
    if problems:
        print("\nProblems:")  # noqa: T201
        for p in problems:
            print(f"- {p}")  # noqa: T201
        return 1
    print("\nNo problems.")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
