"""AI provider, embedding, and reranker settings."""

from typing import Any

from pydantic import BaseModel


class AIConfig(BaseModel):
    """AI provider settings."""

    provider: str = "openai"  # openai, anthropic, ollama, custom
    model: str = "gpt-4o-mini"
    api_key: str | None = None
    base_url: str | None = None  # Custom endpoint (Ollama, vLLM, LiteLLM)
    daily_quota: int = 50  # Per-user daily request limit (Redis-backed)
    stream_timeout_seconds: int = 120  # Max duration for a streaming response

    # Model routing — maps task tiers to model identifiers
    model_complex: str = ""  # Empty = use default model
    model_standard: str = ""  # Empty = use default model
    model_lightweight: str = ""  # Empty = use default model

    # Visual QA agent (Phase 17.3)
    visual_qa_enabled: bool = False  # AI__VISUAL_QA_ENABLED
    visual_qa_model: str = ""  # AI__VISUAL_QA_MODEL — empty = use default model routing
    visual_qa_clients: list[str] = [
        "gmail_web",
        "outlook_2019",
        "apple_mail",
    ]  # AI__VISUAL_QA_CLIENTS

    # Visual QA auto-fix (Phase 17.4)
    visual_qa_autofix_enabled: bool = False  # AI__VISUAL_QA_AUTOFIX_ENABLED
    visual_qa_autofix_max_rounds: int = 1  # AI__VISUAL_QA_AUTOFIX_MAX_ROUNDS

    # Token budget management (Phase 22.3)
    token_budget_enabled: bool = (
        True  # AI__TOKEN_BUDGET_ENABLED — default-on (GA); kept for rollback
    )
    token_budget_reserve: int = 4096  # AI__TOKEN_BUDGET_RESERVE — tokens reserved for response
    token_budget_max: int = 0  # AI__TOKEN_BUDGET_MAX — 0 = auto-detect from model name

    # Prompt template store (Phase 22.2)
    prompt_store_enabled: bool = False  # AI__PROMPT_STORE_ENABLED

    # Model capability registry (Phase 22.1)
    model_specs: list[dict[str, Any]] = []  # AI__MODEL_SPECS — JSON array of model specs

    # Fallback chains — ordered model fallbacks per tier (Phase 22.4)
    # JSON: {"complex": ["anthropic:claude-opus-4-6", "openai:gpt-4o"], ...}
    fallback_chains: dict[str, list[str]] = {}  # AI__FALLBACK_CHAINS

    # Cost governor (Phase 22.5)
    cost_governor_enabled: bool = (
        True  # AI__COST_GOVERNOR_ENABLED — default-on (GA); kept for rollback
    )
    monthly_budget_gbp: float = 600.0  # AI__MONTHLY_BUDGET_GBP — 0 = unlimited
    budget_warning_threshold: float = 0.8  # AI__BUDGET_WARNING_THRESHOLD — warn at 80%

    # Multimodal protocol (Phase 23.1)
    max_image_size_mb: int = 20  # AI__MAX_IMAGE_SIZE_MB
    max_audio_duration_s: int = 300  # AI__MAX_AUDIO_DURATION_S
    supported_image_types: list[str] = [
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
    ]  # AI__SUPPORTED_IMAGE_TYPES

    # Multimodal agent context (Phase 23.3)
    multimodal_context_enabled: bool = False  # AI__MULTIMODAL_CONTEXT_ENABLED

    # Scaffolder tree mode (Phase 48.7)
    scaffolder_tree_mode: bool = False  # AI__SCAFFOLDER_TREE_MODE
    scaffolder_tree_manifest_budget: int = 8000  # AI__SCAFFOLDER_TREE_MANIFEST_BUDGET (tokens)


class EmbeddingConfig(BaseModel):
    """Embedding provider settings."""

    provider: str = "openai"  # openai, jina, local
    model: str = "text-embedding-3-small"
    dimension: int = 1536
    api_key: str | None = None
    base_url: str | None = None


class RerankerConfig(BaseModel):
    """Reranker settings."""

    provider: str = "none"  # none, cohere, jina, local
    model: str = ""
    top_k: int = 10
