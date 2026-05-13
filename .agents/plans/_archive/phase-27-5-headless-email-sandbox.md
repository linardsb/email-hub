# Plan: 27.5 Headless Email Client Sandbox — SMTP-Based Real Sanitizer Capture

## Context

External rendering providers (Litmus, EoA) charge per-screenshot. The calibration loop (27.4) works with them but costs add up. A self-hosted sandbox eliminates this cost for the most common clients by sending email via SMTP to Mailpit (local), then using Playwright to open webmail (Roundcube) and capture the post-sanitizer DOM. This isn't a Gmail replica — it's for pipeline regression detection and Roundcube/Thunderbird-specific validation. For Gmail/Outlook.com fidelity, emulators (27.1) + external calibration (27.4) remain primary.

**Existing module structure:** `app/rendering/` already has `local/` (emulators, profiles, runner, service), `eoa/`, `litmus/`, `protocol.py`, `exceptions.py`, `routes.py`, `schemas.py`, `service.py`. The sandbox is a new sub-package at `app/rendering/sandbox/`.

**Dependencies already present:** `lxml`, `beautifulsoup4`, `playwright` (via npx CLI). **New dependency:** `aiosmtplib`.

## Files to Create

| File | Purpose |
|------|---------|
| `app/rendering/sandbox/__init__.py` | Package init |
| `app/rendering/sandbox/profiles.py` | `SandboxProfile` dataclass + `SANDBOX_PROFILES` registry |
| `app/rendering/sandbox/smtp.py` | `SandboxSMTP` — async SMTP send via `aiosmtplib` |
| `app/rendering/sandbox/dom_diff.py` | `DOMDiff` dataclass + `compute_dom_diff()` using `lxml` |
| `app/rendering/sandbox/sandbox.py` | `EmailSandbox` — orchestrator: send → navigate → extract DOM → diff → screenshot |
| `app/rendering/sandbox/schemas.py` | Request/response Pydantic models for sandbox API |
| `app/rendering/sandbox/service.py` | `SandboxService` — business logic, feature-flag gating |
| `app/rendering/sandbox/tests/__init__.py` | Test package |
| `app/rendering/sandbox/tests/test_dom_diff.py` | DOM diff unit tests |
| `app/rendering/sandbox/tests/test_smtp.py` | SMTP send tests (mocked) |
| `app/rendering/sandbox/tests/test_sandbox.py` | End-to-end sandbox tests (mocked Playwright + SMTP) |
| `app/rendering/sandbox/tests/test_sandbox_routes.py` | Route tests (auth, feature-flag, happy path) |

## Files to Modify

| File | Change |
|------|--------|
| `app/core/config.py` | Add `SandboxConfig` class, add `sandbox` field to `RenderingConfig` |
| `app/rendering/exceptions.py` | Add `SandboxUnavailableError`, `SandboxSMTPError`, `SandboxCaptureError` |
| `app/rendering/routes.py` | Add sandbox test + health endpoints |
| `app/rendering/schemas.py` | Import sandbox schemas (or keep separate — see below) |
| `pyproject.toml` | Add `aiosmtplib>=2.0` dependency |
| `docker-compose.yml` | Add `mailpit` and `roundcube` services behind `sandbox` profile |

## Implementation Steps

### Step 1: Add `aiosmtplib` dependency

In `pyproject.toml`, add to the main dependencies list:
```python
"aiosmtplib>=2.0",
```

### Step 2: Add `SandboxConfig` to `app/core/config.py`

Insert new config class **before** `RenderingConfig` (around line 202):

```python
class SandboxConfig(BaseModel):
    """Headless email sandbox settings."""

    enabled: bool = False
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    mailpit_url: str = "http://localhost:8025"
    roundcube_url: str = "http://localhost:9080"
    playwright_timeout_ms: int = 15000
    from_addr: str = "sandbox@test.local"
    to_addr: str = "inbox@test.local"
```

Add to `RenderingConfig`:
```python
sandbox: SandboxConfig = SandboxConfig()
```

This enables env vars like `RENDERING__SANDBOX__ENABLED=true`, `RENDERING__SANDBOX__SMTP_HOST=mailpit`, etc.

### Step 3: Add sandbox exceptions to `app/rendering/exceptions.py`

Append after existing exceptions:

```python
class SandboxUnavailableError(ServiceUnavailableError):
    """Raised when sandbox infrastructure (Mailpit/Roundcube) is unreachable."""


class SandboxSMTPError(ServiceUnavailableError):
    """Raised when SMTP send to sandbox mail server fails."""


class SandboxCaptureError(AppError):
    """Raised when Playwright DOM extraction from webmail fails."""
```

### Step 4: Create `app/rendering/sandbox/__init__.py`

```python
```

(Empty init file.)

### Step 5: Create `app/rendering/sandbox/profiles.py`

```python
"""Sandbox webmail profiles for DOM capture."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SandboxProfile:
    """A webmail interface to capture post-sanitizer DOM from."""

    name: str
    webmail_url_template: str  # Use {message_id} placeholder
    content_selector: str  # CSS selector for email body container
    login_required: bool = False
    wait_selector: str | None = None  # Extra selector to wait for before extraction
    browser: str = "cr"  # Playwright browser: "cr", "ff", "wk"


SANDBOX_PROFILES: dict[str, SandboxProfile] = {
    "mailpit": SandboxProfile(
        name="mailpit",
        webmail_url_template="{base_url}/view/{message_id}",
        content_selector=".message-body",
        browser="cr",
    ),
    "roundcube": SandboxProfile(
        name="roundcube",
        webmail_url_template="{base_url}/?_task=mail&_action=show&_uid={message_id}",
        content_selector="#messagebody",
        login_required=True,
        wait_selector="#messagebody .rcmBody",
        browser="cr",
    ),
}


def get_sandbox_profile(name: str) -> SandboxProfile | None:
    """Get a sandbox profile by name."""
    return SANDBOX_PROFILES.get(name)
```

### Step 6: Create `app/rendering/sandbox/smtp.py`

```python
"""Async SMTP client for sending test emails to sandbox mail server."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from email.message import EmailMessage

import aiosmtplib

from app.core.config import get_settings
from app.core.logging import get_logger
from app.rendering.exceptions import SandboxSMTPError

logger = get_logger(__name__)


async def send_test_email(
    html: str,
    subject: str,
    *,
    from_addr: str | None = None,
    to_addr: str | None = None,
) -> str:
    """Send an HTML email to the sandbox mail server via SMTP.

    Returns the Message-ID header value for later retrieval.
    """
    settings = get_settings()
    cfg = settings.rendering.sandbox
    sender = from_addr or cfg.from_addr
    recipient = to_addr or cfg.to_addr

    message_id = f"<{uuid.uuid4().hex}@sandbox.local>"

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject
    msg["Date"] = datetime.now(tz=UTC).strftime("%a, %d %b %Y %H:%M:%S %z")
    msg["Message-ID"] = message_id
    msg["MIME-Version"] = "1.0"
    msg.set_content(subject, subtype="plain")
    msg.add_alternative(html, subtype="html", charset="utf-8")

    try:
        await aiosmtplib.send(
            msg,
            hostname=cfg.smtp_host,
            port=cfg.smtp_port,
            start_tls=False,
            use_tls=False,
        )
    except (aiosmtplib.SMTPException, OSError) as exc:
        raise SandboxSMTPError(
            f"Failed to send email to sandbox SMTP ({cfg.smtp_host}:{cfg.smtp_port}): {exc}"
        ) from exc

    logger.info(
        "sandbox.smtp_sent",
        message_id=message_id,
        host=cfg.smtp_host,
        port=cfg.smtp_port,
    )
    return message_id
```

### Step 7: Create `app/rendering/sandbox/dom_diff.py`

```python
"""DOM diff computation between original and rendered HTML."""

from __future__ import annotations

from dataclasses import dataclass, field

from lxml import html as lxml_html


@dataclass(frozen=True)
class DOMDiff:
    """Structural diff between original and post-sanitizer HTML."""

    removed_elements: list[str] = field(default_factory=list)
    removed_attributes: dict[str, list[str]] = field(default_factory=dict)
    removed_css_properties: dict[str, list[str]] = field(default_factory=dict)
    added_elements: list[str] = field(default_factory=list)
    modified_styles: dict[str, tuple[str, str]] = field(default_factory=dict)


def _parse_inline_style(style: str) -> dict[str, str]:
    """Parse a CSS inline style string into a property→value dict."""
    props: dict[str, str] = {}
    for part in style.split(";"):
        part = part.strip()
        if ":" not in part:
            continue
        key, _, val = part.partition(":")
        props[key.strip().lower()] = val.strip()
    return props


def _collect_elements(root: lxml_html.HtmlElement) -> dict[str, set[str]]:
    """Collect tag→set of XPaths for all elements."""
    elements: dict[str, set[str]] = {}
    for el in root.iter():
        tag = el.tag if isinstance(el.tag, str) else str(el.tag)
        path = root.getroottree().getpath(el)
        elements.setdefault(tag, set()).add(path)
    return elements


def _collect_attributes(root: lxml_html.HtmlElement) -> dict[str, dict[str, str]]:
    """Collect XPath→{attr: value} for all elements."""
    attrs: dict[str, dict[str, str]] = {}
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        path = root.getroottree().getpath(el)
        el_attrs = dict(el.attrib)
        if el_attrs:
            attrs[path] = el_attrs
    return attrs


def compute_dom_diff(original_html: str, rendered_html: str) -> DOMDiff:
    """Compute structural diff between original and rendered HTML.

    Identifies elements removed by sanitizer, stripped attributes,
    removed CSS properties, and style modifications.
    """
    try:
        orig_doc = lxml_html.fragment_fromstring(original_html, create_parent="div")
        rend_doc = lxml_html.fragment_fromstring(rendered_html, create_parent="div")
    except Exception:
        return DOMDiff()

    # Element diff: find tags in original but not rendered
    orig_tags: dict[str, int] = {}
    for el in orig_doc.iter():
        tag = el.tag if isinstance(el.tag, str) else ""
        if tag:
            orig_tags[tag] = orig_tags.get(tag, 0) + 1

    rend_tags: dict[str, int] = {}
    for el in rend_doc.iter():
        tag = el.tag if isinstance(el.tag, str) else ""
        if tag:
            rend_tags[tag] = rend_tags.get(tag, 0) + 1

    removed_elements: list[str] = []
    for tag, count in orig_tags.items():
        rend_count = rend_tags.get(tag, 0)
        if rend_count < count:
            removed_elements.extend([tag] * (count - rend_count))

    added_elements: list[str] = []
    for tag, count in rend_tags.items():
        orig_count = orig_tags.get(tag, 0)
        if count > orig_count:
            added_elements.extend([tag] * (count - orig_count))

    # Attribute diff: compare attributes on elements that exist in both
    orig_attrs = _collect_attributes(orig_doc)
    rend_attrs = _collect_attributes(rend_doc)

    removed_attributes: dict[str, list[str]] = {}
    for path, attrs in orig_attrs.items():
        rend_el_attrs = rend_attrs.get(path, {})
        removed = [a for a in attrs if a not in rend_el_attrs and a != "style"]
        if removed:
            removed_attributes[path] = removed

    # CSS property diff: compare inline styles
    removed_css: dict[str, list[str]] = {}
    modified_styles: dict[str, tuple[str, str]] = {}

    for path, attrs in orig_attrs.items():
        orig_style = attrs.get("style", "")
        rend_style = rend_attrs.get(path, {}).get("style", "")
        if not orig_style:
            continue

        orig_props = _parse_inline_style(orig_style)
        rend_props = _parse_inline_style(rend_style)

        removed_props = [p for p in orig_props if p not in rend_props]
        if removed_props:
            removed_css[path] = removed_props

        for prop, val in orig_props.items():
            if prop in rend_props and rend_props[prop] != val:
                modified_styles[f"{path}::{prop}"] = (val, rend_props[prop])

    return DOMDiff(
        removed_elements=removed_elements,
        removed_attributes=removed_attributes,
        removed_css_properties=removed_css,
        added_elements=added_elements,
        modified_styles=modified_styles,
    )
```

### Step 8: Create `app/rendering/sandbox/schemas.py`

```python
"""Pydantic schemas for sandbox API endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SandboxTestRequest(BaseModel):
    """Request to send email through sandbox and capture results."""

    html: str = Field(..., min_length=1, max_length=500_000)
    subject: str = Field(default="Sandbox Test", max_length=200)
    profiles: list[str] = Field(default=["mailpit"])


class SandboxProfileResult(BaseModel):
    """Result from a single sandbox profile capture."""

    profile: str
    rendered_html: str
    screenshot_base64: str | None = None
    dom_diff: SandboxDOMDiff | None = None


class SandboxDOMDiff(BaseModel):
    """Serializable DOM diff result."""

    removed_elements: list[str] = Field(default_factory=list)
    removed_attributes: dict[str, list[str]] = Field(default_factory=dict)
    removed_css_properties: dict[str, list[str]] = Field(default_factory=dict)
    added_elements: list[str] = Field(default_factory=list)
    modified_styles: dict[str, tuple[str, str]] = Field(default_factory=dict)


class SandboxTestResponse(BaseModel):
    """Response with per-profile sandbox capture results."""

    message_id: str
    results: list[SandboxProfileResult]


class SandboxHealthResponse(BaseModel):
    """Health check for sandbox infrastructure."""

    sandbox_enabled: bool
    mailpit_reachable: bool = False
    roundcube_reachable: bool = False
    smtp_reachable: bool = False
```

**Note:** `SandboxDOMDiff` must be defined before `SandboxProfileResult` in the file since the latter references it. In the code above, use `model_rebuild()` or reorder — best to define `SandboxDOMDiff` first:

Move `SandboxDOMDiff` class above `SandboxProfileResult`.

### Step 9: Create `app/rendering/sandbox/sandbox.py`

```python
"""Email sandbox orchestrator — send, navigate, capture, diff."""

from __future__ import annotations

import asyncio
import base64
import tempfile
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import get_logger
from app.rendering.exceptions import SandboxCaptureError
from app.rendering.sandbox.dom_diff import DOMDiff, compute_dom_diff
from app.rendering.sandbox.profiles import SandboxProfile, get_sandbox_profile
from app.rendering.sandbox.smtp import send_test_email

logger = get_logger(__name__)


async def _wait_for_email_in_mailpit(message_id: str) -> str:
    """Poll Mailpit API until the message appears. Returns Mailpit internal ID."""
    import httpx

    settings = get_settings()
    base_url = settings.rendering.sandbox.mailpit_url
    timeout_ms = settings.rendering.sandbox.playwright_timeout_ms

    deadline = asyncio.get_event_loop().time() + timeout_ms / 1000
    while asyncio.get_event_loop().time() < deadline:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{base_url}/api/v1/messages", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                for msg in data.get("messages", []):
                    if msg.get("MessageID") == message_id:
                        return msg["ID"]
        await asyncio.sleep(0.5)
    raise SandboxCaptureError(f"Email {message_id} not found in Mailpit within {timeout_ms}ms")


async def _capture_mailpit_html(mailpit_id: str) -> str:
    """Fetch rendered HTML directly from Mailpit API (no Playwright needed)."""
    import httpx

    settings = get_settings()
    base_url = settings.rendering.sandbox.mailpit_url

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{base_url}/api/v1/message/{mailpit_id}/html", timeout=10)
        if resp.status_code != 200:
            raise SandboxCaptureError(f"Mailpit HTML fetch failed: HTTP {resp.status_code}")
        return resp.text


async def _capture_with_playwright(
    profile: SandboxProfile,
    mailpit_id: str,
) -> tuple[str, bytes | None]:
    """Open webmail in Playwright, extract DOM and optional screenshot.

    Returns (rendered_html, screenshot_bytes | None).
    """
    from playwright.async_api import async_playwright

    settings = get_settings()
    timeout = settings.rendering.sandbox.playwright_timeout_ms

    base_url_map = {
        "mailpit": settings.rendering.sandbox.mailpit_url,
        "roundcube": settings.rendering.sandbox.roundcube_url,
    }
    base_url = base_url_map.get(profile.name, settings.rendering.sandbox.mailpit_url)

    url = profile.webmail_url_template.format(
        base_url=base_url,
        message_id=mailpit_id,
    )

    async with async_playwright() as p:
        browser_launcher = {
            "cr": p.chromium,
            "ff": p.firefox,
            "wk": p.webkit,
        }.get(profile.browser, p.chromium)

        browser = await browser_launcher.launch(headless=True)
        try:
            page = await browser.new_page()
            page.set_default_timeout(timeout)

            await page.goto(url, wait_until="networkidle")

            if profile.wait_selector:
                await page.wait_for_selector(profile.wait_selector, timeout=timeout)
            else:
                await page.wait_for_selector(profile.content_selector, timeout=timeout)

            rendered_html = await page.eval_on_selector(
                profile.content_selector,
                "el => el.innerHTML",
            )

            # Capture screenshot
            screenshot: bytes | None = None
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                screenshot_path = Path(f.name)
            try:
                element = await page.query_selector(profile.content_selector)
                if element:
                    screenshot = await element.screenshot(type="png")
                else:
                    screenshot = await page.screenshot(full_page=True, type="png")
            except Exception as exc:
                logger.warning("sandbox.screenshot_failed", profile=profile.name, error=str(exc))
            finally:
                try:
                    screenshot_path.unlink(missing_ok=True)
                except OSError:
                    pass

            return rendered_html, screenshot
        finally:
            await browser.close()


async def send_and_capture(
    html: str,
    subject: str,
    profile_names: list[str],
) -> tuple[str, list[tuple[str, str, bytes | None, DOMDiff | None]]]:
    """Send email to sandbox and capture rendered DOM from each profile.

    Returns:
        (message_id, [(profile_name, rendered_html, screenshot, dom_diff), ...])
    """
    settings = get_settings()

    # Send email via SMTP
    message_id = await send_test_email(html, subject)

    # Wait for Mailpit to receive it
    mailpit_id = await _wait_for_email_in_mailpit(message_id)

    results: list[tuple[str, str, bytes | None, DOMDiff | None]] = []

    for name in profile_names:
        profile = get_sandbox_profile(name)
        if not profile:
            logger.warning("sandbox.unknown_profile", profile=name)
            continue

        try:
            if name == "mailpit":
                # Mailpit: use API directly (no sanitization — baseline)
                rendered = await _capture_mailpit_html(mailpit_id)
                screenshot: bytes | None = None
            else:
                # Webmail clients: use Playwright for real sanitizer capture
                rendered, screenshot = await _capture_with_playwright(profile, mailpit_id)

            dom_diff = compute_dom_diff(html, rendered)

            results.append((name, rendered, screenshot, dom_diff))

            logger.info(
                "sandbox.capture_completed",
                profile=name,
                removed_elements=len(dom_diff.removed_elements),
                removed_css=sum(len(v) for v in dom_diff.removed_css_properties.values()),
            )
        except Exception as exc:
            logger.error("sandbox.capture_failed", profile=name, error=str(exc))
            raise SandboxCaptureError(
                f"Sandbox capture failed for profile '{name}': {exc}"
            ) from exc

    return message_id, results
```

### Step 10: Create `app/rendering/sandbox/service.py`

```python
"""Sandbox service — business logic with feature-flag gating."""

from __future__ import annotations

import base64

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.rendering.exceptions import SandboxUnavailableError
from app.rendering.sandbox.sandbox import send_and_capture
from app.rendering.sandbox.schemas import (
    SandboxDOMDiff,
    SandboxHealthResponse,
    SandboxProfileResult,
    SandboxTestRequest,
    SandboxTestResponse,
)

logger = get_logger(__name__)


def _require_sandbox_enabled() -> None:
    """Raise if sandbox is disabled."""
    if not get_settings().rendering.sandbox.enabled:
        raise SandboxUnavailableError("Email sandbox is disabled (RENDERING__SANDBOX__ENABLED=false)")


async def run_sandbox_test(data: SandboxTestRequest) -> SandboxTestResponse:
    """Send email through sandbox and return capture results."""
    _require_sandbox_enabled()

    message_id, captures = await send_and_capture(
        html=data.html,
        subject=data.subject,
        profile_names=data.profiles,
    )

    results: list[SandboxProfileResult] = []
    for profile_name, rendered_html, screenshot, dom_diff in captures:
        screenshot_b64 = base64.b64encode(screenshot).decode() if screenshot else None
        diff_schema = None
        if dom_diff:
            diff_schema = SandboxDOMDiff(
                removed_elements=dom_diff.removed_elements,
                removed_attributes=dom_diff.removed_attributes,
                removed_css_properties=dom_diff.removed_css_properties,
                added_elements=dom_diff.added_elements,
                modified_styles=dom_diff.modified_styles,
            )
        results.append(
            SandboxProfileResult(
                profile=profile_name,
                rendered_html=rendered_html,
                screenshot_base64=screenshot_b64,
                dom_diff=diff_schema,
            )
        )

    return SandboxTestResponse(message_id=message_id, results=results)


async def check_sandbox_health() -> SandboxHealthResponse:
    """Check availability of sandbox infrastructure."""
    settings = get_settings()
    cfg = settings.rendering.sandbox

    if not cfg.enabled:
        return SandboxHealthResponse(sandbox_enabled=False)

    mailpit_ok = False
    roundcube_ok = False
    smtp_ok = False

    async with httpx.AsyncClient(timeout=5) as client:
        # Check Mailpit web UI
        try:
            resp = await client.get(f"{cfg.mailpit_url}/api/v1/messages")
            mailpit_ok = resp.status_code == 200
        except (httpx.HTTPError, OSError):
            pass

        # Check Roundcube
        try:
            resp = await client.get(cfg.roundcube_url)
            roundcube_ok = resp.status_code in (200, 302)  # 302 = redirect to login
        except (httpx.HTTPError, OSError):
            pass

    # Check SMTP connectivity
    try:
        import aiosmtplib

        smtp = aiosmtplib.SMTP(hostname=cfg.smtp_host, port=cfg.smtp_port)
        await smtp.connect()
        await smtp.quit()
        smtp_ok = True
    except Exception:
        pass

    return SandboxHealthResponse(
        sandbox_enabled=True,
        mailpit_reachable=mailpit_ok,
        roundcube_reachable=roundcube_ok,
        smtp_reachable=smtp_ok,
    )
```

### Step 11: Add sandbox routes to `app/rendering/routes.py`

Add imports at the top of `routes.py`:

```python
from app.rendering.sandbox.schemas import (
    SandboxHealthResponse,
    SandboxTestRequest,
    SandboxTestResponse,
)
from app.rendering.sandbox.service import check_sandbox_health, run_sandbox_test
```

Add two new endpoints at the end of the file (before the closing):

```python
@router.post("/sandbox/test", response_model=SandboxTestResponse)
@limiter.limit("5/minute")
async def sandbox_test(
    request: Request,
    data: SandboxTestRequest,
    _current_user: User = Depends(require_role("admin")),  # noqa: B008
) -> SandboxTestResponse:
    """Send email to sandbox, capture rendered DOM and screenshots."""
    _ = request
    return await run_sandbox_test(data)


@router.get("/sandbox/health", response_model=SandboxHealthResponse)
@limiter.limit("30/minute")
async def sandbox_health(
    request: Request,
    _current_user: User = Depends(require_role("admin")),  # noqa: B008
) -> SandboxHealthResponse:
    """Check sandbox infrastructure availability."""
    _ = request
    return await check_sandbox_health()
```

### Step 12: Add Docker Compose sandbox profile services

Append to `docker-compose.yml` before `networks:`:

```yaml
  mailpit:
    image: axllent/mailpit:latest
    ports:
      - "8025:8025"   # Web UI
      - "1025:1025"   # SMTP
    environment:
      MP_SMTP_AUTH_ACCEPT_ANY: 1
      MP_MAX_MESSAGES: 1000
    profiles:
      - sandbox
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    deploy:
      resources:
        limits:
          cpus: "0.25"
          memory: 128M

  roundcube:
    image: roundcube/roundcubemail:latest
    ports:
      - "9080:80"
    environment:
      ROUNDCUBEMAIL_DEFAULT_HOST: mailpit
      ROUNDCUBEMAIL_DEFAULT_PORT: 1025
      ROUNDCUBEMAIL_SMTP_SERVER: mailpit
      ROUNDCUBEMAIL_SMTP_PORT: 1025
    depends_on:
      - mailpit
    profiles:
      - sandbox
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    deploy:
      resources:
        limits:
          cpus: "0.25"
          memory: 128M
```

### Step 13: Create tests

#### `app/rendering/sandbox/tests/__init__.py`

Empty file.

#### `app/rendering/sandbox/tests/test_dom_diff.py`

```python
"""Unit tests for DOM diff computation."""

from __future__ import annotations

import pytest

from app.rendering.sandbox.dom_diff import DOMDiff, compute_dom_diff, _parse_inline_style


class TestParseInlineStyle:
    def test_simple(self) -> None:
        result = _parse_inline_style("color: red; font-size: 14px")
        assert result == {"color": "red", "font-size": "14px"}

    def test_empty(self) -> None:
        assert _parse_inline_style("") == {}

    def test_trailing_semicolon(self) -> None:
        result = _parse_inline_style("margin: 0;")
        assert result == {"margin": "0"}


class TestComputeDomDiff:
    def test_identical(self) -> None:
        html = '<table><tr><td style="color:red">Hello</td></tr></table>'
        diff = compute_dom_diff(html, html)
        assert diff.removed_elements == []
        assert diff.removed_attributes == {}
        assert diff.removed_css_properties == {}

    def test_removed_element(self) -> None:
        original = "<div><style>body{color:red}</style><p>Hello</p></div>"
        rendered = "<div><p>Hello</p></div>"
        diff = compute_dom_diff(original, rendered)
        assert "style" in diff.removed_elements

    def test_removed_css_property(self) -> None:
        original = '<td style="color: red; position: absolute">text</td>'
        rendered = '<td style="color: red">text</td>'
        diff = compute_dom_diff(original, rendered)
        # position was removed from at least one element
        removed_props = [p for props in diff.removed_css_properties.values() for p in props]
        assert "position" in removed_props

    def test_modified_style(self) -> None:
        original = '<td style="margin: 10px">text</td>'
        rendered = '<td style="margin: 0">text</td>'
        diff = compute_dom_diff(original, rendered)
        assert any("margin" in k for k in diff.modified_styles)

    def test_invalid_html_returns_empty_diff(self) -> None:
        diff = compute_dom_diff("", "")
        assert isinstance(diff, DOMDiff)

    def test_added_elements(self) -> None:
        original = "<div><p>Hello</p></div>"
        rendered = "<div><p>Hello</p><span>Added</span></div>"
        diff = compute_dom_diff(original, rendered)
        assert "span" in diff.added_elements

    def test_removed_attribute(self) -> None:
        original = '<img src="test.png" alt="test" data-custom="val">'
        rendered = '<img src="test.png" alt="test">'
        diff = compute_dom_diff(original, rendered)
        removed = [a for attrs in diff.removed_attributes.values() for a in attrs]
        assert "data-custom" in removed
```

#### `app/rendering/sandbox/tests/test_smtp.py`

```python
"""Unit tests for sandbox SMTP sender (mocked — no real SMTP)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.rendering.exceptions import SandboxSMTPError
from app.rendering.sandbox.smtp import send_test_email


@pytest.fixture(autouse=True)
def _sandbox_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure sandbox settings for tests."""
    monkeypatch.setenv("RENDERING__SANDBOX__ENABLED", "true")
    monkeypatch.setenv("RENDERING__SANDBOX__SMTP_HOST", "localhost")
    monkeypatch.setenv("RENDERING__SANDBOX__SMTP_PORT", "1025")


class TestSendTestEmail:
    @patch("app.rendering.sandbox.smtp.aiosmtplib.send", new_callable=AsyncMock)
    async def test_send_success(self, mock_send: AsyncMock) -> None:
        mock_send.return_value = ({}, "OK")
        message_id = await send_test_email("<p>Hello</p>", "Test Subject")
        assert message_id.startswith("<")
        assert message_id.endswith("@sandbox.local>")
        mock_send.assert_called_once()

    @patch("app.rendering.sandbox.smtp.aiosmtplib.send", new_callable=AsyncMock)
    async def test_send_failure_raises(self, mock_send: AsyncMock) -> None:
        import aiosmtplib

        mock_send.side_effect = aiosmtplib.SMTPException("Connection refused")
        with pytest.raises(SandboxSMTPError, match="Connection refused"):
            await send_test_email("<p>Hello</p>", "Test")

    @patch("app.rendering.sandbox.smtp.aiosmtplib.send", new_callable=AsyncMock)
    async def test_custom_addresses(self, mock_send: AsyncMock) -> None:
        mock_send.return_value = ({}, "OK")
        await send_test_email(
            "<p>Hi</p>",
            "Custom",
            from_addr="custom@test.local",
            to_addr="recv@test.local",
        )
        call_args = mock_send.call_args
        msg = call_args[0][0]
        assert msg["From"] == "custom@test.local"
        assert msg["To"] == "recv@test.local"
```

#### `app/rendering/sandbox/tests/test_sandbox.py`

```python
"""Integration tests for sandbox orchestrator (mocked Playwright + SMTP)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.rendering.exceptions import SandboxCaptureError
from app.rendering.sandbox.sandbox import send_and_capture


@pytest.fixture(autouse=True)
def _sandbox_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RENDERING__SANDBOX__ENABLED", "true")
    monkeypatch.setenv("RENDERING__SANDBOX__SMTP_HOST", "localhost")
    monkeypatch.setenv("RENDERING__SANDBOX__SMTP_PORT", "1025")
    monkeypatch.setenv("RENDERING__SANDBOX__MAILPIT_URL", "http://localhost:8025")


class TestSendAndCapture:
    @patch("app.rendering.sandbox.sandbox.send_test_email", new_callable=AsyncMock)
    @patch("app.rendering.sandbox.sandbox._wait_for_email_in_mailpit", new_callable=AsyncMock)
    @patch("app.rendering.sandbox.sandbox._capture_mailpit_html", new_callable=AsyncMock)
    async def test_mailpit_profile(
        self,
        mock_capture: AsyncMock,
        mock_wait: AsyncMock,
        mock_send: AsyncMock,
    ) -> None:
        mock_send.return_value = "<abc123@sandbox.local>"
        mock_wait.return_value = "mp-id-1"
        mock_capture.return_value = '<table><tr><td style="color:red">Hello</td></tr></table>'

        original_html = '<table><tr><td style="color:red">Hello</td></tr></table>'
        message_id, results = await send_and_capture(
            html=original_html,
            subject="Test",
            profile_names=["mailpit"],
        )

        assert message_id == "<abc123@sandbox.local>"
        assert len(results) == 1
        name, rendered, screenshot, dom_diff = results[0]
        assert name == "mailpit"
        assert rendered == original_html
        assert screenshot is None  # Mailpit uses API, no Playwright
        assert dom_diff is not None
        assert dom_diff.removed_elements == []  # Identical HTML

    @patch("app.rendering.sandbox.sandbox.send_test_email", new_callable=AsyncMock)
    @patch("app.rendering.sandbox.sandbox._wait_for_email_in_mailpit", new_callable=AsyncMock)
    @patch("app.rendering.sandbox.sandbox._capture_mailpit_html", new_callable=AsyncMock)
    async def test_mailpit_with_sanitizer_diff(
        self,
        mock_capture: AsyncMock,
        mock_wait: AsyncMock,
        mock_send: AsyncMock,
    ) -> None:
        mock_send.return_value = "<abc@sandbox.local>"
        mock_wait.return_value = "mp-2"
        # Simulate sanitizer stripping <style> block
        mock_capture.return_value = "<div><p>Hello</p></div>"

        message_id, results = await send_and_capture(
            html="<div><style>p{color:red}</style><p>Hello</p></div>",
            subject="Test",
            profile_names=["mailpit"],
        )

        _, _, _, dom_diff = results[0]
        assert dom_diff is not None
        assert "style" in dom_diff.removed_elements

    async def test_unknown_profile_skipped(self) -> None:
        with patch("app.rendering.sandbox.sandbox.send_test_email", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = "<x@sandbox.local>"
            with patch("app.rendering.sandbox.sandbox._wait_for_email_in_mailpit", new_callable=AsyncMock) as mock_wait:
                mock_wait.return_value = "mp-3"
                _, results = await send_and_capture(
                    html="<p>Hi</p>",
                    subject="T",
                    profile_names=["nonexistent"],
                )
                assert len(results) == 0
```

#### `app/rendering/sandbox/tests/test_sandbox_routes.py`

```python
"""Route tests for sandbox endpoints — auth, feature-flag, happy path."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.rate_limit import limiter
from app.main import app
from app.rendering.exceptions import SandboxUnavailableError
from app.rendering.sandbox.schemas import (
    SandboxDOMDiff,
    SandboxHealthResponse,
    SandboxProfileResult,
    SandboxTestResponse,
)

BASE = "/api/v1/rendering/sandbox"


def _make_user(role: str = "admin") -> User:
    user = User(email="admin@example.com", hashed_password="x", role=role)
    user.id = 1
    return user


@pytest.fixture(autouse=True)
def _disable_rate_limit() -> Generator[None, None, None]:
    limiter.enabled = False
    yield
    limiter.enabled = True


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


class TestSandboxTestEndpoint:
    def test_requires_admin(self, client: TestClient) -> None:
        viewer = _make_user(role="viewer")
        app.dependency_overrides[get_current_user] = lambda: viewer
        try:
            resp = client.post(f"{BASE}/test", json={"html": "<p>Hi</p>"})
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_rejects_unauthenticated(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/test", json={"html": "<p>Hi</p>"})
        assert resp.status_code in (401, 403)

    @patch("app.rendering.sandbox.service.run_sandbox_test", new_callable=AsyncMock)
    def test_happy_path(self, mock_run: AsyncMock, client: TestClient) -> None:
        admin = _make_user(role="admin")
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            mock_run.return_value = SandboxTestResponse(
                message_id="<test@sandbox.local>",
                results=[
                    SandboxProfileResult(
                        profile="mailpit",
                        rendered_html="<p>Hi</p>",
                        dom_diff=SandboxDOMDiff(),
                    )
                ],
            )
            resp = client.post(f"{BASE}/test", json={"html": "<p>Hi</p>", "profiles": ["mailpit"]})
            assert resp.status_code == 200
            body = resp.json()
            assert body["message_id"] == "<test@sandbox.local>"
            assert len(body["results"]) == 1
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    @patch("app.rendering.sandbox.service.run_sandbox_test", new_callable=AsyncMock)
    def test_disabled_returns_503(self, mock_run: AsyncMock, client: TestClient) -> None:
        admin = _make_user(role="admin")
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            mock_run.side_effect = SandboxUnavailableError("Sandbox disabled")
            resp = client.post(f"{BASE}/test", json={"html": "<p>Hi</p>"})
            assert resp.status_code == 503
        finally:
            app.dependency_overrides.pop(get_current_user, None)


class TestSandboxHealthEndpoint:
    def test_requires_admin(self, client: TestClient) -> None:
        viewer = _make_user(role="viewer")
        app.dependency_overrides[get_current_user] = lambda: viewer
        try:
            resp = client.get(f"{BASE}/health")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    @patch("app.rendering.sandbox.service.check_sandbox_health", new_callable=AsyncMock)
    def test_disabled_sandbox(self, mock_health: AsyncMock, client: TestClient) -> None:
        admin = _make_user(role="admin")
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            mock_health.return_value = SandboxHealthResponse(sandbox_enabled=False)
            resp = client.get(f"{BASE}/health")
            assert resp.status_code == 200
            assert resp.json()["sandbox_enabled"] is False
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    @patch("app.rendering.sandbox.service.check_sandbox_health", new_callable=AsyncMock)
    def test_healthy_sandbox(self, mock_health: AsyncMock, client: TestClient) -> None:
        admin = _make_user(role="admin")
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            mock_health.return_value = SandboxHealthResponse(
                sandbox_enabled=True,
                mailpit_reachable=True,
                roundcube_reachable=True,
                smtp_reachable=True,
            )
            resp = client.get(f"{BASE}/health")
            assert resp.status_code == 200
            body = resp.json()
            assert body["sandbox_enabled"] is True
            assert body["mailpit_reachable"] is True
        finally:
            app.dependency_overrides.pop(get_current_user, None)
```

### Step 14: Wire into `app/main.py` (if needed)

The sandbox routes are part of the existing `rendering` router, so no additional include is needed — they're already served under `/api/v1/rendering/sandbox/*`.

## Security Checklist

### `POST /api/v1/rendering/sandbox/test`
- **Auth:** `require_role("admin")` — admin only
- **Rate limiting:** `@limiter.limit("5/minute")`
- **Input validation:** Pydantic model with `max_length=500_000` on HTML, `max_length=200` on subject, list of profile names (validated against `SANDBOX_PROFILES` in orchestrator)
- **Error responses:** `SandboxUnavailableError` → 503 (via global handler), `SandboxSMTPError` → 503, `SandboxCaptureError` → generic message, no stack traces
- **BOLA/IDOR:** No resource IDs — sandbox is stateless, no tenant data
- **Injection:** HTML is sent to Mailpit SMTP (local), not executed server-side. Playwright runs headless in a sandboxed browser. No SQL, no shell commands
- **Data exposure:** Sandbox is ephemeral — Mailpit stores in memory by default. No persistent storage of email content
- **Network isolation:** SMTP to localhost only. Playwright connects to localhost webmail only. No external network requests

### `GET /api/v1/rendering/sandbox/health`
- **Auth:** `require_role("admin")` — admin only
- **Rate limiting:** `@limiter.limit("30/minute")`
- **Error responses:** Always returns 200 with health status (no internal errors leaked)
- **Network:** Health checks connect to local services only (Mailpit, Roundcube, SMTP)

### Docker services
- **`mailpit`:** `no-new-privileges`, all capabilities dropped, 128M memory limit, `profiles: [sandbox]` (not started by default)
- **`roundcube`:** Same hardening, `profiles: [sandbox]`
- **Credentials:** Roundcube credentials (if login required) via env vars, never in code. Mailpit accepts any auth (`MP_SMTP_AUTH_ACCEPT_ANY`)

## Verification

- [ ] `make check` passes (lint + types + tests + security)
- [ ] `RENDERING__SANDBOX__ENABLED=false` → sandbox endpoints return 503
- [ ] `RENDERING__SANDBOX__ENABLED=true` + no Docker → health returns `sandbox_enabled=true`, all services unreachable
- [ ] `docker compose --profile sandbox up` → Mailpit on 8025, Roundcube on 9080, SMTP on 1025
- [ ] Sandbox test endpoint sends email, captures DOM, returns diff
- [ ] DOM diff correctly identifies stripped elements and CSS properties
- [ ] All sandbox tests pass with mocked SMTP/Playwright (no Docker dependency)
- [ ] Admin-only access enforced on both endpoints
- [ ] Rate limiting active on both endpoints
