#!/usr/bin/env python3
"""PreToolUse hook — deterministic guardrails for the email-hub repo.

Adapted from the taxi repo's hook (f2cc6c4); see PORTED-FROM-TAXI.md.
Stdlib only, run with plain `python3` (>=3.8): a `uv run` launcher exits 2
when uv itself fails (e.g. unwritable cache), which would block every tool.
Runs alongside block-dangerous.sh (force push, reset --hard, rm -rf on
protected paths, DROP) and pre-commit-security.sh (staged secrets).

Blocks (exit 2, reason on stderr):
  1. Secret access — .env files, keys, credentials, or dumping the process
     environment. Committed templates (`.env.example`, `.env.*.example`) are
     allowed, and so is one bare `cp <checkout>/.env <worktree>/.env` segment
     (the worktree spin-up recipe).
  2. Database destruction — `alembic downgrade` (directly or via
     safe_alembic.sh), `make db-squash` / squash-migrations.sh, `dropdb`,
     `TRUNCATE`, `docker compose down -v`, `docker volume rm|prune`,
     `docker system prune --volumes`. The local DB is shared by every
     checkout and worktree; a mistake here is not branch-local.
  3. The draft→ready flip — `gh pr ready`, `--undo` and the GraphQL mutations
     behind them. CI's `ready` job is the only path. Also `gh pr merge`
     (the user merges) and `gh pr create` without `--draft`.
  4. Suppressing a code-scanning finding — dismissing an alert through the
     API (CodeQL and Semgrep both report to code scanning), or adding a
     `nosemgrep` / `lgtm[…]` / `codeql[…]` comment to shipped source. The
     user decides suppressions.
  6. Gate settings — `gh api` writes to branch protection, rulesets or
     code-scanning default setup. Reads pass.
  5. The guard fence — writes to `.github/workflows/`, `.github/scripts/`,
     `.claude/hooks/`, `.claude/settings{,.local}.json` and `.semgrepignore`,
     the files that define the gate, its suppressions and this hook. Write
     tools only: a Bash heredoc is the deliberate, visible route for a
     user-approved change to these files (same limit as the taxi original).

Guards 2-4 read a Bash command's text AND (3-4) the text a write tool would
put into a non-`.md` file. Text is all they read: a command written into a
script, or a Make target that wraps one, matches nothing here. They make the
wrong move deliberate rather than convenient. Branch protection on `main` is
the control that holds.

Everything else is allowed. FAILS OPEN: any unexpected error exits 0 so a bug
here can never brick a session.
"""

import json
import os
import re
import sys
from pathlib import Path

ENV_TEMPLATE = re.compile(r"\.env(\.[\w-]+)?\.example\b", re.IGNORECASE)

SECRET_PATH = re.compile(
    r"(?<![\w)\]])\.env\b|\.(pem|key)(?=[\s\"')]|$)|id_rsa|id_ed25519|\.ssh/|\.aws/credentials|\.netrc|credentials\.json",
    re.IGNORECASE,
)

# `os.environ` / `process.env` are not here: they false-positive on every grep
# of settings code, and reading env in code is not a dump. SECRET_PATH's
# lookbehind lets `process.env` / `import.meta.env` through for the same reason.
ENV_DUMP = (
    re.compile(r"\bprintenv\b", re.IGNORECASE),
    re.compile(r"^\s*(\S*/)?env\s*(\||>|$)", re.IGNORECASE),
    re.compile(r"\becho\b.*\$\{?[A-Z_]*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)", re.IGNORECASE),
)

# The one allowed secret-touching segment: copy the main checkout's .env into
# a worktree, nothing else in the segment.
ENV_COPY = re.compile(r"^\s*cp\s+(\S*/)?\.env\s+\S*/\.env\s*$")

CMD_SPLIT = re.compile(r"&&|\|\||[;|\n]")

# Matched per command segment, so `ls alembic/versions | xargs grep downgrade`
# does not trip the alembic pattern across the pipe.
DB_DESTRUCTIVE = (
    re.compile(
        r"\balembic(\s+(-c|--config|-x|-n|--name)\s+\S+|\s+-[\w-]+)*\s+downgrade\b", re.IGNORECASE
    ),
    re.compile(r"\bsafe_alembic\.sh\b.*\bdowngrade\b", re.IGNORECASE),
    re.compile(r"\bmake\b.*\bdb-squash\b", re.IGNORECASE),
    re.compile(r"\bsquash-migrations\.sh\b", re.IGNORECASE),
    re.compile(r"\bdropdb\b", re.IGNORECASE),
    re.compile(r"\btruncate\s+table\b|\b(psql|pgcli)\b.*\btruncate\b", re.IGNORECASE),
    re.compile(
        r"\bdocker[\s-]+compose\b.*\b(down|rm)\b.*(\s-[a-z]*v[a-z]*\b|--volumes)", re.IGNORECASE
    ),
    re.compile(r"\bdocker\s+volume\s+(rm|remove|prune)\b", re.IGNORECASE),
    re.compile(r"\bdocker\s+system\s+prune\b.*--volumes", re.IGNORECASE),
)

PR_READY_FLIP = re.compile(
    r"\bgh\s+pr\s+ready\b|markPullRequestReadyForReview|convertPullRequestToDraft",
    re.IGNORECASE,
)
PR_MERGE = re.compile(
    r"\bgh\s+pr\s+merge\b|pulls/\d+/merge\b|mergePullRequest|enablePullRequestAutoMerge",
    re.IGNORECASE,
)
PR_CREATE = re.compile(r"\bgh\s+pr\s+create\b", re.IGNORECASE)
DRAFT_FLAG = re.compile(r"--draft(?!=false)\b|(?<![\w-])-d\b", re.IGNORECASE)
QUOTED = re.compile(r"\"[^\"]*\"|'[^']*'")
# Opening a PR through the REST API (`gh api …/pulls -f …`) without draft=true.
API_PR_CREATE = re.compile(r"\bgh\s+api\b.*/pulls(?![/\w])", re.IGNORECASE)
API_FIELDS = re.compile(r"\s(-f|-F|--field|--raw-field|--input)[\s=]", re.IGNORECASE)
API_DRAFT = re.compile(r"draft=[\"']?true", re.IGNORECASE)

# Dismissing a code-scanning alert (PATCH …/code-scanning/alerts/N with
# state=dismissed), in either word order; a plain read is allowed.
ALERT_DISMISS = re.compile(
    r"code-scanning/alerts.*?(state=[\"']?dismissed|(-X|--method)[\s=]*[\"']?PATCH|--input)"
    r"|((-X|--method)[\s=]*[\"']?PATCH|state=[\"']?dismissed).*?code-scanning/alerts",
    re.IGNORECASE | re.DOTALL,
)
# Suppression markers for both scanners (D11: CodeQL job in ci.yml + Semgrep).
# Semgrep honours `nosemgrep` / `nosem` in a comment. CodeQL's matcher
# (shared/util/codeql/util/suppression/AlertSuppression.qll) honours
# `lgtm[…]` / `codeql[…]` anywhere in a comment and a bare leading `lgtm`,
# case-insensitively. Bare words outside a comment (e.g. a grep) pass.
SUPPRESSION_COMMENT = re.compile(
    r"(?://|/\*|#|<!--|\{#|--)\s*nosem(?:grep)?\b"
    r"|\b(?:lgtm|codeql)\s*\["
    r"|(?://|/\*|#|;)\s*lgtm\b(?!\s*\[)",
    re.IGNORECASE,
)
# A Bash segment is judged for suppressions only when it writes a file;
# `grep -rn "# nosemgrep" app` is a read.
BASH_WRITES = re.compile(r">|\btee\b|\b(sed|perl)\b.*\s-i|\bpython3?\b", re.IGNORECASE)
SOURCE_SUFFIXES = (
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".html",
    ".sh",
    ".yml",
    ".yaml",
    ".sql",
)

# Writes to the repo settings that ARE the gate: branch protection, rulesets
# and code-scanning default setup. The user applies these (D10/D11); a
# session that can lift branch protection has no backstop. Reads pass.
GATE_SETTINGS = re.compile(
    r"branches/[^\s/]+/protection|/rulesets\b|code-scanning/default-setup", re.IGNORECASE
)
API_WRITE = re.compile(
    r"(-X|--method)[\s=]*[\"']?(PUT|POST|PATCH|DELETE)\b|\s(-f|-F|--field|--raw-field|--input)[\s=]",
    re.IGNORECASE,
)

# Case-insensitive: the macOS disk is, so `.GITHUB/workflows/ci.yml` is ci.yml.
GUARD_FENCE = re.compile(
    r"(^|/)(\.github/(workflows|scripts)/|\.claude/hooks/|\.claude/settings(\.local)?\.json$|\.semgrepignore$)",
    re.IGNORECASE,
)

# Monitor runs a shell command just like Bash.
SHELL_TOOLS = ("Bash", "Monitor")

WRITE_TOOLS = ("Edit", "MultiEdit", "Write", "NotebookEdit")

BLOCKED_ENV_MESSAGE = (
    "BLOCKED: access to secrets is not allowed.\n"
    "Read a committed template (.env.example, .env.production.example) instead.\n"
    "The one allowed form is a bare `cp <checkout>/.env <worktree>/.env`."
)
BLOCKED_DB_MESSAGE = (
    "BLOCKED: this command can destroy local database state (migrations,\n"
    "tables or Docker volumes). The native Postgres is shared by every checkout\n"
    "and worktree. If the user explicitly asked for it, ask them to run it\n"
    "themselves with `! <command>`."
)
BLOCKED_PR_READY_MESSAGE = (
    "BLOCKED: `gh pr ready` is CI's to run, never a model's.\n"
    "A PR leaves draft only when ci.yml's `ready` job sees every gate job green.\n"
    "If it is stuck: read the failing check, fix, push. The user can flip it in\n"
    "the GitHub UI. See CLAUDE.md § PR flow."
)
BLOCKED_ALERT_SUPPRESSION_MESSAGE = (
    "BLOCKED: suppressing a CodeQL / Semgrep finding is the user's call.\n"
    "Fix the finding inside this diff, or leave it and say why under\n"
    "`## Notes for the reviewer`. The user dismisses it, with a reason.\n"
    "(Discussing suppression forms is fine in a .md file, which is exempt.)"
)
BLOCKED_PR_MERGE_MESSAGE = (
    "BLOCKED: merging a PR is the user's call, never a model's.\n"
    "The agent loop ends at a reviewed, green, draft-flipped PR. A green tick can\n"
    "belong to an EARLIER head than the one you are looking at."
)
BLOCKED_PR_CREATE_MESSAGE = (
    "BLOCKED: every PR opens as a draft — add --draft.\n"
    "CI's `ready` job flips it when the gate is green. A PR opened ready cannot\n"
    "be re-drafted by CI if that job then fails."
)
BLOCKED_GUARD_FENCE_MESSAGE = (
    "BLOCKED: this file defines the PR gate, its suppressions, or this hook.\n"
    ".github/workflows/, .github/scripts/, .claude/hooks/, .claude/settings.json\n"
    "and .semgrepignore are fenced: a session that can edit the gate does not\n"
    "have one. If the user explicitly asked for this change, ask them to confirm\n"
    "and make it outside this guard."
)

BLOCKED_GATE_SETTINGS_MESSAGE = (
    "BLOCKED: branch protection, rulesets and code-scanning setup are the gate.\n"
    "The user applies them. Show the exact `gh api` call and ask them to run it\n"
    "with `! <command>`."
)


def _strip_templates(text: str) -> str:
    return ENV_TEMPLATE.sub("", text)


def is_secret_access(tool_name: str, tool_input: dict) -> bool:
    if tool_name in ("Read", *WRITE_TOOLS):
        path = tool_input.get("file_path", "") or tool_input.get("notebook_path", "")
        return bool(SECRET_PATH.search(_strip_templates(path.replace("\\", "/"))))

    if tool_name in ("Grep", "Glob"):
        target = f"{tool_input.get('pattern', '')} {tool_input.get('path', '')} {tool_input.get('glob', '')}"
        return bool(SECRET_PATH.search(_strip_templates(target.replace("\\", "/"))))

    if tool_name in SHELL_TOOLS:
        command = tool_input.get("command", "").replace("\\", "/")
        for segment in CMD_SPLIT.split(command):
            if ENV_COPY.match(segment):
                continue
            if any(p.search(segment) for p in ENV_DUMP):
                return True
            if SECRET_PATH.search(_strip_templates(segment)):
                return True
        return False

    return False


def is_db_destructive(tool_name: str, tool_input: dict) -> bool:
    if tool_name not in SHELL_TOOLS:
        return False
    segments = CMD_SPLIT.split(tool_input.get("command", ""))
    return any(p.search(seg) for seg in segments for p in DB_DESTRUCTIVE)


def _written_texts(tool_input: dict) -> list:
    """Every string a write tool would put into the file."""
    texts = [
        tool_input.get("new_string", ""),
        tool_input.get("content", ""),
        tool_input.get("new_source", ""),
    ]
    texts += [e.get("new_string", "") for e in tool_input.get("edits", []) if isinstance(e, dict)]
    return [t for t in texts if t]


def _guarded_texts(tool_name: str, tool_input: dict) -> list:
    """Bash command text, or write-tool text bound for a non-.md file.

    `.md` is exempt so docs and skills can name the phrases they document.
    """
    if tool_name in SHELL_TOOLS:
        return [tool_input.get("command", "")]
    if tool_name in WRITE_TOOLS:
        path = tool_input.get("file_path", "").replace("\\", "/").lower()
        if path.endswith(".md"):
            return []
        return _written_texts(tool_input)
    return []


def is_pr_ready_flip(tool_name: str, tool_input: dict) -> bool:
    return any(PR_READY_FLIP.search(t) for t in _guarded_texts(tool_name, tool_input))


def is_pr_merge(tool_name: str, tool_input: dict) -> bool:
    return any(PR_MERGE.search(t) for t in _guarded_texts(tool_name, tool_input))


def is_undrafted_pr_create(tool_name: str, tool_input: dict) -> bool:
    if tool_name not in SHELL_TOOLS:
        return False
    for segment in CMD_SPLIT.split(tool_input.get("command", "")):
        # Quoted text is a title or body, never a flag: `-b 'use -d later'`.
        bare = QUOTED.sub("", segment)
        if PR_CREATE.search(segment) and not DRAFT_FLAG.search(bare):
            return True
        if (
            API_PR_CREATE.search(segment)
            and API_FIELDS.search(segment)
            and not API_DRAFT.search(segment)
        ):
            return True
    return False


def _count_suppressions(text: str) -> int:
    return len(SUPPRESSION_COMMENT.findall(text or ""))


def _adds_suppression(tool_name: str, tool_input: dict) -> bool:
    """True if a write tool leaves the file with MORE `nosemgrep` comments.

    Counting, not matching: an Edit whose context carries an existing
    suppression along (3 exist today) must not be blocked.
    """
    if tool_name == "Edit":
        return _count_suppressions(tool_input.get("new_string", "")) > _count_suppressions(
            tool_input.get("old_string", "")
        )
    if tool_name == "MultiEdit":
        return any(
            _count_suppressions(e.get("new_string", ""))
            > _count_suppressions(e.get("old_string", ""))
            for e in tool_input.get("edits", [])
            if isinstance(e, dict)
        )
    if tool_name == "Write":
        path = tool_input.get("file_path", "")
        before = ""
        if Path(path).is_file():
            before = Path(path).read_text(encoding="utf-8", errors="replace")
        return _count_suppressions(tool_input.get("content", "")) > _count_suppressions(before)
    if tool_name == "NotebookEdit":
        return _count_suppressions(tool_input.get("new_source", "")) > 0
    return False


def is_alert_suppression(tool_name: str, tool_input: dict) -> bool:
    for text in _guarded_texts(tool_name, tool_input):
        if ALERT_DISMISS.search(text):
            return True
    if tool_name in SHELL_TOOLS:
        return any(
            BASH_WRITES.search(seg) and SUPPRESSION_COMMENT.search(seg)
            for seg in CMD_SPLIT.split(tool_input.get("command", ""))
        )
    if tool_name in WRITE_TOOLS:
        path = (tool_input.get("file_path", "") or tool_input.get("notebook_path", "")).replace(
            "\\", "/"
        )
        if not path.endswith(SOURCE_SUFFIXES) and tool_name != "NotebookEdit":
            return False
        return _adds_suppression(tool_name, tool_input)
    return False


def is_gate_settings_write(tool_name: str, tool_input: dict) -> bool:
    if tool_name not in SHELL_TOOLS:
        return False
    return any(
        GATE_SETTINGS.search(seg) and API_WRITE.search(seg)
        for seg in CMD_SPLIT.split(tool_input.get("command", ""))
    )


def is_fenced_guard_write(tool_name: str, tool_input: dict) -> bool:
    if tool_name not in WRITE_TOOLS:
        return False
    path = tool_input.get("file_path", "") or tool_input.get("notebook_path", "")
    return bool(GUARD_FENCE.search(os.path.normpath(path.replace("\\", "/"))))


CHECKS = (
    (is_secret_access, BLOCKED_ENV_MESSAGE),
    (is_db_destructive, BLOCKED_DB_MESSAGE),
    (is_pr_ready_flip, BLOCKED_PR_READY_MESSAGE),
    (is_pr_merge, BLOCKED_PR_MERGE_MESSAGE),
    (is_undrafted_pr_create, BLOCKED_PR_CREATE_MESSAGE),
    (is_alert_suppression, BLOCKED_ALERT_SUPPRESSION_MESSAGE),
    (is_fenced_guard_write, BLOCKED_GUARD_FENCE_MESSAGE),
    (is_gate_settings_write, BLOCKED_GATE_SETTINGS_MESSAGE),
)


def main() -> None:
    try:
        data = json.load(sys.stdin)
        tool_name = data.get("tool_name", "")
        tool_input = data.get("tool_input", {}) or {}
        for check, message in CHECKS:
            if check(tool_name, tool_input):
                sys.stderr.write(message + "\n")
                sys.exit(2)
        sys.exit(0)
    except Exception:
        sys.exit(0)  # fail open


if __name__ == "__main__":
    main()
