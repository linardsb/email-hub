"""Give converter output a working unsubscribe link (CE-2 #420).

Runs on final HTML in every output path (default, MJML, tree):

1. Any ``<a>`` whose text is an unsubscribe phrase and whose href is not an
   ESP merge tag (``{{…}}``) is repointed at ``{{unsubscribeUrl}}``.
2. If no unsubscribe link exists afterwards, every unlinked phrase in visible
   text is wrapped in ``<a href="{{unsubscribeUrl}}">`` coloured like its cell.

Comments (including MSO conditional blocks) are never edited. The pass is
idempotent, so it is safe on cached HTML.
"""

from __future__ import annotations

import re

from app.core.logging import get_logger

logger = get_logger(__name__)

# Word-bounded on purpose (diverges from app/qa_engine/checks/deliverability.py:81):
# without \b, opt[\s-]?out matches inside "adopt outdoor".
# Privacy opt-outs ("Opt-out of sale", "cookie opt-out") are not unsubscribes:
# they keep their design href and never count as an unsubscribe link.
_OPT_OUT = (
    r"(?<!cookie[\s-])(?<!cookies[\s-])"
    r"opt[\s-]?out"
    r"(?![\s/_-]+of[\s/_-]+(?:the[\s/_-]+)?"
    r"(?:sale|sell|selling|share|sharing|cookies?|tracking|targeted|personali[sz]ed"
    r"|interest[\s-]based|ads|advertising|data)\b)"
)
UNSUBSCRIBE_RE = re.compile(
    r"\b(?:"
    rf"unsubscribe|{_OPT_OUT}"  # en
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

_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_TOKEN_RE = re.compile(r"(<!--.*?-->|<[^>]+>)", re.DOTALL)
_TAG_RE = re.compile(r"<\s*(/?)\s*([a-zA-Z][\w:-]*)([^>]*)>", re.DOTALL)
_STYLE_ATTR_RE = re.compile(r"""\bstyle\s*=\s*(["'])(.*?)\1""", re.DOTALL | re.IGNORECASE)
_COLOR_DECL_RE = re.compile(r"(?:^|;)\s*color\s*:\s*([^;]+)", re.IGNORECASE)
_HREF_RE = re.compile(r"""\bhref\s*=\s*(["'])(.*?)\1""", re.DOTALL | re.IGNORECASE)
_ANCHOR_RE = re.compile(r"<a\b([^>]*)>(.*?)</a\s*>", re.DOTALL | re.IGNORECASE)
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
        if href and UNSUBSCRIBE_RE.search(href.group(2)):
            return True
        if UNSUBSCRIBE_RE.search(_STRIP_TAGS_RE.sub(" ", inner)):
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
        if not UNSUBSCRIBE_RE.search(_STRIP_TAGS_RE.sub(" ", inner)):
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

    return _ANCHOR_RE.sub(_outside_comments, html), count


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
        if any(t in _OPAQUE for t, _ in stack) or not UNSUBSCRIBE_RE.search(token):
            out.append(token)
            continue
        color = next((c for _, c in reversed(stack) if c), "inherit")

        def _wrap(match: re.Match[str], color: str = color) -> str:
            return (
                f'<a href="{_UNSUB_HREF}" style="color:{color};text-decoration:underline;">'
                f"{match.group(0)}</a>"
            )

        new, n = UNSUBSCRIBE_RE.subn(_wrap, token)
        linked += n
        out.append(new)
    if linked:
        logger.info("design_sync.unsubscribe_text_linked", count=linked)
    return "".join(out)
