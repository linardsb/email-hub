# AI Layer (`app/ai/`)

Protocol-based AI infrastructure with provider registry for LLM calls (Claude/OpenAI), model routing (Opus/Sonnet/Haiku), and WebSocket streaming.

## Architecture
- **Provider Registry** — Runtime-swappable AI providers via Python Protocols
- **Agents** (`agents/`) — 9 specialized agents (3 implemented, 6 planned). Each agent: `prompt.py` + `schemas.py` + `service.py`
- **Blueprints** (`blueprints/`) — State machine engine orchestrating agents as pipeline nodes with QA gating and bounded self-correction (max 2 rounds, max 20 steps)
- **Evals** (`agents/evals/`) — Agent evaluation framework: dimension-based synthetic data, JSONL trace runner, binary LLM judges, TPR/TNR calibration. Applies to all 9 agents. See `agents/CLAUDE.md` for status and `TODO.md` Phase 5 for roadmap.
