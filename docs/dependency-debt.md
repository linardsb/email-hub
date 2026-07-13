# Dependency Debt — Deferred SCA Findings

Registry of vulnerability findings surfaced by CI tools (pip-audit, Trivy)
that are intentionally suppressed at the gate. Each entry must record:
package, advisory ID, severity, why deferred, expected fix trigger, owner.

For Dependabot-surfaced advisories, see `docs/dependabot-status.md` — the same
upstream CVE may appear in both registries when both gates flag it.

## pip-audit deferrals (`uv run pip-audit --strict --ignore-vuln <ID>`)

| Package | Advisory | Severity | Pinned at | Why deferred | Fix trigger | Owner |
|---|---|---|---|---|---|---|
| pip | [CVE-2026-3219](https://github.com/advisories/GHSA-58qw-9mgm-455v) (GHSA-58qw-9mgm-455v) | medium | 26.0.1 | No upstream patch released; vulnerability is in pip's parsing of attacker-crafted package files (tar+ZIP). We resolve only against PyPI through `uv` and do not pip-install attacker-controlled URLs. Same item tracked as Dependabot #101 in `docs/dependabot-status.md`. | pip releases a patched version | Linards |
| pip | [PYSEC-2026-196](https://osv.dev/vulnerability/PYSEC-2026-196) | high | 26.1.1 | Newly disclosed (fix: pip 26.1.2). pip is the installer, not a project dependency; we resolve only against PyPI through `uv` and do not pip-install attacker-controlled URLs. Same low-reachability rationale as CVE-2026-3219 above. | bump pip to >=26.1.2 | Linards |

CI invocation lives at `.github/workflows/ci.yml` (backend job, `pip-audit` step) and `Makefile :: ci-be`.

## Trivy deferrals (`.trivyignore`)

Populated as Phase 2 §2.1 lands. First scan triage will append base-image CVEs
that have no upstream fix; each entry needs an expiration date and re-check trigger.

| Image | CVE | Severity | Why deferred | Expires | Owner |
|---|---|---|---|---|---|
| pgvector/pgvector:pg16 (gobinary) | CVE-2025-68121 | CRITICAL | Go stdlib `crypto/tls` cert-validation flaw inside a Go binary shipped in the upstream pgvector base image (likely `gosu`). We don't build or vendor this binary, so we can't bump its Go toolchain. The vulnerability requires attacker-supplied TLS input; `gosu` does not handle network input, so reachability is effectively zero. | 2026-08-31 | Linards |
| pgvector/pgvector:pg16 (gobinary) | CVE-2025-58183 | HIGH | Go stdlib `archive/tar` unbounded allocation. Same `gobinary` as above; the CVE class requires attacker-controlled archive input. | 2026-08-31 | Linards |
| pgvector/pgvector:pg16 (gobinary) | CVE-2025-61726 | HIGH | Go stdlib `net/url` memory exhaustion. Same `gobinary`; not exposed to network input in our runtime. | 2026-08-31 | Linards |
| pgvector/pgvector:pg16 (gobinary) | CVE-2025-61728 | HIGH | Go stdlib `archive/zip` CPU consumption. Same `gobinary`; archive parsing not invoked at runtime. | 2026-08-31 | Linards |
| pgvector/pgvector:pg16 (gobinary) | CVE-2025-61729 | HIGH | Go stdlib `crypto/x509` DoS. Same `gobinary`; not on TLS code path in our runtime. | 2026-08-31 | Linards |
| pgvector/pgvector:pg16 (gobinary) | CVE-2026-25679 | HIGH | Go stdlib `net/url` IPv6 host-literal parsing. Same `gobinary`; not invoked. | 2026-08-31 | Linards |
| pgvector/pgvector:pg16 (gobinary) | CVE-2026-32280 | HIGH | Go stdlib `crypto/tls` DoS. Same `gobinary`; not on TLS code path. | 2026-08-31 | Linards |
| pgvector/pgvector:pg16 (gobinary) | CVE-2026-32281 | HIGH | Go stdlib `crypto/x509` DoS. Same `gobinary`; not on cert-parse code path. | 2026-08-31 | Linards |
| pgvector/pgvector:pg16 (gobinary) | CVE-2026-32283 | HIGH | Go stdlib `crypto/tls` key-update DoS. Same `gobinary`; not on TLS code path. | 2026-08-31 | Linards |
| pgvector/pgvector:pg16 (gobinary) | CVE-2026-33811 | HIGH | Go stdlib `net` cgo-resolver `LookupCNAME` DoS on overlong CNAME chains. Same `gobinary`; gosu does not run a DNS resolver. | 2026-08-31 | Linards |
| pgvector/pgvector:pg16 (gobinary) | CVE-2026-33814 | HIGH | Go stdlib `net/http` HTTP/2 SETTINGS infinite loop in client transport. Same `gobinary`; gosu does not run an HTTP/2 client or server. | 2026-08-31 | Linards |
| pgvector/pgvector:pg16 (gobinary) | CVE-2026-39820 | HIGH | Go stdlib `net/mail` `ParseAddress`/`ParseAddressList` DoS. Same `gobinary`; gosu does not parse mail addresses. | 2026-08-31 | Linards |
| pgvector/pgvector:pg16 (gobinary) | CVE-2026-39836 | HIGH | Go stdlib `net.Dial`/`LookupPort` NUL-byte panic on Windows. Same `gobinary`; gosu runs on Debian only. | 2026-08-31 | Linards |
| pgvector/pgvector:pg16 (gobinary) | CVE-2026-42499 | HIGH | Go stdlib `net/mail` `consumePhrase` DoS. Same `gobinary`; gosu does not parse mail input. | 2026-08-31 | Linards |
| pgvector/pgvector:pg16 (gobinary) | CVE-2026-39823 | HIGH | Go stdlib `html/template` — URLs not correctly escaped inside a `<meta>` refresh directive. Same `gobinary` (confirmed `/usr/local/bin/gosu`); gosu renders no HTML templates. | 2026-08-31 | Linards |
| pgvector/pgvector:pg16 (gobinary) | CVE-2026-39825 | HIGH | Go stdlib `net/http/httputil` — `ReverseProxy` forwards query parameters not visible to `Rewrite` funcs (request-smuggling risk). Same `gobinary`; gosu runs no reverse proxy. | 2026-08-31 | Linards |
| pgvector/pgvector:pg16 (gobinary) | CVE-2026-39826 | HIGH | Go stdlib `html/template` — a `<script>` tag with an empty `type` attribute breaks contextual auto-escaping. Same `gobinary`; gosu renders no HTML templates. | 2026-08-31 | Linards |
| pgvector/pgvector:pg16 (gobinary) | CVE-2026-42504 | HIGH | Go stdlib `mime`/`net/textproto` — decoding a maliciously-crafted MIME header with many parts causes DoS. Same `gobinary`; gosu does not decode MIME headers. | 2026-08-31 | Linards |
| pgvector/pgvector:pg16 (gobinary) | CVE-2026-27145 | HIGH | Go stdlib `crypto/x509` DoS via excessive processing of DNS names during certificate parsing. Same `gobinary` (`/usr/local/bin/gosu`); gosu does not parse certificates. | 2026-08-31 | Linards |

**Re-check trigger:** when pgvector publishes a new `pg16` image (different digest from
`sha256:7d400e34…`), pull it and re-run Trivy. If the scanner no longer detects the embedded
Go binary at the old version, drop these entries from `.trivyignore` and this table.

**Note:** OpenSSL/libssl3 CVEs (CVE-2026-31789 + 4 related HIGHs) are *fixed* by an
`apt-get upgrade libssl3 openssl` step in `db/Dockerfile` rather than ignored — Debian
ships a patched 3.0.19-1~deb12u2 in `bookworm-security`. They never reach this table.

## mypy stub-gap deferrals (post-Phase 3 §3.5)

Recorded here once Phase 3 §3.5 reduces the `[[tool.mypy.overrides]]` block
in `pyproject.toml` — only the modules we cannot remove (no published stubs)
remain, with a one-line justification.

## How to re-check

```bash
# pip-audit (backend)
uv run pip-audit --strict

# Trivy (after §2.1 lands)
docker build -t email-hub:local .
trivy image --severity HIGH,CRITICAL --ignore-unfixed email-hub:local
```
