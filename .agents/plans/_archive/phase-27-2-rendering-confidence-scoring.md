# Plan: 27.2 Rendering Confidence Scoring

## Context

Local rendering previews need a confidence score (0–100) quantifying how faithful the emulated screenshot is relative to the real email client. Three signals feed the score: emulator rule coverage, ontology CSS support gaps, and historical calibration seeds. This converts rendering testing from binary pass/fail into quantified risk assessment.

## Key Discoveries from Research

- **Emulators** (`app/rendering/local/emulators.py`): 8 emulators registered in `_EMULATORS` dict. Each has a `rules: list[EmulatorRule]` with `confidence_impact: float` field (already exists, currently all 0.0). `get_emulator(client_id)` returns emulator by ID.
- **Profiles** (`app/rendering/local/profiles.py`): 14 `RenderingProfile` entries in `CLIENT_PROFILES` dict. Each has `emulator_id: str | None` linking to emulator. Frozen dataclass.
- **Ontology** (`app/knowledge/ontology/`): `load_ontology()` → `OntologyRegistry`. `get_support(property_id, client_id) -> SupportLevel` (FULL/PARTIAL/NONE/UNKNOWN). `unsupported_css_in_html(html)` scans HTML for unsupported CSS. `_extract_css_content(html)` extracts CSS from `<style>` blocks + inline `style=""`.
- **Ontology client IDs** are different from emulator IDs (ontology has `gmail_web`, `outlook_2021`, etc.; emulators have `gmail_web`, `outlook_desktop`, etc.). Need a mapping.
- **Service layer** (`app/rendering/service.py`): `render_screenshots()` calls `LocalRenderingProvider().render_screenshots()` which returns `list[dict]` with `client_name`, `image_bytes`, `viewport`, `browser`. Results mapped to `ScreenshotClientResult` schema.
- **LocalRenderingProvider** (`app/rendering/local/service.py`): iterates `CLIENT_PROFILES`, calls `capture_screenshot()` per profile.
- **Schema** (`app/rendering/schemas.py`): `ScreenshotClientResult` has `client_name`, `image_base64`, `viewport`, `browser`. `ScreenshotResponse` has `screenshots`, `clients_rendered`, `clients_failed`.
- **DB models** (`app/rendering/models.py`): `RenderingScreenshot` has no confidence fields yet.
- **Config** (`app/core/config.py`): `RenderingConfig` at line 216 — no confidence-related settings yet.
- **Test pattern** (`app/rendering/local/tests/test_emulators.py`): Uses `_EMAIL_SKELETON` with table-based layout. Uses `get_emulator()` + `.transform()`.

## Files to Create

1. `app/rendering/local/confidence.py` — `RenderingConfidenceScorer` with scoring logic
2. `app/rendering/local/confidence_seeds.yaml` — initial calibration seed data
3. `app/rendering/local/tests/test_confidence.py` — unit tests
4. `alembic/versions/w7x8y9z0a1b2_add_confidence_to_screenshots.py` — migration

## Files to Modify

5. `app/rendering/schemas.py` — add confidence fields to `ScreenshotClientResult` + new `ConfidenceBreakdownSchema` + new `ClientConfidenceResponse`
6. `app/rendering/models.py` — add confidence columns to `RenderingScreenshot`
7. `app/rendering/local/service.py` — compute confidence after each screenshot
8. `app/rendering/service.py` — pass confidence data through to response
9. `app/rendering/routes.py` — add `GET /confidence/{client_id}` endpoint
10. `app/core/config.py` — add `confidence_enabled: bool` to `RenderingConfig`

## Implementation Steps

### Step 1: Add `confidence_enabled` to `RenderingConfig`

In `app/core/config.py`, add to `RenderingConfig` (after line 232, before `sandbox`):

```python
confidence_enabled: bool = True
```

### Step 2: Create `app/rendering/local/confidence_seeds.yaml`

```yaml
# Initial calibration seeds for rendering confidence scoring.
# Updated by the calibration loop (Phase 27.4) when real data is available.
# accuracy: estimated fidelity of emulator vs real client (0.0–1.0)
# sample_count: 0 = seed only, >0 = calibrated with real data
# known_blind_spots: behaviors the emulator cannot model

gmail_web:
  accuracy: 0.80
  sample_count: 0
  last_calibrated: "2026-03-22"
  known_blind_spots:
    - "DOM restructuring (div wrapping, attribute reordering)"
    - "URL click-tracking rewriting"
    - "Viewport clipping at 102KB"

outlook_web:
  accuracy: 0.75
  sample_count: 0
  last_calibrated: "2026-03-22"
  known_blind_spots:
    - "data-ogsc/data-ogsb color inversion logic"
    - "CSS specificity recalculation"
    - "Conditional comment processing differences"

yahoo_web:
  accuracy: 0.70
  sample_count: 0
  last_calibrated: "2026-03-22"
  known_blind_spots:
    - "Class prefix collision handling"
    - "Embedded CSS scope isolation"
    - "Mobile responsive breakpoint override"

yahoo_mobile:
  accuracy: 0.68
  sample_count: 0
  last_calibrated: "2026-03-22"
  known_blind_spots:
    - "Class prefix collision handling"
    - "Touch target size enforcement"
    - "Image lazy-loading rewriting"

samsung_mail:
  accuracy: 0.65
  sample_count: 0
  last_calibrated: "2026-03-22"
  known_blind_spots:
    - "Image proxy URL rewriting fidelity"
    - "Auto dark mode color inversion algorithm"
    - "OneUI-specific rendering quirks"

outlook_desktop:
  accuracy: 0.50
  sample_count: 0
  last_calibrated: "2026-03-22"
  known_blind_spots:
    - "Word table cell width calculation"
    - "VML rendering (Chromium cannot render VML)"
    - "DPI scaling behavior"
    - "Page break insertion for tall emails"
    - "Font substitution and metric differences"

thunderbird:
  accuracy: 0.85
  sample_count: 0
  last_calibrated: "2026-03-22"
  known_blind_spots:
    - "Gecko remote image blocking default"
    - "Thunderbird-specific content policy filtering"

android_gmail:
  accuracy: 0.78
  sample_count: 0
  last_calibrated: "2026-03-22"
  known_blind_spots:
    - "DOM restructuring (shared with Gmail web)"
    - "Android WebView rendering differences"
    - "System dark mode interaction"
```

### Step 3: Create `app/rendering/local/confidence.py`

```python
"""Rendering confidence scoring for local email client emulation.

Quantifies how faithful a local preview is expected to be relative
to the real email client, based on emulator coverage, CSS compatibility,
calibration seeds, and layout complexity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.core.logging import get_logger
from app.knowledge.ontology.query import _extract_css_content
from app.knowledge.ontology.registry import OntologyRegistry, load_ontology
from app.knowledge.ontology.types import SupportLevel
from app.rendering.local.emulators import _EMULATORS
from app.rendering.local.profiles import CLIENT_PROFILES, RenderingProfile

logger = get_logger(__name__)

_SEEDS_PATH = Path(__file__).parent / "confidence_seeds.yaml"

# ── Mapping: emulator_id → ontology client_id(s) ──
# Emulators map to one or more ontology clients for CSS compatibility lookup.
_EMULATOR_TO_ONTOLOGY: dict[str, list[str]] = {
    "gmail_web": ["gmail_web"],
    "outlook_web": ["outlook_web"],
    "yahoo_web": ["yahoo_web"],
    "yahoo_mobile": ["yahoo_ios"],
    "samsung_mail": ["samsung_email"],
    "outlook_desktop": ["outlook_2021"],
    "thunderbird": ["thunderbird"],
    "android_gmail": ["gmail_android"],
}

# ── Layout complexity patterns ──
_TABLE_OPEN_RE = re.compile(r"<table\b", re.IGNORECASE)
_FLEXBOX_RE = re.compile(r"display\s*:\s*(?:flex|inline-flex)", re.IGNORECASE)
_GRID_RE = re.compile(r"display\s*:\s*(?:grid|inline-grid)", re.IGNORECASE)
_POSITION_ABS_RE = re.compile(r"position\s*:\s*(?:absolute|fixed)", re.IGNORECASE)
_VML_RE = re.compile(r"<v:", re.IGNORECASE)
_MSO_CONDITIONAL_RE = re.compile(r"<!--\[if\s+mso", re.IGNORECASE)
_MEDIA_QUERY_RE = re.compile(r"@media\b", re.IGNORECASE)


@dataclass(frozen=True)
class ConfidenceBreakdown:
    """Component scores that feed into the overall confidence score."""

    emulator_coverage: float  # 0.0–1.0
    css_compatibility: float  # 0.0–1.0
    calibration_accuracy: float  # 0.0–1.0
    layout_complexity: float  # 0.0–1.0 (higher = more complex)
    known_blind_spots: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RenderingConfidence:
    """Confidence assessment for a rendering preview."""

    score: float  # 0–100
    breakdown: ConfidenceBreakdown
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON storage / API response."""
        return {
            "score": round(self.score, 1),
            "breakdown": {
                "emulator_coverage": round(self.breakdown.emulator_coverage, 3),
                "css_compatibility": round(self.breakdown.css_compatibility, 3),
                "calibration_accuracy": round(self.breakdown.calibration_accuracy, 3),
                "layout_complexity": round(self.breakdown.layout_complexity, 3),
                "known_blind_spots": self.breakdown.known_blind_spots,
            },
            "recommendations": self.recommendations,
        }


def _load_seeds() -> dict[str, dict[str, Any]]:
    """Load calibration seed data from YAML."""
    if not _SEEDS_PATH.exists():
        logger.warning("confidence.seeds_not_found", path=str(_SEEDS_PATH))
        return {}
    with open(_SEEDS_PATH) as f:
        data = yaml.safe_load(f) or {}
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def _table_nesting_depth(html: str) -> int:
    """Compute max nesting depth of <table> elements."""
    depth = 0
    max_depth = 0
    lower = html.lower()
    i = 0
    while i < len(lower):
        if lower[i:i + 6] == "<table":
            depth += 1
            max_depth = max(max_depth, depth)
            i += 6
        elif lower[i:i + 8] == "</table>":
            depth = max(0, depth - 1)
            i += 8
        else:
            i += 1
    return max_depth


def layout_complexity_score(html: str) -> float:
    """Score layout complexity from 0.0 (simple) to 1.0 (highly complex).

    Factors: table nesting depth, flexbox/grid, absolute positioning,
    VML blocks, MSO conditionals, media query count.
    """
    score = 0.0

    # Table nesting >3 deep
    nesting = _table_nesting_depth(html)
    if nesting > 3:
        score += 0.2

    # Flexbox usage
    if _FLEXBOX_RE.search(html):
        score += 0.15

    # Grid usage
    if _GRID_RE.search(html):
        score += 0.15

    # Absolute/fixed positioning
    if _POSITION_ABS_RE.search(html):
        score += 0.1

    # VML blocks
    if _VML_RE.search(html):
        score += 0.1

    # MSO conditionals
    if _MSO_CONDITIONAL_RE.search(html):
        score += 0.05

    # Media queries >5
    mq_count = len(_MEDIA_QUERY_RE.findall(html))
    if mq_count > 5:
        score += 0.1

    return min(1.0, score)


def _emulator_coverage_score(profile: RenderingProfile) -> float:
    """Calculate emulator rule coverage as fraction of known behaviors modeled.

    Profiles with an emulator get coverage based on rule count relative to
    known behavior count. Profiles without emulators get a baseline 0.3
    (CSS injection only).
    """
    if not profile.emulator_id:
        return 0.3  # CSS injection only, no emulator

    emulator = _EMULATORS.get(profile.emulator_id)
    if not emulator:
        return 0.3

    rule_count = len(emulator.rules)

    # Known behavior counts per client (estimated total behaviors
    # a real client applies, including those we can't emulate).
    _KNOWN_BEHAVIORS: dict[str, int] = {
        "gmail_web": 8,
        "outlook_web": 5,
        "yahoo_web": 5,
        "yahoo_mobile": 6,
        "samsung_mail": 5,
        "outlook_desktop": 10,
        "thunderbird": 3,
        "android_gmail": 10,
    }

    known = _KNOWN_BEHAVIORS.get(profile.emulator_id, max(rule_count + 2, 5))
    return min(1.0, rule_count / known)


def _css_compatibility_score(
    html: str,
    profile: RenderingProfile,
    ontology: OntologyRegistry,
) -> float:
    """Fraction of CSS properties in HTML that are supported by the target client.

    Returns 1.0 if all CSS is supported (or no CSS found), lower if the
    target client doesn't support some properties used in the HTML.
    """
    css_content = _extract_css_content(html)
    if not css_content:
        return 1.0  # No CSS = nothing to be incompatible with

    emulator_id = profile.emulator_id or profile.name
    ontology_clients = _EMULATOR_TO_ONTOLOGY.get(emulator_id, [])
    if not ontology_clients:
        return 0.8  # Unknown client — conservative estimate

    # Count total CSS properties used and how many are supported
    total_props = 0
    supported_props = 0

    for prop in ontology.properties:
        prop_escaped = re.escape(prop.property_name)
        if prop.value:
            val_escaped = re.escape(prop.value)
            pattern = rf"(?<![a-z\-]){prop_escaped}\s*:\s*{val_escaped}"
        else:
            pattern = rf"(?<![a-z\-]){prop_escaped}\s*:"

        if not re.search(pattern, css_content):
            continue

        total_props += 1

        # Check worst-case support across mapped ontology clients
        worst = SupportLevel.FULL
        for client_id in ontology_clients:
            level = ontology.get_support(prop.id, client_id)
            if level == SupportLevel.NONE:
                worst = SupportLevel.NONE
                break
            if level == SupportLevel.PARTIAL and worst != SupportLevel.NONE:
                worst = SupportLevel.PARTIAL

        if worst in (SupportLevel.FULL, SupportLevel.UNKNOWN):
            supported_props += 1
        elif worst == SupportLevel.PARTIAL:
            supported_props += 0.5  # type: ignore[assignment]

    if total_props == 0:
        return 1.0

    return float(supported_props) / total_props


class RenderingConfidenceScorer:
    """Computes rendering confidence scores for email client previews."""

    def __init__(self) -> None:
        self._seeds = _load_seeds()

    def get_seed(self, emulator_id: str) -> dict[str, Any]:
        """Get calibration seed data for an emulator."""
        return dict(self._seeds.get(emulator_id, {
            "accuracy": 0.5,
            "sample_count": 0,
            "last_calibrated": "",
            "known_blind_spots": [],
        }))

    def score(self, html: str, profile: RenderingProfile) -> RenderingConfidence:
        """Compute rendering confidence for a profile against given HTML."""
        emulator_id = profile.emulator_id or profile.name
        seed = self.get_seed(emulator_id)
        ontology = load_ontology()

        # Component scores
        emulator_cov = _emulator_coverage_score(profile)
        css_compat = _css_compatibility_score(html, profile, ontology)
        calibration_acc = float(seed.get("accuracy", 0.5))
        layout_complex = layout_complexity_score(html)
        blind_spots: list[str] = list(seed.get("known_blind_spots", []))

        breakdown = ConfidenceBreakdown(
            emulator_coverage=emulator_cov,
            css_compatibility=css_compat,
            calibration_accuracy=calibration_acc,
            layout_complexity=layout_complex,
            known_blind_spots=blind_spots,
        )

        # Weighted formula
        raw = (
            emulator_cov * 0.25
            + css_compat * 0.25
            + calibration_acc * 0.35
            + (1.0 - layout_complex) * 0.15
        )
        final_score = round(min(100.0, max(0.0, raw * 100)), 1)

        # Generate recommendations
        recommendations = self._build_recommendations(
            final_score, breakdown, emulator_id
        )

        return RenderingConfidence(
            score=final_score,
            breakdown=breakdown,
            recommendations=recommendations,
        )

    def _build_recommendations(
        self,
        score: float,
        breakdown: ConfidenceBreakdown,
        emulator_id: str,
    ) -> list[str]:
        """Generate actionable recommendations based on confidence breakdown."""
        recs: list[str] = []

        if score < 70:
            recs.append(
                f"Low confidence ({score:.0f}%) — consider using Litmus or "
                "Email on Acid for this client."
            )

        if breakdown.css_compatibility < 0.7:
            recs.append(
                "CSS compatibility is low — some properties used in this "
                "email are unsupported by this client."
            )

        if breakdown.layout_complexity > 0.5:
            recs.append(
                "Complex layout detected — emulator accuracy decreases "
                "with nested tables, flexbox, or VML."
            )

        if breakdown.emulator_coverage < 0.5:
            recs.append(
                f"Emulator coverage for {emulator_id} is limited — "
                "not all client behaviors are modeled."
            )

        if breakdown.known_blind_spots:
            spots = ", ".join(breakdown.known_blind_spots[:3])
            recs.append(f"Known blind spots: {spots}")

        return recs
```

### Step 4: Add confidence fields to schemas

In `app/rendering/schemas.py`, add after `ScreenshotResponse` (after line 125):

```python
class ConfidenceBreakdownSchema(BaseModel):
    """Component scores for rendering confidence."""

    emulator_coverage: float = Field(ge=0.0, le=1.0)
    css_compatibility: float = Field(ge=0.0, le=1.0)
    calibration_accuracy: float = Field(ge=0.0, le=1.0)
    layout_complexity: float = Field(ge=0.0, le=1.0)
    known_blind_spots: list[str] = []


class ClientConfidenceResponse(BaseModel):
    """Current confidence data for a specific client."""

    client_id: str
    accuracy: float
    sample_count: int
    last_calibrated: str
    known_blind_spots: list[str] = []
    emulator_rule_count: int
    profiles: list[str] = []
```

Modify `ScreenshotClientResult` (line 111) — add 3 optional fields:

```python
class ScreenshotClientResult(BaseModel):
    """Single client screenshot result with base64 image."""

    client_name: str
    image_base64: str
    viewport: str
    browser: str
    confidence_score: float | None = None
    confidence_breakdown: ConfidenceBreakdownSchema | None = None
    confidence_recommendations: list[str] | None = None
```

### Step 5: Add confidence columns to `RenderingScreenshot` model

In `app/rendering/models.py`, add to `RenderingScreenshot` class (after `status` at line 48):

```python
from sqlalchemy import Float, JSON
# ... in the class:
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_breakdown: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence_recommendations: Mapped[list | None] = mapped_column(JSON, nullable=True)
```

### Step 6: Alembic migration

Create `alembic/versions/w7x8y9z0a1b2_add_confidence_to_screenshots.py`:

```python
"""Add confidence scoring columns to rendering_screenshots.

Revision ID: w7x8y9z0a1b2
Revises: v6w7x8y9z0a1
Create Date: 2026-03-22
"""

from alembic import op
import sqlalchemy as sa

revision = "w7x8y9z0a1b2"
down_revision = "v6w7x8y9z0a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rendering_screenshots", sa.Column("confidence_score", sa.Float(), nullable=True))
    op.add_column("rendering_screenshots", sa.Column("confidence_breakdown", sa.JSON(), nullable=True))
    op.add_column("rendering_screenshots", sa.Column("confidence_recommendations", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("rendering_screenshots", "confidence_recommendations")
    op.drop_column("rendering_screenshots", "confidence_breakdown")
    op.drop_column("rendering_screenshots", "confidence_score")
```

### Step 7: Integrate scoring into `LocalRenderingProvider`

In `app/rendering/local/service.py`, modify `render_screenshots()`:

```python
# Add import at top:
from app.core.config import get_settings
from app.rendering.local.confidence import RenderingConfidenceScorer

# In render_screenshots(), after getting settings and before the loop:
        scorer = RenderingConfidenceScorer() if get_settings().rendering.confidence_enabled else None

# In the try block, after capturing image_bytes, before appending to results:
                    confidence = None
                    if scorer:
                        confidence = scorer.score(html, profile)

                    results.append(
                        {
                            "client_name": name,
                            "image_bytes": image_bytes,
                            "viewport": f"{profile.viewport_width}x{profile.viewport_height}",
                            "browser": profile.browser,
                            "confidence_score": confidence.score if confidence else None,
                            "confidence_breakdown": confidence.to_dict()["breakdown"] if confidence else None,
                            "confidence_recommendations": confidence.recommendations if confidence else None,
                        }
                    )
```

### Step 8: Pass confidence through `RenderingService.render_screenshots()`

In `app/rendering/service.py`, modify the `render_screenshots()` method (line 212). Update the `ScreenshotClientResult` construction:

```python
        screenshots = [
            ScreenshotClientResult(
                client_name=str(r["client_name"]),
                image_base64=base64.b64encode(
                    r["image_bytes"]  # type: ignore[arg-type]
                ).decode("ascii"),
                viewport=str(r["viewport"]),
                browser=str(r["browser"]),
                confidence_score=r.get("confidence_score"),  # type: ignore[arg-type]
                confidence_breakdown=r.get("confidence_breakdown"),  # type: ignore[arg-type]
                confidence_recommendations=r.get("confidence_recommendations"),  # type: ignore[arg-type]
            )
            for r in raw_results
        ]
```

### Step 9: Add confidence endpoint to routes

In `app/rendering/routes.py`, add import and endpoint:

```python
# Add to imports:
from app.rendering.schemas import ClientConfidenceResponse

# Add endpoint after render_screenshots (after line 112):
@router.get("/confidence/{client_id}", response_model=ClientConfidenceResponse)
@limiter.limit("30/minute")
async def get_client_confidence(
    request: Request,
    client_id: str,
    _current_user: User = Depends(get_current_user),  # noqa: B008
) -> ClientConfidenceResponse:
    """Get current confidence calibration data for an email client."""
    _ = request
    from app.rendering.local.confidence import RenderingConfidenceScorer
    from app.rendering.local.emulators import _EMULATORS
    from app.rendering.local.profiles import CLIENT_PROFILES

    scorer = RenderingConfidenceScorer()
    seed = scorer.get_seed(client_id)

    emulator = _EMULATORS.get(client_id)
    rule_count = len(emulator.rules) if emulator else 0

    # Find which profiles use this emulator
    profiles = [
        name for name, p in CLIENT_PROFILES.items()
        if p.emulator_id == client_id
    ]

    return ClientConfidenceResponse(
        client_id=client_id,
        accuracy=seed.get("accuracy", 0.5),
        sample_count=seed.get("sample_count", 0),
        last_calibrated=seed.get("last_calibrated", ""),
        known_blind_spots=seed.get("known_blind_spots", []),
        emulator_rule_count=rule_count,
        profiles=profiles,
    )
```

### Step 10: Create tests

Create `app/rendering/local/tests/test_confidence.py`:

```python
"""Tests for rendering confidence scoring."""

from __future__ import annotations

import pytest

from app.rendering.local.confidence import (
    ConfidenceBreakdown,
    RenderingConfidence,
    RenderingConfidenceScorer,
    layout_complexity_score,
    _emulator_coverage_score,
    _table_nesting_depth,
)
from app.rendering.local.profiles import CLIENT_PROFILES

# Reuse table-based email skeleton from emulator tests
_SIMPLE_EMAIL = (
    "<!DOCTYPE html>"
    '<html xmlns="http://www.w3.org/1999/xhtml">'
    "<head>"
    '<meta charset="utf-8">'
    "</head>"
    "<body>"
    '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
    '<tr><td align="center">'
    '<table role="presentation" width="600" cellpadding="0" cellspacing="0">'
    '<tr><td style="padding:20px;font-family:Arial,sans-serif;font-size:16px;color:#333333;">'
    "Hello World"
    "</td></tr>"
    "</table>"
    "</td></tr></table>"
    "</body></html>"
)

_COMPLEX_EMAIL = (
    "<!DOCTYPE html>"
    '<html xmlns="http://www.w3.org/1999/xhtml">'
    "<head>"
    '<meta charset="utf-8">'
    "<style>"
    "@media screen and (max-width: 600px) { .col { width: 100% !important; } }"
    "@media screen and (max-width: 480px) { .col { padding: 10px !important; } }"
    "@media screen and (max-width: 400px) { .btn { width: 100% !important; } }"
    "@media screen and (max-width: 320px) { .img { width: 100% !important; } }"
    "@media (prefers-color-scheme: dark) { .dark { background: #000; } }"
    "@media (prefers-color-scheme: dark) { .dark-text { color: #fff; } }"
    "</style>"
    "</head>"
    "<body>"
    "<!--[if mso]>"
    '<table width="600"><tr><td>'
    "<![endif]-->"
    '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
    '<tr><td style="display:flex;position:absolute;">'
    '<table role="presentation"><tr><td>'
    '<table role="presentation"><tr><td>'
    '<table role="presentation"><tr><td>'
    '<table role="presentation"><tr><td>'
    '<v:roundrect xmlns:v="urn:schemas-microsoft-com:vml">Click</v:roundrect>'
    "</td></tr></table>"
    "</td></tr></table>"
    "</td></tr></table>"
    "</td></tr></table>"
    "</td></tr></table>"
    "<!--[if mso]>"
    "</td></tr></table>"
    "<![endif]-->"
    "</body></html>"
)


class TestTableNestingDepth:
    def test_simple_email(self) -> None:
        assert _table_nesting_depth(_SIMPLE_EMAIL) == 2

    def test_complex_email(self) -> None:
        assert _table_nesting_depth(_COMPLEX_EMAIL) >= 4

    def test_no_tables(self) -> None:
        assert _table_nesting_depth("<html><body>Hello</body></html>") == 0


class TestLayoutComplexity:
    def test_simple_email_low_complexity(self) -> None:
        score = layout_complexity_score(_SIMPLE_EMAIL)
        assert score < 0.2

    def test_complex_email_high_complexity(self) -> None:
        score = layout_complexity_score(_COMPLEX_EMAIL)
        # flexbox (+0.15) + absolute (+0.1) + VML (+0.1) + nesting>3 (+0.2)
        # + MSO (+0.05) + media queries>5 (+0.1) = 0.7
        assert score >= 0.5

    def test_capped_at_one(self) -> None:
        score = layout_complexity_score(_COMPLEX_EMAIL)
        assert score <= 1.0


class TestEmulatorCoverage:
    def test_gmail_web_coverage(self) -> None:
        profile = CLIENT_PROFILES["gmail_web"]
        score = _emulator_coverage_score(profile)
        # 6 rules / 8 known = 0.75
        assert 0.6 <= score <= 1.0

    def test_no_emulator_baseline(self) -> None:
        profile = CLIENT_PROFILES["apple_mail"]
        score = _emulator_coverage_score(profile)
        assert score == 0.3  # No emulator = baseline


class TestRenderingConfidenceScorer:
    def test_simple_email_gmail_high_confidence(self) -> None:
        scorer = RenderingConfidenceScorer()
        profile = CLIENT_PROFILES["gmail_web"]
        result = scorer.score(_SIMPLE_EMAIL, profile)
        assert result.score > 70  # Simple email, Gmail = good confidence
        assert isinstance(result.breakdown, ConfidenceBreakdown)
        assert len(result.breakdown.known_blind_spots) > 0

    def test_complex_email_outlook_desktop_low_confidence(self) -> None:
        scorer = RenderingConfidenceScorer()
        profile = CLIENT_PROFILES["outlook_desktop"]
        result = scorer.score(_COMPLEX_EMAIL, profile)
        assert result.score < 70
        assert "Word table cell width" in " ".join(result.breakdown.known_blind_spots)

    def test_thunderbird_high_confidence(self) -> None:
        scorer = RenderingConfidenceScorer()
        profile = CLIENT_PROFILES["thunderbird"]
        result = scorer.score(_SIMPLE_EMAIL, profile)
        assert result.score > 75  # Standards-compliant client

    def test_to_dict_serialization(self) -> None:
        scorer = RenderingConfidenceScorer()
        profile = CLIENT_PROFILES["gmail_web"]
        result = scorer.score(_SIMPLE_EMAIL, profile)
        d = result.to_dict()
        assert "score" in d
        assert "breakdown" in d
        assert "recommendations" in d
        assert isinstance(d["breakdown"]["known_blind_spots"], list)

    def test_all_profiles_score_without_error(self) -> None:
        """Every profile in CLIENT_PROFILES can be scored."""
        scorer = RenderingConfidenceScorer()
        for name, profile in CLIENT_PROFILES.items():
            result = scorer.score(_SIMPLE_EMAIL, profile)
            assert 0 <= result.score <= 100, f"Score out of range for {name}"

    def test_recommendations_for_low_confidence(self) -> None:
        scorer = RenderingConfidenceScorer()
        profile = CLIENT_PROFILES["outlook_desktop"]
        result = scorer.score(_COMPLEX_EMAIL, profile)
        assert len(result.recommendations) > 0

    def test_get_seed_known_client(self) -> None:
        scorer = RenderingConfidenceScorer()
        seed = scorer.get_seed("gmail_web")
        assert seed["accuracy"] == 0.80
        assert seed["sample_count"] == 0

    def test_get_seed_unknown_client(self) -> None:
        scorer = RenderingConfidenceScorer()
        seed = scorer.get_seed("nonexistent_client")
        assert seed["accuracy"] == 0.5
```

## Security Checklist

### New endpoint: `GET /api/v1/rendering/confidence/{client_id}`
- **Authentication**: `Depends(get_current_user)` — requires valid JWT ✅
- **Authorization**: Any authenticated user (read-only data) — no role restriction needed ✅
- **Rate limiting**: `@limiter.limit("30/minute")` ✅
- **Input validation**: `client_id` is a path param string, used only for dict lookup (no SQL, no injection vector) ✅
- **Error responses**: Returns empty/default data for unknown clients — no internal types leaked ✅
- **BOLA**: No per-user or per-project data — global client metadata only ✅

### Modified endpoint: `POST /api/v1/rendering/screenshots`
- No new inputs — confidence computed from existing HTML input
- Confidence data is derived (read-only analysis), no new external calls
- Response adds optional fields — backwards compatible

### Data flow
- Seed YAML is read-only from filesystem (developer-maintained)
- Ontology data loaded via existing `load_ontology()` (cached, immutable)
- No user-controlled data reaches confidence scoring other than HTML already accepted by the existing endpoint

## Verification

- [ ] `make check` passes (lint, types, tests, security)
- [ ] Simple table-based email + Gmail → confidence >70%
- [ ] Complex email (flexbox, VML, dark mode) + Outlook desktop → confidence <70%, "Word table cell width" in blind spots
- [ ] Simple email + Thunderbird → confidence >75%
- [ ] `POST /screenshots` response includes `confidence_score`, `confidence_breakdown`, `confidence_recommendations`
- [ ] `GET /confidence/gmail_web` returns seed data with accuracy=0.80
- [ ] `GET /confidence/nonexistent` returns defaults (accuracy=0.5)
- [ ] All 14 profiles score without error
- [ ] New columns nullable — no data migration needed
