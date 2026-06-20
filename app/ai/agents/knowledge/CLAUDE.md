# Knowledge Agent

RAG-powered Q&A agent for email development questions. Searches the Hub's knowledge base (20 documents across css_support, best_practices, client_quirks domains) and generates grounded answers with citations.

## Architecture
- **Not an HTML transformer** — Receives question, returns answer with sources
- **Requires DB session** — `KnowledgeService.search()` needs `AsyncSession`
- **Progressive disclosure** — SKILL.md (L1+L2) + 4 L3 skill files loaded on-demand

## Files
- `schemas.py` — `KnowledgeRequest`, `KnowledgeResponse`, `KnowledgeSource`
- `prompt.py` — `detect_relevant_skills()`, `build_system_prompt()`
- `service.py` — `KnowledgeAgentService.process()` (RAG search → LLM → parse)
- `SKILL.md` — Core instructions (grounding rules, answer structure, confidence)
- `skills/` — 4 L3 files (rag_strategies, email_client_engines, can_i_email_reference, citation_rules)

## Eval
- 10 synthetic test cases in `evals/synthetic_data_knowledge.py`
- 5-criteria judge in `evals/judges/knowledge.py` (answer_accuracy, citation_grounding, code_example_quality, source_relevance, completeness)
