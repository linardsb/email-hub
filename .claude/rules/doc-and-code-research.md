---
description: Token-efficient research using jDocMunch and jCodeMunch indexes
globs: "**/*"
---

# Document & Code Research Rules

## jDocMunch — Documentation Search
Repo: `local/email-hub`

**NEVER** call `get_document_outline` on large docs (TODO.md, PRD.md — 60+ sections each).

**Instead use:**
- `search_sections(repo, query, doc_path, max_results=3)` — find sections by keyword
- `get_section(repo, section_id)` — read a specific section (~300-600 tokens vs 25k for full file)

**When to use jDocMunch vs Read:**
| File | Method | Why |
|------|--------|-----|
| TODO.md (~95KB) | `search_sections` → `get_section` | 600 tokens vs 25,000 |
| PRD.md (~27KB) | `search_sections` → `get_section` | 400 tokens vs 7,000 |
| CLAUDE.md (~5KB) | `Read` directly | Small enough, 1 call |
| Any .md < 200 lines | `Read` directly | Faster, 1 call |
| Any .md > 200 lines | jDocMunch | Saves context |

**Common section ID patterns for TODO.md:**
- Phase N: `local/email-hub::TODO.md::redacted-email-innovation-hub-implementation-roadmap/phase-{N}-{slug}#2`
- Subtask: append `/{subtask-slug}#3` to the phase ID

## jCodeMunch — Code Search
Repo: `local/email-hub-0ddab3c4`

**Use for cross-file research** (not for editing — use Read for that):
- `search_symbols(repo, query, kind, file_pattern)` — find functions, classes, methods
- `get_file_outline(repo, file_path)` — see structure without reading full file
- `get_symbol(repo, symbol_name)` — get a specific symbol's code
- `find_references(repo, symbol_name)` — find all usages

**When to use jCodeMunch vs Grep/Read:**
| Task | Method |
|------|--------|
| "Which files use X?" | `search_symbols` or `find_references` |
| "What's in this directory?" | `get_file_tree(repo, path_prefix=...)` |
| "Show me this function" | `Read` the file (you'll edit it) |
| "Find string in code" | `Grep` (exact match, faster) |

## Re-indexing
Run when codebase has changed significantly (new files, renamed modules):
- jDocMunch: `index_local(path, incremental=true, use_ai_summaries=false)`
- jCodeMunch: `index_folder(path, incremental=true, use_ai_summaries=false)`
