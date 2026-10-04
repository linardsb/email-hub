"""Give converter output a working unsubscribe link (CE-2 #420).

Runs on final HTML in every output path (default, MJML, tree):

1. Any ``<a>`` whose text is an unsubscribe phrase and whose href is not an
   ESP merge tag (``{{…}}``) is repointed at ``{{unsubscribeUrl}}``.
2. If no unsubscribe link exists afterwards, every unlinked phrase in visible
   text is wrapped in ``<a href="{{unsubscribeUrl}}">`` coloured like its cell.

Comments (including MSO conditional blocks) are never edited, with one
exception: a ``<v:roundrect>`` VML button (CE-11) whose label is an unsubscribe
phrase gets the same href as its HTML twin. The pass is idempotent, so it is
safe on cached HTML.
"""

from __future__ import annotations

import re

from app.core.logging import get_logger

logger = get_logger(__name__)

# Word-bounded on purpose (diverges from app/qa_engine/checks/deliverability.py:81):
# without \b, opt[\s-]?out matches inside "adopt outdoor".
UNSUBSCRIBE_RE = re.compile(
    r"\b(?:"
    r"unsubscribe|opt[\s-]?out"  # en
    r"|abmelden|abbestellen"  # de
    r"|(?:se\s+)?d[ée]sabonner|(?:se\s+)?d[ée]sinscrire|d[ée]sinscription"  # fr
    r"|darse\s+de\s+baja|date\s+de\s+baja|cancelar\s+(?:la\s+)?suscripci[óo]n"  # es
    r"|disiscriviti|annulla\s+(?:l['\u2019]\s*)?iscrizione"  # it
    r"|afmelden|uitschrijven"  # nl
    r"|descadastrar|cancelar\s+(?:a\s+)?inscri[çc][ãa]o"  # pt
    r"|avregistrera|avsluta\s+prenumerationen|afmeld"  # sv/da/no
    r"|wypisz\s+si[ęe]"  # pl
    r")\b",
    re.IGNORECASE,
)

# An English opt-out next to a privacy marker in the same footer segment is a
# privacy control (CCPA "Do Not Sell … Opt Out", cookie or ad opt-outs), not an
# unsubscribe: it keeps its design href and never counts as the unsubscribe
# link. "Opt out of … emails/newsletters" is always an unsubscribe.
_OPT_OUT_RE = re.compile(r"opt[\s-]?out", re.IGNORECASE)
_EMAIL_OPT_OUT_RE = re.compile(
    r"opt[\s-]?out\s+of\s+(?:[\w'-]+\s+){0,4}?"
    r"(?:e-?mails|mailings?|newsletters?|messages|communications"
    r"|(?:marketing|promotional)\s+e-?mail)\b",
    re.IGNORECASE,
)
_PRIVACY_RE = re.compile(
    r"\b(?:sell|selling|sale|share|sharing|personal\s+(?:information|data)"
    r"|privacy\s+(?:choices|rights|options)|cookies?|ad\s*choices|ads|advertising"
    r"|targeted|tracking|profiling|analytics|third[\s-]party|data\s+(?:collection|sharing)"
    r"|interest[\s-]based|gpc|global\s+privacy\s+control|preference\s+signal)\b",
    re.IGNORECASE,
)
# Footer segment separators: "Privacy Policy | Opt out" is two segments.
_SEGMENT_SEP_RE = re.compile(r"[|•·\n]")


def _segment(text: str, start: int, end: int) -> str:
    """The separator-delimited part of *text* around ``text[start:end]``."""
    seps = [m.start() for m in _SEGMENT_SEP_RE.finditer(text)]
    left = max((i for i in seps if i < start), default=-1) + 1
    right = min((i for i in seps if i >= end), default=len(text))
    return text[left:right]


def find_unsubscribe(text: str) -> list[re.Match[str]]:
    """Unsubscribe phrase matches in *text*, privacy opt-outs excluded."""
    found: list[re.Match[str]] = []
    for m in UNSUBSCRIBE_RE.finditer(text):
        if (
            _OPT_OUT_RE.fullmatch(m.group(0))
            and not _EMAIL_OPT_OUT_RE.match(text, m.start())
            and _PRIVACY_RE.search(_segment(text, m.start(), m.end()))
        ):
            continue
        found.append(m)
    return found


def has_unsubscribe_phrase(text: str) -> bool:
    return bool(find_unsubscribe(text))


_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_TOKEN_RE = re.compile(r"(<!--.*?-->|<[^>]+>)", re.DOTALL)
_TAG_RE = re.compile(r"<\s*(/?)\s*([a-zA-Z][\w:-]*)([^>]*)>", re.DOTALL)
_STYLE_ATTR_RE = re.compile(r"""\bstyle\s*=\s*(["'])(.*?)\1""", re.DOTALL | re.IGNORECASE)
_COLOR_DECL_RE = re.compile(r"(?:^|;)\s*color\s*:\s*([^;]+)", re.IGNORECASE)
_HREF_RE = re.compile(r"""\bhref\s*=\s*(["'])(.*?)\1""", re.DOTALL | re.IGNORECASE)
_ANCHOR_RE = re.compile(r"<a\b([^>]*)>(.*?)</a\s*>", re.DOTALL | re.IGNORECASE)
_ROUNDRECT_RE = re.compile(r"<v:roundrect\b([^>]*)>(.*?)</v:roundrect>", re.DOTALL | re.IGNORECASE)
_STRIP_TAGS_RE = re.compile(r"<[^>]+>")
_VOID = frozenset(
    {"img", "br", "hr", "meta", "link", "input", "col", "area", "source", "wbr", "base"}
)
_OPAQUE = frozenset({"a", "style", "script", "title", "head"})
_UNSUB_HREF = "{{unsubscribeUrl}}"


def has_unsubscribe_link(html: str) -> bool:
    """True when any ``<a>`` has an unsubscribe phrase in its href or text."""
    for attrs, inner in _ANCHOR_RE.findall(html):
        href = _HREF_RE.search(attrs)
        if href and has_unsubscribe_phrase(href.group(2)):
            return True
        if has_unsubscribe_phrase(_STRIP_TAGS_RE.sub(" ", inner)):
            return True
    return False


def _tag_color(attrs: str) -> str | None:
    style = _STYLE_ATTR_RE.search(attrs)
    if style is None:
        return None
    found = _COLOR_DECL_RE.findall(style.group(2))
    return found[-1].strip() if found else None


def _repoint(html: str) -> tuple[str, int]:
    """Point phrase anchors outside comments at ``{{unsubscribeUrl}}``."""
    count = 0

    def _point_at_esp(match: re.Match[str]) -> str:
        nonlocal count
        attrs, inner = match.group(1), match.group(2)
        if not has_unsubscribe_phrase(_STRIP_TAGS_RE.sub(" ", inner)):
            return match.group(0)
        href = _HREF_RE.search(attrs)
        if href is not None and href.group(2).startswith("{{"):
            return match.group(0)
        if href is None:
            new_attrs = f' href="{_UNSUB_HREF}"{attrs}'
        else:
            new_attrs = attrs[: href.start()] + f'href="{_UNSUB_HREF}"' + attrs[href.end() :]
        count += 1
        return f"<a{new_attrs}>{inner}</a>"

    # Scan the whole document: an anchor may hold comments (the ``button``
    # seed's MSO spacers). Only anchors that start inside a comment are kept.
    comments = [(m.start(), m.end()) for m in _COMMENT_RE.finditer(html)]

    def _outside_comments(match: re.Match[str]) -> str:
        if any(start <= match.start() < end for start, end in comments):
            return match.group(0)
        return _point_at_esp(match)

    html = _ANCHOR_RE.sub(_outside_comments, html)

    def _point_vml_at_esp(match: re.Match[str]) -> str:
        # The VML twin is Outlook's clickable button: it must unsubscribe too.
        nonlocal count
        attrs, inner = match.group(1), match.group(2)
        href = _HREF_RE.search(attrs)
        if (
            href is None
            or href.group(2).startswith("{{")
            or not has_unsubscribe_phrase(_STRIP_TAGS_RE.sub(" ", inner))
        ):
            return match.group(0)
        count += 1
        new_attrs = attrs[: href.start()] + f'href="{_UNSUB_HREF}"' + attrs[href.end() :]
        return f"<v:roundrect{new_attrs}>{inner}</v:roundrect>"

    return _ROUNDRECT_RE.sub(_point_vml_at_esp, html), count


def link_unsubscribe_text(html: str) -> str:
    """Repoint unsubscribe anchors, then link bare phrases if none exists."""
    html, repointed = _repoint(html)
    if repointed:
        logger.info("design_sync.unsubscribe_link_repointed", count=repointed)
    if has_unsubscribe_link(html):
        return html

    stack: list[tuple[str, str | None]] = []
    out: list[str] = []
    linked = 0
    for token in _TOKEN_RE.split(html):
        if not token:
            continue
        if token.startswith("<!--"):
            out.append(token)
            continue
        m = _TAG_RE.fullmatch(token)
        if m:
            closing, name, attrs = m.group(1), m.group(2).lower(), m.group(3)
            if closing:
                for i in range(len(stack) - 1, -1, -1):
                    if stack[i][0] == name:
                        del stack[i:]
                        break
            elif name not in _VOID and not attrs.rstrip().endswith("/"):
                stack.append((name, _tag_color(attrs)))
            out.append(token)
            continue
        matches = [] if any(t in _OPAQUE for t, _ in stack) else find_unsubscribe(token)
        if not matches:
            out.append(token)
            continue
        color = next((c for _, c in reversed(stack) if c), "inherit")
        anchor = f'<a href="{_UNSUB_HREF}" style="color:{color};text-decoration:underline;">'
        cursor = 0
        for m in matches:
            out.append(f"{token[cursor : m.start()]}{anchor}{m.group(0)}</a>")
            cursor = m.end()
        out.append(token[cursor:])
        linked += len(matches)
    if linked:
        logger.info("design_sync.unsubscribe_text_linked", count=linked)
    return "".join(out)
