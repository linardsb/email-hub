"""Pinned safety preamble — canonical clauses + fail-closed loader (51.2).

Loads ``safety_preamble.md`` once at import. The file text becomes
``SAFETY_PREAMBLE``; the ``<!-- PREAMBLE_VERSION: X.Y.Z -->`` marker on the
first line becomes ``PREAMBLE_VERSION``. Any read error is captured (not
raised) so importing this module can never crash the process; callers convert
it to a fail-closed ``ServiceUnavailableError`` via :func:`ensure_loaded` only
when the safe-compaction flag is on.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.core.exceptions import ServiceUnavailableError
from app.core.logging import get_logger

logger = get_logger(__name__)

__all__ = [
    "PREAMBLE_VERSION",
    "SAFETY_PREAMBLE",
    "check_version_drift",
    "ensure_loaded",
]

_PREAMBLE_PATH = Path(__file__).with_name("safety_preamble.md")
_VERSION_RE = re.compile(r"<!--\s*PREAMBLE_VERSION:\s*(\S+)\s*-->")


def _load() -> tuple[str, str, OSError | None]:
    """Read the preamble file, returning (text, version, load_error).

    Captures ``OSError`` instead of raising so import is crash-proof.
    """
    try:
        text = _PREAMBLE_PATH.read_text(encoding="utf-8").strip()
    except OSError as exc:  # missing / unreadable file
        return "", "", exc
    match = _VERSION_RE.search(text)
    version = match.group(1) if match else ""
    return text, version, None


SAFETY_PREAMBLE, PREAMBLE_VERSION, _LOAD_ERROR = _load()


def ensure_loaded() -> None:
    """Raise ``ServiceUnavailableError`` if the preamble failed to load.

    Fail-closed hook: callers invoke this only when
    ``security.safe_compaction_enabled`` is on, so a missing safety file
    short-circuits the agent with a 503 rather than shipping an unpinned
    prompt.
    """
    if _LOAD_ERROR is not None:
        logger.error(
            "security.safety_preamble_load_failed",
            path=str(_PREAMBLE_PATH),
            error=str(_LOAD_ERROR),
        )
        raise ServiceUnavailableError("Safety preamble unavailable")


def check_version_drift(config_version: str) -> None:
    """Warn when the configured expected version differs from the loaded file.

    Stateless: emits per call, but only fires when ``config_version`` is
    non-empty and mismatched — a misconfiguration that is itself worth fixing.
    """
    if config_version and config_version != PREAMBLE_VERSION:
        logger.warning(
            "security.safety_preamble_version_drift",
            expected=config_version,
            loaded=PREAMBLE_VERSION,
        )
