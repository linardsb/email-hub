"""Blueprint execution + eval/production-sampling settings."""

from pydantic import BaseModel


class BlueprintConfig(BaseModel):
    """Blueprint execution settings."""

    daily_token_cap: int = 500_000  # Max tokens per user per day across all blueprint runs
    judge_on_retry: bool = False  # When True, run LLM judge on recovery retries (iteration > 0)
    checkpoints_enabled: bool = False  # Opt-in checkpoint persistence (backward compatible)
    checkpoint_retention_days: int = 7  # Auto-cleanup age limit for old checkpoints
    recovery_ledger_enabled: bool = False  # Adaptive recovery routing from outcome history
    visual_qa_precheck: bool = False  # Pre-QA visual defect detection via VLM screenshots
    visual_comparison: bool = False  # Post-build screenshot comparison vs original design
    visual_comparison_threshold: float = 5.0  # Pixel diff % threshold for drift warning
    visual_precheck_top_clients: int = 3  # Number of clients to render for precheck


class EvalConfig(BaseModel):
    """Eval and production sampling settings."""

    production_sample_rate: float = 0.0  # 0.0 = disabled; 1.0 = 100%
    production_queue_key: str = "eval:production_judge_queue"
    worker_interval_seconds: int = 300  # 5 min polling
    verdicts_path: str = "traces/production_verdicts.jsonl"
