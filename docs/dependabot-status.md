# Dependabot Alert Status

Snapshot: 2026-05-11.

## Resolved by this PR

| Alert | Package | Severity | Manifest | Action |
|---|---|---|---|---|
| #100 | postcss | medium | services/maizzle-builder/package-lock.json | `npm update postcss` → 8.5.10 |
| #99 | postcss | medium | cms/pnpm-lock.yaml | Added `"postcss": ">=8.5.10"` to pnpm overrides; `pnpm install` |

## Held — risk does not apply (litellm)

| Alert | Package | Severity | Advisory | Disposition |
|---|---|---|---|---|
| #106 | litellm | high | [GHSA-wxxx-gvqv-xp7p](https://github.com/advisories/GHSA-wxxx-gvqv-xp7p) — Sandbox escape via Proxy `/guardrails/test_custom_code` endpoint | Held at 1.83.0 |
| #103 | litellm | high | [GHSA-v4p8-mg3p-g94g](https://github.com/advisories/GHSA-v4p8-mg3p-g94g) — Authenticated command execution via Proxy MCP stdio test endpoints | Held at 1.83.0 |
| #102 | litellm | critical | [GHSA-r75f-5x8p-qvmc](https://github.com/advisories/GHSA-r75f-5x8p-qvmc) — SQL injection in Proxy API key verification | Held at 1.83.0 |
| #98 | litellm | high | [GHSA-xqmj-j6mv-4862](https://github.com/advisories/GHSA-xqmj-j6mv-4862) — SSTI in Proxy `/prompts/test` endpoint | Held at 1.83.0 |

**Why held**: all four CVEs target the LiteLLM **Proxy server** — an HTTP gateway
service. We do not run the LiteLLM Proxy. We pull `litellm` transitively
through `cognee` (the optional `[graph]` extra) and use it only as an SDK
(model routing). No HTTP endpoints from litellm are exposed.

**Why we can't blindly bump**: `litellm>=1.83.7` strictly pins
`python-dotenv==1.0.1`. Our project requires `python-dotenv>=1.2.2` to patch
[GHSA-xx5x-9xc9-rrqr](https://github.com/advisories/GHSA-xx5x-9xc9-rrqr)
(symlink-following in `set_key`). Upgrading litellm would re-introduce a
real (if narrow) CVE to fix two CVEs that don't apply to us.

**Re-check trigger**: bump to a litellm version that loosens its dotenv pin,
or onboard the LiteLLM Proxy (which would make these CVEs apply).

## Held — no upstream fix

| Alert | Package | Severity | Advisory | Disposition |
|---|---|---|---|---|
| #101 | pip | medium | [GHSA-58qw-9mgm-455v](https://github.com/advisories/GHSA-58qw-9mgm-455v) — handling concatenated tar+ZIP as ZIP | Awaiting upstream patch |

**Why held**: no patched version exists yet. The vulnerability is in pip's
parsing of attacker-crafted package files. Our pip resolves only against
PyPI through `uv` — we don't pip-install attacker-controlled URLs.

**Re-check trigger**: pip releases a patched version, or `uv` advertises
mitigation.

## Pre-existing exclusions (from `5d22d617`)

The prior dep-pinning pass also documented three "no upstream fix" alerts:

- `mjml` (CVE-2020-12827 incomplete fix)
- `html-minifier` (unmaintained ReDoS)
- `lupa` (sandbox escape, no patched release)

These remain held under the same logic — re-check when upstream releases.

## How to re-check

```bash
gh api repos/<owner>/<repo>/dependabot/alerts \
  --jq '.[] | select(.state=="open") | {number, severity: .security_advisory.severity, package: .security_vulnerability.package.name, patched: .security_vulnerability.first_patched_version.identifier}'
```
