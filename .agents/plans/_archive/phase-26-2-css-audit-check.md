# Plan: Phase 26.2 — Per-Build CSS Compatibility Audit in QA Output

## Context
The ontology-driven CSS compatibility data and per-build conversion metadata already exist (`OptimizedCSS.removed_properties`, `OptimizedCSS.conversions` from `EmailCSSCompiler.optimize_css()`), but this data is only logged — it never reaches the user. This plan surfaces it as a proper QA check result with a per-client compatibility matrix, severity classification, and a frontend visualization panel.

## Key Findings from Research

### Existing Patterns
- **QA checks** follow `QACheckProtocol`: `async run(self, html: str, config: QACheckConfig | None = None) -> QACheckResult`
- **QACheckResult** has: `check_name`, `passed`, `score` (0–1), `details` (str | None), `severity` (str)
- **ALL_CHECKS** in `app/qa_engine/checks/__init__.py` — list of 13 check instances
- **QAEngineService.run_checks()** iterates `ALL_CHECKS`, respects `check_config.enabled`, stores results in DB
- **QACheckConfig** has: `enabled`, `severity`, `threshold`, `params` (dict[str, Any])
- **EmailCSSCompiler** — `optimize_css(html) -> OptimizedCSS` (stages 1-5, no inlining). Constructor takes `target_clients: list[str] | None`
- **OptimizedCSS** — `html`, `removed_properties: list[str]`, `conversions: list[CSSConversion]`, `warnings`, `optimize_time_ms`
- **CSSConversion** — `original_property`, `original_value`, `replacement_property`, `replacement_value`, `reason`, `affected_clients: tuple[str, ...]`
- **OntologyRegistry** — `get_support(property_id, client_id) -> SupportLevel`, `find_property_by_name(css_name, value?) -> CSSProperty | None`, `find_client_by_name(name) -> EmailClient | None`, `clients_not_supporting(property_id)`, `fallbacks_for(property_id)`, `engine_support(property_id)`
- **SupportLevel** — FULL, PARTIAL, NONE, UNKNOWN
- **CssSupportCheck** — existing check uses `unsupported_css_in_html()` + rule engine. Engine-level summary already included via `engines_not_supporting()`.
- **QAResultsPanel** (frontend) — renders checks as list items via `QACheckItem`, then collapsible sections for Visual QA, Chaos, Property Testing, Outlook Advisor, CSS Compiler, Gmail, Ontology Sync, Competitive Report. New panel follows same pattern.

### Design Decisions
1. **New check, not modifying existing `CssSupportCheck`** — the css_support check does rule-based CSS syntax validation + ontology unsupported-property scanning. The css_audit check does per-client compatibility matrix from compilation output. Different concerns, different outputs.
2. **`QACheckResult.details` is a plain string** — for the matrix data we'll serialize the structured output as JSON in `details`, which the frontend can parse. This avoids schema changes to the existing `QACheckResult` model.
3. **No schema migration needed** — `QACheckResult` details field stores any string, and check results are serialized to JSON in the DB's `checks` column.
4. **No new API endpoint** — the css_audit check runs as part of the standard `run_checks()` flow.

## Files to Create

### Backend
- `app/qa_engine/checks/css_audit.py` — `CSSAuditCheck` class

### Frontend
- `cms/apps/web/src/components/qa/CSSAuditPanel.tsx` — CSS audit visualization panel

## Files to Modify

### Backend
- `app/qa_engine/checks/__init__.py` — register `CSSAuditCheck` in `ALL_CHECKS`

### Frontend
- `cms/apps/web/src/components/workspace/qa-results-panel.tsx` — add `CSSAuditPanel` section
- `cms/apps/web/src/types/qa.ts` — add `CSSAuditDetails` frontend type

## Implementation Steps

### Step 1: Create `app/qa_engine/checks/css_audit.py`

```python
"""Per-build CSS compatibility audit check.

Surfaces ontology-driven CSS compatibility data as a per-client matrix
showing which properties survive, were converted, or were removed in
each target email client.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any

from app.email_engine.css_compiler.compiler import EmailCSSCompiler, OptimizedCSS
from app.email_engine.css_compiler.conversions import CSSConversion
from app.knowledge.ontology.registry import load_ontology
from app.knowledge.ontology.types import SupportLevel
from app.qa_engine.check_config import QACheckConfig
from app.qa_engine.schemas import QACheckResult

_DEFAULT_TARGET_CLIENTS = [
    "gmail-web",
    "outlook-web",
    "apple-mail",
    "yahoo-mail-web",
    "samsung-mail",
]


class PropertyStatus(str, Enum):
    """Support status for a CSS property in a specific client."""

    SUPPORTED = "supported"
    CONVERTED = "converted"
    REMOVED = "removed"
    PARTIAL = "partial"


class CSSAuditCheck:
    """Per-build CSS compatibility audit.

    Runs the CSS compiler in optimize-only mode and builds a per-client
    matrix showing the support status of every CSS property used in the
    email. Severity classification:
    - error: property removed with no fallback in a tier-1 client
    - warning: property converted to fallback
    - info: property has partial support
    """

    name = "css_audit"

    async def run(
        self,
        html: str,
        config: QACheckConfig | None = None,
        *,
        compilation_result: OptimizedCSS | None = None,
    ) -> QACheckResult:
        target_clients: list[str] = (
            config.params.get("target_clients", _DEFAULT_TARGET_CLIENTS)
            if config
            else _DEFAULT_TARGET_CLIENTS
        )
        tier1_clients: list[str] = (
            config.params.get("tier1_clients", ["gmail-web", "outlook-web"])
            if config
            else ["gmail-web", "outlook-web"]
        )

        # Use pre-computed result or run optimizer
        if compilation_result is None:
            compiler = EmailCSSCompiler(target_clients=target_clients)
            compilation_result = compiler.optimize_css(html)

        registry = load_ontology()

        # Collect all CSS properties used in the HTML via ontology scan
        from app.knowledge.ontology.query import unsupported_css_in_html

        ontology_issues = unsupported_css_in_html(html)

        # Build sets for quick lookup from compilation result
        removed_set: set[str] = set(compilation_result.removed_properties)
        conversion_map: dict[str, CSSConversion] = {}
        for conv in compilation_result.conversions:
            conversion_map[conv.original_property] = conv

        # Build per-client compatibility matrix
        matrix: dict[str, dict[str, str]] = {}
        all_properties: set[str] = set()

        for issue in ontology_issues:
            prop_name = str(issue["property_name"])
            all_properties.add(prop_name)

        # Also include converted/removed properties not in ontology issues
        for prop in removed_set:
            all_properties.add(prop)
        for prop in conversion_map:
            all_properties.add(prop)

        per_client_supported: dict[str, int] = {}
        total_props = len(all_properties) if all_properties else 1

        for client_id in target_clients:
            client_statuses: dict[str, str] = {}
            supported_count = 0

            for prop_name in sorted(all_properties):
                # Determine status for this property in this client
                if prop_name in removed_set:
                    # Check if this client specifically caused the removal
                    css_prop = registry.find_property_by_name(prop_name)
                    if css_prop:
                        support = registry.get_support(css_prop.id, client_id)
                        if support == SupportLevel.NONE:
                            client_statuses[prop_name] = PropertyStatus.REMOVED.value
                        elif support == SupportLevel.PARTIAL:
                            client_statuses[prop_name] = PropertyStatus.PARTIAL.value
                            supported_count += 1
                        else:
                            # Removed for other clients, but this client supports it
                            client_statuses[prop_name] = PropertyStatus.SUPPORTED.value
                            supported_count += 1
                    else:
                        client_statuses[prop_name] = PropertyStatus.REMOVED.value
                elif prop_name in conversion_map:
                    conv = conversion_map[prop_name]
                    if client_id in conv.affected_clients:
                        client_statuses[prop_name] = PropertyStatus.CONVERTED.value
                    else:
                        client_statuses[prop_name] = PropertyStatus.SUPPORTED.value
                        supported_count += 1
                else:
                    # Check ontology support
                    css_prop = registry.find_property_by_name(prop_name)
                    if css_prop:
                        support = registry.get_support(css_prop.id, client_id)
                        if support == SupportLevel.NONE:
                            client_statuses[prop_name] = PropertyStatus.REMOVED.value
                        elif support == SupportLevel.PARTIAL:
                            client_statuses[prop_name] = PropertyStatus.PARTIAL.value
                            supported_count += 1
                        else:
                            client_statuses[prop_name] = PropertyStatus.SUPPORTED.value
                            supported_count += 1
                    else:
                        # Property not in ontology — assume supported
                        client_statuses[prop_name] = PropertyStatus.SUPPORTED.value
                        supported_count += 1

            matrix[client_id] = client_statuses
            per_client_supported[client_id] = supported_count

        # Calculate per-client coverage scores
        client_coverage: dict[str, float] = {}
        for client_id in target_clients:
            client_coverage[client_id] = round(
                (per_client_supported.get(client_id, 0) / total_props) * 100, 1
            )

        # Overall coverage score (average across target clients)
        overall_coverage = (
            round(sum(client_coverage.values()) / len(client_coverage), 1)
            if client_coverage
            else 100.0
        )

        # Severity classification
        errors: list[str] = []
        warnings: list[str] = []
        infos: list[str] = []

        for prop_name in sorted(all_properties):
            for client_id in tier1_clients:
                status = matrix.get(client_id, {}).get(prop_name)
                if status == PropertyStatus.REMOVED.value:
                    # Check if fallback exists
                    css_prop = registry.find_property_by_name(prop_name)
                    has_fallback = bool(css_prop and registry.fallbacks_for(css_prop.id))
                    if not has_fallback:
                        errors.append(f"{prop_name} removed in {client_id} (no fallback)")
                    else:
                        warnings.append(f"{prop_name} removed in {client_id} (fallback available)")
                elif status == PropertyStatus.CONVERTED.value:
                    warnings.append(f"{prop_name} converted in {client_id}")
                elif status == PropertyStatus.PARTIAL.value:
                    infos.append(f"{prop_name} partial support in {client_id}")

        # Build structured details as JSON
        structured_details: dict[str, Any] = {
            "compatibility_matrix": matrix,
            "conversions": [
                {
                    "original_property": c.original_property,
                    "original_value": c.original_value,
                    "replacement_property": c.replacement_property,
                    "replacement_value": c.replacement_value,
                    "reason": c.reason,
                    "affected_clients": list(c.affected_clients),
                }
                for c in compilation_result.conversions
            ],
            "removed_properties": compilation_result.removed_properties,
            "client_coverage_score": client_coverage,
            "overall_coverage_score": overall_coverage,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "info_count": len(infos),
            "issues": errors[:5] + warnings[:5],
        }

        has_errors = len(errors) > 0
        has_warnings = len(warnings) > 0
        severity = "error" if has_errors else ("warning" if has_warnings else "info")
        passed = not has_errors

        # Score: normalized coverage (0–1)
        score = round(overall_coverage / 100.0, 2)

        return QACheckResult(
            check_name=self.name,
            passed=passed,
            score=max(0.0, min(1.0, score)),
            details=json.dumps(structured_details),
            severity=severity,
        )
```

### Step 2: Register in `app/qa_engine/checks/__init__.py`

Add import and instance to `ALL_CHECKS`:

```python
# Add import:
from app.qa_engine.checks.css_audit import CSSAuditCheck

# Add to ALL_CHECKS list (after CssSupportCheck):
ALL_CHECKS: list[QACheckProtocol] = [
    HtmlValidationCheck(),
    CssSupportCheck(),
    CSSAuditCheck(),        # ← new: per-build CSS compatibility audit
    FileSizeCheck(),
    # ... rest unchanged
]
```

### Step 3: Add frontend type `CSSAuditDetails` in `cms/apps/web/src/types/qa.ts`

```typescript
/** Structured details from the css_audit QA check. */
export interface CSSAuditConversion {
  original_property: string;
  original_value: string;
  replacement_property: string;
  replacement_value: string;
  reason: string;
  affected_clients: string[];
}

export interface CSSAuditDetails {
  compatibility_matrix: Record<string, Record<string, "supported" | "converted" | "removed" | "partial">>;
  conversions: CSSAuditConversion[];
  removed_properties: string[];
  client_coverage_score: Record<string, number>;
  overall_coverage_score: number;
  error_count: number;
  warning_count: number;
  info_count: number;
  issues: string[];
}
```

### Step 4: Create `cms/apps/web/src/components/qa/CSSAuditPanel.tsx`

Collapsible panel matching existing pattern (ChaosTestPanel, PropertyTestPanel). Parses `details` JSON from the `css_audit` check result.

```tsx
"use client";

import { useState, useMemo } from "react";
import { ChevronDown, ChevronUp, ShieldCheck, AlertTriangle, XCircle, Info } from "lucide-react";
import type { QACheckResult } from "@/types/qa";
import type { CSSAuditDetails } from "@/types/qa";

interface CSSAuditPanelProps {
  check: QACheckResult | undefined;
}

const STATUS_COLORS: Record<string, string> = {
  supported: "bg-status-success/20 text-status-success",
  converted: "bg-status-warning/20 text-status-warning",
  removed: "bg-destructive/20 text-destructive",
  partial: "bg-badge-info-bg text-badge-info-text",
};

const STATUS_LABELS: Record<string, string> = {
  supported: "✓",
  converted: "~",
  removed: "✗",
  partial: "◐",
};

type FilterMode = "all" | "errors" | "warnings";

export function CSSAuditPanel({ check }: CSSAuditPanelProps) {
  const [expanded, setExpanded] = useState(false);
  const [filter, setFilter] = useState<FilterMode>("all");

  const details = useMemo<CSSAuditDetails | null>(() => {
    if (!check?.details) return null;
    try {
      return JSON.parse(check.details) as CSSAuditDetails;
    } catch {
      return null;
    }
  }, [check?.details]);

  if (!check || !details) return null;

  const clients = Object.keys(details.compatibility_matrix);
  const allProperties = clients.length > 0
    ? Object.keys(details.compatibility_matrix[clients[0]] ?? {}).sort()
    : [];

  const filteredProperties = allProperties.filter((prop) => {
    if (filter === "all") return true;
    return clients.some((client) => {
      const status = details.compatibility_matrix[client]?.[prop];
      if (filter === "errors") return status === "removed";
      if (filter === "warnings") return status === "converted" || status === "partial";
      return true;
    });
  });

  const formatClientName = (id: string) =>
    id.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

  return (
    <div>
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between text-sm font-medium text-foreground"
      >
        <span className="flex items-center gap-2">
          {check.passed ? (
            <ShieldCheck className="h-4 w-4 text-status-success" />
          ) : (
            <AlertTriangle className="h-4 w-4 text-status-warning" />
          )}
          CSS Compatibility
          <span className="text-xs text-muted-foreground">
            {details.overall_coverage_score}%
          </span>
        </span>
        {expanded ? (
          <ChevronUp className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        )}
      </button>

      {expanded && (
        <div className="mt-3 space-y-3">
          {/* Coverage bars */}
          <div className="space-y-1.5">
            {clients.map((client) => (
              <div key={client} className="flex items-center gap-2">
                <span className="w-24 truncate text-xs text-muted-foreground">
                  {formatClientName(client)}
                </span>
                <div className="h-1.5 flex-1 rounded-full bg-muted">
                  <div
                    className={`h-1.5 rounded-full transition-all ${
                      (details.client_coverage_score[client] ?? 0) >= 90
                        ? "bg-status-success"
                        : (details.client_coverage_score[client] ?? 0) >= 70
                          ? "bg-status-warning"
                          : "bg-destructive"
                    }`}
                    style={{ width: `${details.client_coverage_score[client] ?? 0}%` }}
                  />
                </div>
                <span className="w-10 text-right text-xs text-muted-foreground">
                  {details.client_coverage_score[client] ?? 0}%
                </span>
              </div>
            ))}
          </div>

          {/* Filter buttons */}
          <div className="flex gap-1">
            {(["all", "errors", "warnings"] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => setFilter(mode)}
                className={`rounded px-2 py-0.5 text-xs transition-colors ${
                  filter === mode
                    ? "bg-accent text-foreground"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {mode === "all" ? `All (${allProperties.length})` :
                 mode === "errors" ? `Errors (${details.error_count})` :
                 `Warnings (${details.warning_count})`}
              </button>
            ))}
          </div>

          {/* Matrix table */}
          {filteredProperties.length > 0 && (
            <div className="overflow-x-auto rounded border border-border">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border bg-muted/50">
                    <th className="px-2 py-1.5 text-left font-medium text-muted-foreground">
                      Property
                    </th>
                    {clients.map((client) => (
                      <th
                        key={client}
                        className="px-2 py-1.5 text-center font-medium text-muted-foreground"
                        title={formatClientName(client)}
                      >
                        {formatClientName(client).slice(0, 8)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filteredProperties.map((prop) => (
                    <tr key={prop} className="border-b border-border last:border-0">
                      <td className="px-2 py-1 font-mono text-foreground">{prop}</td>
                      {clients.map((client) => {
                        const status = details.compatibility_matrix[client]?.[prop] ?? "supported";
                        return (
                          <td key={client} className="px-2 py-1 text-center">
                            <span
                              className={`inline-flex h-5 w-5 items-center justify-center rounded text-xs font-medium ${STATUS_COLORS[status] ?? ""}`}
                              title={`${prop}: ${status} in ${formatClientName(client)}`}
                            >
                              {STATUS_LABELS[status] ?? "?"}
                            </span>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Conversions detail */}
          {details.conversions.length > 0 && (
            <details className="text-xs">
              <summary className="cursor-pointer font-medium text-muted-foreground hover:text-foreground">
                {details.conversions.length} conversion{details.conversions.length > 1 ? "s" : ""} applied
              </summary>
              <div className="mt-1.5 space-y-1">
                {details.conversions.map((conv, i) => (
                  <div key={i} className="rounded border border-border px-2 py-1.5">
                    <div className="flex items-center gap-1">
                      <span className="font-mono text-destructive line-through">
                        {conv.original_property}: {conv.original_value}
                      </span>
                      <span className="text-muted-foreground">→</span>
                      <span className="font-mono text-status-success">
                        {conv.replacement_property}: {conv.replacement_value}
                      </span>
                    </div>
                    <p className="mt-0.5 text-muted-foreground">{conv.reason}</p>
                  </div>
                ))}
              </div>
            </details>
          )}

          {/* Issues summary */}
          {details.issues.length > 0 && (
            <div className="space-y-1">
              {details.issues.map((issue, i) => (
                <div key={i} className="flex items-start gap-1.5 text-xs">
                  {issue.includes("no fallback") ? (
                    <XCircle className="mt-0.5 h-3 w-3 shrink-0 text-destructive" />
                  ) : issue.includes("converted") ? (
                    <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-status-warning" />
                  ) : (
                    <Info className="mt-0.5 h-3 w-3 shrink-0 text-badge-info-text" />
                  )}
                  <span className="text-muted-foreground">{issue}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

### Step 5: Wire `CSSAuditPanel` into `qa-results-panel.tsx`

Add import and render section:

```tsx
// Add import:
import { CSSAuditPanel } from "@/components/qa/CSSAuditPanel";

// Inside the component, after the checks list and before Visual QA section, add:
const cssAuditCheck = useMemo(
  () => checks.find((c) => c.check_name === "css_audit"),
  [checks]
);

// In JSX, add after the passed checks collapsible section (line ~177), before Visual QA:
{cssAuditCheck && (
  <div className="border-t border-border px-4 py-3">
    <CSSAuditPanel check={cssAuditCheck} />
  </div>
)}
```

### Step 6: Backend tests — `app/qa_engine/tests/test_css_audit.py`

```python
"""Tests for the CSS audit QA check."""

from __future__ import annotations

import json

import pytest

from app.qa_engine.checks.css_audit import CSSAuditCheck, PropertyStatus


@pytest.fixture
def check() -> CSSAuditCheck:
    return CSSAuditCheck()


class TestCSSAuditCheck:
    """Test suite for CSSAuditCheck."""

    async def test_simple_html_high_coverage(self, check: CSSAuditCheck) -> None:
        """Simple HTML with universally-supported properties should score high."""
        html = "<html><head><style>body { color: #000; font-size: 16px; }</style></head><body>Hello</body></html>"
        result = await check.run(html)
        assert result.check_name == "css_audit"
        assert result.passed is True
        assert result.score >= 0.8
        details = json.loads(result.details or "{}")
        assert "compatibility_matrix" in details
        assert "client_coverage_score" in details

    async def test_unsupported_property_detected(self, check: CSSAuditCheck) -> None:
        """Properties unsupported in major clients should be flagged."""
        html = "<html><head><style>body { border-radius: 8px; }</style></head><body>Hello</body></html>"
        result = await check.run(html)
        details = json.loads(result.details or "{}")
        matrix = details.get("compatibility_matrix", {})
        # At least one client should show removed or partial
        statuses = set()
        for client_data in matrix.values():
            for status in client_data.values():
                statuses.add(status)
        # border-radius is commonly unsupported in Outlook
        assert PropertyStatus.REMOVED.value in statuses or PropertyStatus.PARTIAL.value in statuses or PropertyStatus.CONVERTED.value in statuses

    async def test_empty_css_full_coverage(self, check: CSSAuditCheck) -> None:
        """HTML with no CSS should get 100% coverage."""
        html = "<html><head></head><body>Hello</body></html>"
        result = await check.run(html)
        assert result.passed is True
        assert result.score >= 0.9  # No properties = no issues
        details = json.loads(result.details or "{}")
        assert details.get("error_count", 0) == 0

    async def test_custom_target_clients(self, check: CSSAuditCheck) -> None:
        """Custom target_clients should be respected via config params."""
        from app.qa_engine.check_config import QACheckConfig

        html = "<html><head><style>div { color: red; }</style></head><body><div>Test</div></body></html>"
        config = QACheckConfig(params={"target_clients": ["gmail-web"]})
        result = await check.run(html, config)
        details = json.loads(result.details or "{}")
        assert list(details["compatibility_matrix"].keys()) == ["gmail-web"]
        assert list(details["client_coverage_score"].keys()) == ["gmail-web"]

    async def test_pre_computed_compilation_result(self, check: CSSAuditCheck) -> None:
        """Passing a pre-computed OptimizedCSS should skip re-compilation."""
        from app.email_engine.css_compiler.compiler import OptimizedCSS

        pre_computed = OptimizedCSS(
            html="<html><head></head><body>Test</body></html>",
            removed_properties=["flex"],
            conversions=[],
            warnings=[],
            optimize_time_ms=0.0,
        )
        result = await check.run(
            "<html><head><style>div { flex: 1; }</style></head><body><div>Test</div></body></html>",
            compilation_result=pre_computed,
        )
        details = json.loads(result.details or "{}")
        assert "flex" in details["removed_properties"]

    async def test_details_is_valid_json(self, check: CSSAuditCheck) -> None:
        """Details field should be valid parseable JSON."""
        html = "<html><head><style>body { margin: 0; padding: 0; color: #333; }</style></head><body>Hello</body></html>"
        result = await check.run(html)
        assert result.details is not None
        details = json.loads(result.details)
        assert isinstance(details, dict)
        assert "overall_coverage_score" in details
        assert isinstance(details["overall_coverage_score"], (int, float))

    async def test_score_between_zero_and_one(self, check: CSSAuditCheck) -> None:
        """Score should always be between 0 and 1."""
        html = "<html><head><style>div { border-radius: 8px; box-shadow: 0 0 5px #ccc; flex: 1; grid-template-columns: 1fr 1fr; }</style></head><body><div>Test</div></body></html>"
        result = await check.run(html)
        assert 0.0 <= result.score <= 1.0
```

## Security Checklist
- [x] **No new endpoints** — css_audit runs within existing `run_checks()` flow, which already has `Depends(get_current_user)`, rate limiting, and Pydantic validation
- [x] **Read-only** — only reads ontology data and CSS compilation output, no writes
- [x] **No user input reaches SQL** — ontology queries are in-memory lookups
- [x] **Error responses** — uses standard `QACheckResult`, auto-sanitized via `AppError` hierarchy
- [x] **No secrets in logs** — only CSS property names and support levels logged

## Verification
- [ ] `make test` passes — new tests in `test_css_audit.py` all green
- [ ] `make lint` passes — ruff format + lint clean
- [ ] `make types` passes — mypy + pyright type-check clean
- [ ] `make check-fe` passes — frontend type-check + build clean
- [ ] Manual: Build email with `border-radius` → css_audit shows `removed` for Outlook
- [ ] Manual: Build simple email → css_audit shows high coverage score
- [ ] Manual: Frontend matrix renders in QA panel
