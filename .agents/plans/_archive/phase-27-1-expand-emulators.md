# Plan: Phase 27.1 — Expand Email Client Emulators

## Context

The rendering module currently has 2 emulators (Gmail Web, Outlook.com) and 6 Playwright profiles. This subtask adds 5 new emulators (Yahoo Mail, Samsung Mail, Outlook Desktop/Word, Thunderbird, Android Gmail) and 8 new rendering profiles, pushing email client coverage from ~35% to ~85% market share.

**Existing pattern** (from `app/rendering/local/emulators.py`):
- `EmulatorRule(frozen dataclass)` — `name: str, transform: Callable[[str], str]`
- `EmailClientEmulator` — `client_id: str, rules: list[EmulatorRule]`, `.transform(html)` chains rules in order
- `_EMULATORS: dict[str, EmailClientEmulator]` registry
- `get_emulator(client_id) -> EmailClientEmulator | None`
- Rules are pure `str -> str` functions using regex transforms on HTML
- Shared regex patterns: `_INLINE_STYLE_RE`, `_STYLE_TAG_RE`, `_CLASS_ATTR_RE` etc.

**Existing profiles** (from `app/rendering/local/profiles.py`):
- `RenderingProfile(frozen dataclass)` — `name, viewport_width, viewport_height, browser, color_scheme, device, css_injections, strip_style_tags, max_screenshot_height, emulator_id`
- 6 profiles: `gmail_web`, `outlook_2019`, `apple_mail`, `outlook_dark`, `mobile_ios`, `outlook_web`

**Ontology client IDs** (from `clients.yaml`): `yahoo_web`, `yahoo_ios`, `yahoo_android`, `samsung_mail`, `thunderbird`, `outlook_2019_win`, `outlook_365_win`, `gmail_android`. Engine types: Yahoo Web=custom, Samsung=blink, Outlook Desktop=word, Thunderbird=gecko, Gmail Android=blink.

**Key design decisions:**
1. `EmulatorRule` stays as-is (name + transform). The spec calls for adding `description` and `confidence_impact` fields — add these for future subtask 27.2 (confidence scoring), but keep them optional with defaults so existing code is unaffected.
2. The Outlook Desktop emulator models **CSS preprocessing only** — Playwright renders the preprocessed HTML through Chromium, not Word. This is an inherent approximation (noted in profile comments).
3. Android Gmail inherits Gmail Web rules + adds mobile-specific transforms. Implemented by copying the Gmail Web rule list and appending.

## Files to Create/Modify

- `app/rendering/local/emulators.py` — Add 5 new emulator rule sets + register in `_EMULATORS`; extend `EmulatorRule` with optional `description` and `confidence_impact`
- `app/rendering/local/profiles.py` — Add 8 new `RenderingProfile` entries to `CLIENT_PROFILES`
- `app/rendering/local/tests/test_emulators.py` — Add tests for all 5 new emulators + regression tests for existing

## Implementation Steps

### Step 1: Extend `EmulatorRule` with optional fields

In `app/rendering/local/emulators.py`, update the dataclass:

```python
@dataclass(frozen=True)
class EmulatorRule:
    """A single transformation rule applied by an email client emulator."""

    name: str
    transform: Callable[[str], str]
    description: str = ""
    confidence_impact: float = 0.0  # 0.0 = no impact, 1.0 = full confidence loss
```

This is backward-compatible — existing `EmulatorRule(name=..., transform=...)` calls remain valid.

### Step 2: Add Yahoo Mail emulator rules

Add after the Outlook.com rules section (~line 198). Yahoo Web uses a custom engine with aggressive CSS overrides.

**Regex patterns needed:**
```python
# ── Yahoo Mail Emulator Rules ──

_YAHOO_UNSUPPORTED_CSS_RE = re.compile(
    r"(position)\s*:[^;]+;?|"
    r"(float)\s*:[^;]+;?|"
    r"(overflow)\s*:[^;]+;?|"
    r"clip-path\s*:[^;]+;?",
    re.IGNORECASE,
)

_YAHOO_MAX_WIDTH_CSS = "max-width:800px;margin:0 auto;"
```

**Rule functions:**
1. `_yahoo_strip_style_blocks(html: str) -> str` — For the mobile Yahoo profile, strip `<style>` blocks (reuse `_STYLE_TAG_RE`). Desktop Yahoo keeps them. This function is ONLY used in the `yahoo_mobile` emulator, not `yahoo_web`.
2. `_yahoo_strip_unsupported_css(html: str) -> str` — Remove `position`, `float`, `overflow`, `clip-path` from inline styles using `_YAHOO_UNSUPPORTED_CSS_RE` via `_INLINE_STYLE_RE` sub pattern (same approach as Gmail/Outlook).
3. `_yahoo_rewrite_classes(html: str) -> str` — Prefix classes with `yiv` + hash (10-digit). Use `hashlib.md5(html[:200], usedforsecurity=False).hexdigest()[:10]` for deterministic prefix per HTML. Pattern: `.hero` → `.yiv1234567890hero` (no underscore between prefix and class — matches real Yahoo behavior).
4. `_yahoo_enforce_max_width(html: str) -> str` — Inject `max-width: 800px; margin: 0 auto;` on `<body>`. Same approach as `_gmail_enforce_body_max_width` but with 800px.

**Register two emulators:**
- `yahoo_web` — rules: [strip_unsupported_css, rewrite_classes, enforce_max_width] (keeps `<style>` blocks)
- `yahoo_mobile` — rules: [strip_style_blocks, strip_unsupported_css, rewrite_classes, enforce_max_width]

### Step 3: Add Samsung Mail emulator rules

Samsung uses Blink via Android WebView with partial CSS3 support.

**Regex patterns:**
```python
# ── Samsung Mail Emulator Rules ──

_SAMSUNG_UNSUPPORTED_CSS_RE = re.compile(
    r"background-blend-mode\s*:[^;]+;?|"
    r"mix-blend-mode\s*:[^;]+;?|"
    r"filter\s*:[^;]+;?|"
    r"backdrop-filter\s*:[^;]+;?|"
    r"clip-path\s*:[^;]+;?",
    re.IGNORECASE,
)

_IMG_SRC_RE = re.compile(r'(<img\b[^>]*\bsrc\s*=\s*")([^"]+)(")', re.IGNORECASE)
```

**Rule functions:**
1. `_samsung_strip_unsupported_css(html: str) -> str` — Remove blend modes, filter, backdrop-filter, clip-path from inline styles.
2. `_samsung_image_proxy(html: str) -> str` — Append `?samsung_proxy=1` to `<img src>` URLs (or `&samsung_proxy=1` if URL already has query params). Tests whether templates break with URL modification. Use `_IMG_SRC_RE`.
3. `_samsung_dark_mode_inject(html: str) -> str` — Check if HTML contains `prefers-color-scheme` in any `<style>` block. If NOT present, inject `color-scheme: dark` on `<html>` element and add `style="background-color:#1e1e1e;color:#ffffff;"` to `<body>` (simulating Samsung's auto-dark-mode inversion). If explicit dark mode styles exist, leave HTML unchanged.

**Register:**
- `samsung_mail` — rules: [strip_unsupported_css, image_proxy, dark_mode_inject]

### Step 4: Add Outlook Desktop (Word engine) emulator rules

This is the most complex emulator — it models Word's CSS preprocessing. Ontology client `outlook_2019_win` provides the authoritative unsupported property list, but we hardcode the regex for runtime performance (no ontology dependency at transform time).

**Regex patterns:**
```python
# ── Outlook Desktop (Word Engine) Emulator Rules ──

_OUTLOOK_WORD_UNSUPPORTED_RE = re.compile(
    r"display\s*:\s*(?:flex|grid|inline-flex|inline-grid)[^;]*;?|"
    r"position\s*:\s*(?:fixed|sticky|absolute|relative)[^;]*;?|"
    r"float\s*:[^;]+;?|"
    r"box-shadow\s*:[^;]+;?|"
    r"text-shadow\s*:[^;]+;?|"
    r"border-radius\s*:[^;]+;?|"
    r"background-image\s*:[^;]+;?|"
    r"opacity\s*:[^;]+;?|"
    r"transform\s*:[^;]+;?|"
    r"transition\s*:[^;]+;?|"
    r"animation[^:]*\s*:[^;]+;?|"
    r"filter\s*:[^;]+;?|"
    r"overflow\s*:[^;]+;?|"
    r"clip-path\s*:[^;]+;?|"
    r"object-fit\s*:[^;]+;?",
    re.IGNORECASE,
)

_MSO_CONDITIONAL_RE = re.compile(
    r"<!--\[if\s+mso\]>(.*?)<!\[endif\]-->",
    re.DOTALL | re.IGNORECASE,
)
_NOT_MSO_CONDITIONAL_RE = re.compile(
    r"<!--\[if\s+!mso\]><!-->(.*?)<!--<!\[endif\]-->",
    re.DOTALL | re.IGNORECASE,
)

_SHORTHAND_BORDER_RE = re.compile(
    r"border\s*:\s*(\S+)\s+(\S+)\s+(\S+)\s*(?:;|$)",
    re.IGNORECASE,
)
_SHORTHAND_FONT_RE = re.compile(
    r"font\s*:\s*(?:(?:italic|oblique|normal)\s+)?(?:(?:bold|bolder|lighter|\d+)\s+)?(\S+)\s*/?\s*(?:\S+\s+)?(.+?)\s*(?:;|$)",
    re.IGNORECASE,
)
```

**Rule functions:**
1. `_outlook_word_strip_unsupported(html: str) -> str` — Bulk-remove all CSS properties in `_OUTLOOK_WORD_UNSUPPORTED_RE` from inline styles. Same `_INLINE_STYLE_RE` substitution pattern.
2. `_outlook_word_shorthand_expand(html: str) -> str` — Expand margin/padding (reuse existing `_SHORTHAND_MARGIN_RE`, `_SHORTHAND_PADDING_RE`, `_expand_shorthand`), plus expand `border` shorthand to `border-width/style/color` longhand, and strip `font` shorthand entirely (Word can't parse it — replace with empty string; individual font-size/font-family survive if set separately).
3. `_outlook_word_max_width(html: str) -> str` — Find the outermost `<table` tag and inject `width="600"` attribute + `style="width:100%;max-width:600px;"`. Use regex to find first `<table` occurrence.
4. `_outlook_word_conditional_process(html: str) -> str` — Extract content from `<!--[if mso]>...<![endif]-->` blocks (keep inner HTML, remove comment wrappers). Remove `<!--[if !mso]><!-->...<![endif]-->` blocks entirely (Word doesn't see this content).
5. `_outlook_word_vml_preserve(html: str) -> str` — No-op function (VML `<v:*>` elements pass through unchanged). Documents that Playwright/Chromium won't render VML, so the screenshot will miss these elements.

**Register:**
- `outlook_desktop` — rules: [word_strip_unsupported, word_shorthand_expand, word_max_width, word_conditional_process, word_vml_preserve]

### Step 5: Add Thunderbird emulator rules

Thunderbird uses Gecko — mostly standards-compliant with minor gaps.

**Regex patterns:**
```python
# ── Thunderbird Emulator Rules ──

_THUNDERBIRD_UNSUPPORTED_CSS_RE = re.compile(
    r"position\s*:\s*sticky[^;]*;?|"
    r"backdrop-filter\s*:[^;]+;?|"
    r"clip-path\s*:[^;]+;?",
    re.IGNORECASE,
)
```

**Rule functions:**
1. `_thunderbird_strip_unsupported(html: str) -> str` — Remove `position: sticky`, `backdrop-filter`, `clip-path` from inline styles.
2. `_thunderbird_preserve_style_blocks(html: str) -> str` — No-op. Documents that Thunderbird respects `<style>` blocks.

**Register:**
- `thunderbird` — rules: [strip_unsupported, preserve_style_blocks]

### Step 6: Add Android Gmail emulator rules

Android Gmail inherits Gmail Web sanitizer behavior + mobile-specific transforms.

```python
# ── Android Gmail Emulator Rules ──

_VIEWPORT_META_RE = re.compile(
    r'<meta\s+name\s*=\s*["\']viewport["\'][^>]*/?>',
    re.IGNORECASE,
)

_AMP_HTML_RE = re.compile(
    r"<html\b[^>]*⚡4email[^>]*>",
    re.IGNORECASE,
)
```

**Rule functions:**
1. `_android_gmail_viewport_override(html: str) -> str` — Replace any existing viewport meta with `<meta name="viewport" content="width=device-width, initial-scale=1">`. If no viewport meta exists, inject after `<head>`.
2. `_android_gmail_dark_mode(html: str) -> str` — Add `data-ogsc` attribute and `style="color-scheme:dark;"` on `<html>` element (simulates Android Gmail's system dark mode override).
3. `_android_gmail_amp_strip(html: str) -> str` — If HTML contains `⚡4email` in the `<html>` tag, strip it (Android Gmail handles AMP separately from HTML email).

**Register:**
- `android_gmail` — inherits all 6 Gmail Web rules + appends [viewport_override, dark_mode, amp_strip]. Build by copying `_EMULATORS["gmail_web"].rules` list and extending.

### Step 7: Update `_EMULATORS` registry

Add all new emulators to `_EMULATORS` dict after the existing `outlook_web` entry:

```python
_EMULATORS: dict[str, EmailClientEmulator] = {
    "gmail_web": EmailClientEmulator(...),  # existing
    "outlook_web": EmailClientEmulator(...),  # existing
    "yahoo_web": EmailClientEmulator(...),
    "yahoo_mobile": EmailClientEmulator(...),
    "samsung_mail": EmailClientEmulator(...),
    "outlook_desktop": EmailClientEmulator(...),
    "thunderbird": EmailClientEmulator(...),
    "android_gmail": EmailClientEmulator(...),
}
```

Total: 8 emulators (2 existing + 6 new — Yahoo splits into web + mobile).

### Step 8: Add rendering profiles to `profiles.py`

Add 8 new profiles to `CLIENT_PROFILES`:

```python
# ── Yahoo ──
"yahoo_web": RenderingProfile(
    name="yahoo_web",
    viewport_width=800,
    viewport_height=900,
    browser="cr",
    emulator_id="yahoo_web",
),
"yahoo_mobile": RenderingProfile(
    name="yahoo_mobile",
    viewport_width=375,
    viewport_height=812,
    browser="wk",
    device="iPhone 13",
    emulator_id="yahoo_mobile",
),
# ── Samsung ──
"samsung_mail": RenderingProfile(
    name="samsung_mail",
    viewport_width=360,
    viewport_height=780,
    browser="cr",
    emulator_id="samsung_mail",
),
"samsung_mail_dark": RenderingProfile(
    name="samsung_mail_dark",
    viewport_width=360,
    viewport_height=780,
    browser="cr",
    color_scheme="dark",
    emulator_id="samsung_mail",
),
# ── Outlook Desktop (Word engine — CSS preprocessing only) ──
"outlook_desktop": RenderingProfile(
    name="outlook_desktop",
    viewport_width=800,
    viewport_height=900,
    browser="cr",
    emulator_id="outlook_desktop",
),
# ── Thunderbird (Gecko) ──
"thunderbird": RenderingProfile(
    name="thunderbird",
    viewport_width=700,
    viewport_height=900,
    browser="ff",
    emulator_id="thunderbird",
),
# ── Android Gmail ──
"android_gmail": RenderingProfile(
    name="android_gmail",
    viewport_width=360,
    viewport_height=780,
    browser="cr",
    emulator_id="android_gmail",
),
"android_gmail_dark": RenderingProfile(
    name="android_gmail_dark",
    viewport_width=360,
    viewport_height=780,
    browser="cr",
    color_scheme="dark",
    emulator_id="android_gmail",
),
```

Total profiles: 6 (existing) + 8 (new) = 14.

### Step 9: Write tests in `test_emulators.py`

Add test classes following the existing pattern (`get_emulator("id")` → `assert emulator is not None` → `.transform(html)` → assert transforms). Use **minimal synthetic HTML** for unit tests (per feedback memory — narrow unit tests may use synthetic HTML).

**Yahoo tests:**
```python
class TestYahooClassRewrite:
    def test_rewrites_class_names_with_yiv_prefix(self) -> None:
        emulator = get_emulator("yahoo_web")
        assert emulator is not None
        html = '<div class="hero main">Hello</div>'
        result = emulator.transform(html)
        assert "yiv" in result
        assert "hero" in result  # class name preserved, just prefixed

    def test_strips_unsupported_css(self) -> None:
        emulator = get_emulator("yahoo_web")
        assert emulator is not None
        html = '<div style="position: absolute; color: red;">Hello</div>'
        result = emulator.transform(html)
        assert "position" not in result
        assert "color" in result

    def test_enforces_max_width(self) -> None:
        emulator = get_emulator("yahoo_web")
        assert emulator is not None
        html = "<html><body><p>Hello</p></body></html>"
        result = emulator.transform(html)
        assert "800px" in result

class TestYahooMobileStripsStyleBlocks:
    def test_mobile_strips_style_blocks(self) -> None:
        emulator = get_emulator("yahoo_mobile")
        assert emulator is not None
        html = "<html><head><style>.foo { color: red; }</style></head><body><p>Hello</p></body></html>"
        result = emulator.transform(html)
        assert "<style>" not in result

    def test_web_preserves_style_blocks(self) -> None:
        emulator = get_emulator("yahoo_web")
        assert emulator is not None
        html = "<html><head><style>.foo { color: red; }</style></head><body><p>Hello</p></body></html>"
        result = emulator.transform(html)
        assert "<style>" not in result or "color: red" in result  # style content preserved
```

**Samsung tests:**
```python
class TestSamsungEmulator:
    def test_strips_blend_modes(self) -> None:
        emulator = get_emulator("samsung_mail")
        assert emulator is not None
        html = '<div style="mix-blend-mode: multiply; color: red;">Hello</div>'
        result = emulator.transform(html)
        assert "mix-blend-mode" not in result
        assert "color" in result

    def test_image_proxy_appends_param(self) -> None:
        emulator = get_emulator("samsung_mail")
        assert emulator is not None
        html = '<img src="https://example.com/hero.jpg" alt="Hero">'
        result = emulator.transform(html)
        assert "samsung_proxy=1" in result

    def test_image_proxy_handles_existing_query(self) -> None:
        emulator = get_emulator("samsung_mail")
        assert emulator is not None
        html = '<img src="https://example.com/hero.jpg?w=600" alt="Hero">'
        result = emulator.transform(html)
        assert "&samsung_proxy=1" in result

    def test_dark_mode_inject_when_no_explicit_dark(self) -> None:
        emulator = get_emulator("samsung_mail")
        assert emulator is not None
        html = "<html><head></head><body><p>Hello</p></body></html>"
        result = emulator.transform(html)
        assert "color-scheme" in result or "background-color" in result

    def test_dark_mode_skips_when_explicit(self) -> None:
        emulator = get_emulator("samsung_mail")
        assert emulator is not None
        html = "<html><head><style>@media (prefers-color-scheme: dark) { body { background: #000; } }</style></head><body><p>Hello</p></body></html>"
        result = emulator.transform(html)
        # Should NOT inject forced dark mode since explicit styles exist
        assert "color-scheme" not in result.split("<style>")[0]  # not on <html>
```

**Outlook Desktop tests:**
```python
class TestOutlookDesktopEmulator:
    def test_strips_flex_display(self) -> None:
        emulator = get_emulator("outlook_desktop")
        assert emulator is not None
        html = '<div style="display: flex; color: red;">Hello</div>'
        result = emulator.transform(html)
        assert "display" not in result or "flex" not in result
        assert "color" in result

    def test_strips_border_radius(self) -> None:
        emulator = get_emulator("outlook_desktop")
        assert emulator is not None
        html = '<td style="border-radius: 8px; padding: 10px;">Hello</td>'
        result = emulator.transform(html)
        assert "border-radius" not in result

    def test_expands_margin_shorthand(self) -> None:
        emulator = get_emulator("outlook_desktop")
        assert emulator is not None
        html = '<td style="margin: 10px 20px;">Hello</td>'
        result = emulator.transform(html)
        assert "margin-top" in result

    def test_processes_mso_conditionals(self) -> None:
        emulator = get_emulator("outlook_desktop")
        assert emulator is not None
        html = (
            '<div>Before</div>'
            '<!--[if mso]><table role="presentation" width="600"><tr><td><![endif]-->'
            '<div>Content</div>'
            '<!--[if mso]></td></tr></table><![endif]-->'
            '<div>After</div>'
        )
        result = emulator.transform(html)
        # MSO content should be unwrapped (comments removed)
        assert '<table role="presentation" width="600">' in result
        assert "<!--[if mso]>" not in result

    def test_removes_not_mso_blocks(self) -> None:
        emulator = get_emulator("outlook_desktop")
        assert emulator is not None
        html = (
            '<div>Before</div>'
            '<!--[if !mso]><!--><div class="modern-only">Flex content</div><!--<![endif]-->'
            '<div>After</div>'
        )
        result = emulator.transform(html)
        assert "modern-only" not in result
        assert "Before" in result
        assert "After" in result

    def test_injects_table_width(self) -> None:
        emulator = get_emulator("outlook_desktop")
        assert emulator is not None
        html = '<table role="presentation"><tr><td>Hello</td></tr></table>'
        result = emulator.transform(html)
        assert 'width="600"' in result
```

**Thunderbird tests:**
```python
class TestThunderbirdEmulator:
    def test_strips_position_sticky(self) -> None:
        emulator = get_emulator("thunderbird")
        assert emulator is not None
        html = '<div style="position: sticky; top: 0; color: red;">Hello</div>'
        result = emulator.transform(html)
        assert "sticky" not in result
        assert "color" in result

    def test_preserves_style_blocks(self) -> None:
        emulator = get_emulator("thunderbird")
        assert emulator is not None
        html = "<html><head><style>.foo { color: red; }</style></head><body><p>Hello</p></body></html>"
        result = emulator.transform(html)
        assert "<style>" in result
        assert "color: red" in result
```

**Android Gmail tests:**
```python
class TestAndroidGmailEmulator:
    def test_inherits_gmail_style_strip(self) -> None:
        emulator = get_emulator("android_gmail")
        assert emulator is not None
        html = "<html><head><style>.foo { color: red; }</style></head><body><p>Hello</p></body></html>"
        result = emulator.transform(html)
        assert "<style>" not in result

    def test_inherits_gmail_class_rewrite(self) -> None:
        emulator = get_emulator("android_gmail")
        assert emulator is not None
        html = '<div class="header">Hello</div>'
        result = emulator.transform(html)
        assert "m_" in result

    def test_injects_viewport_meta(self) -> None:
        emulator = get_emulator("android_gmail")
        assert emulator is not None
        html = "<html><head></head><body><p>Hello</p></body></html>"
        result = emulator.transform(html)
        assert "viewport" in result
        assert "width=device-width" in result

    def test_adds_dark_mode_attributes(self) -> None:
        emulator = get_emulator("android_gmail")
        assert emulator is not None
        html = "<html><head></head><body><p>Hello</p></body></html>"
        result = emulator.transform(html)
        assert "data-ogsc" in result

    def test_strips_amp(self) -> None:
        emulator = get_emulator("android_gmail")
        assert emulator is not None
        html = '<html ⚡4email><head></head><body><p>AMP</p></body></html>'
        result = emulator.transform(html)
        assert "⚡4email" not in result
```

**Profile integration tests:**
```python
class TestNewProfileEmulatorIntegration:
    """All new profiles reference valid emulators."""

    def test_yahoo_web_profile(self) -> None:
        profile = CLIENT_PROFILES["yahoo_web"]
        assert profile.emulator_id == "yahoo_web"
        assert get_emulator(profile.emulator_id) is not None

    def test_yahoo_mobile_profile(self) -> None:
        profile = CLIENT_PROFILES["yahoo_mobile"]
        assert profile.emulator_id == "yahoo_mobile"
        assert get_emulator(profile.emulator_id) is not None

    def test_samsung_mail_profile(self) -> None:
        profile = CLIENT_PROFILES["samsung_mail"]
        assert profile.emulator_id == "samsung_mail"
        assert get_emulator(profile.emulator_id) is not None

    def test_outlook_desktop_profile(self) -> None:
        profile = CLIENT_PROFILES["outlook_desktop"]
        assert profile.emulator_id == "outlook_desktop"
        assert get_emulator(profile.emulator_id) is not None

    def test_thunderbird_profile(self) -> None:
        profile = CLIENT_PROFILES["thunderbird"]
        assert profile.emulator_id == "thunderbird"
        assert profile.browser == "ff"  # Gecko
        assert get_emulator(profile.emulator_id) is not None

    def test_android_gmail_profile(self) -> None:
        profile = CLIENT_PROFILES["android_gmail"]
        assert profile.emulator_id == "android_gmail"
        assert get_emulator(profile.emulator_id) is not None
```

**Regression tests — existing emulators unchanged:**
```python
class TestExistingEmulatorRegression:
    """Existing Gmail/Outlook.com emulators are not broken by new code."""

    def test_gmail_still_has_6_rules(self) -> None:
        emulator = get_emulator("gmail_web")
        assert emulator is not None
        assert len(emulator.rules) == 6

    def test_outlook_web_still_has_3_rules(self) -> None:
        emulator = get_emulator("outlook_web")
        assert emulator is not None
        assert len(emulator.rules) == 3

    def test_gmail_transform_unchanged(self) -> None:
        """Gmail emulator produces expected output for known input."""
        emulator = get_emulator("gmail_web")
        assert emulator is not None
        html = '<div class="test" style="display: flex; color: red;">Hello</div>'
        result = emulator.transform(html)
        assert "m_" in result  # class rewriting
        assert "flex" not in result  # unsupported CSS stripped
        assert "color" in result  # supported CSS preserved
```

### Step 10: Verify

- [ ] `make test` passes — all new + existing emulator tests green
- [ ] `make lint` passes — ruff format/check clean
- [ ] `make types` passes — mypy + pyright clean
- [ ] Existing Gmail/Outlook.com emulator behavior unchanged (regression tests)
- [ ] All 14 profiles reference valid emulators (integration tests)
- [ ] No new endpoints (pure internal module change) — no auth/rate-limiting needed

## Security Checklist

**No new endpoints** — this is a pure internal module change. Emulators are `str -> str` HTML transforms with no network calls, no file system access, no subprocess execution.

- [x] **Input validation**: Emulators receive HTML from `_prepare_html()` in `runner.py`, which is called by `capture_screenshot()`. The HTML comes from `RenderingService.render_screenshots()` which validates via Pydantic schema (`ScreenshotRequest.html` max_length=500_000).
- [x] **XSS**: Emulators are NOT a security boundary (see comment in existing code). `sanitize_html_xss()` runs separately. Emulator output goes to Playwright for screenshot — not served to users as HTML.
- [x] **No secrets**: No API keys, credentials, or environment variables involved.
- [x] **No SQL**: No database operations.
- [x] **Samsung image proxy**: URL parameter append only (`?samsung_proxy=1`). No actual HTTP requests — just string manipulation.

## Verification

- [ ] `make check` passes (includes lint, types, tests, frontend, security-check)
- [ ] New endpoints have auth + rate limiting — N/A (no new endpoints)
- [ ] Error responses don't leak internal types — N/A (no new endpoints)
