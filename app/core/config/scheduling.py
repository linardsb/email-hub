"""Cron scheduler and distributed debounce settings."""

from pydantic import BaseModel, Field


class SchedulingConfig(BaseModel):
    """Cron scheduling engine settings."""

    enabled: bool = False  # SCHEDULING__ENABLED
    check_interval_seconds: int = 60  # SCHEDULING__CHECK_INTERVAL_SECONDS
    job_timeout_seconds: int = 3600  # SCHEDULING__JOB_TIMEOUT_SECONDS
    max_run_history: int = 100  # SCHEDULING__MAX_RUN_HISTORY
    run_history_ttl_seconds: int = 86400  # SCHEDULING__RUN_HISTORY_TTL_SECONDS
    max_concurrent_jobs: int = Field(
        default=10,
        ge=1,
        description=(
            "Max in-flight scheduled jobs per worker. Excess due jobs are skipped this tick."
        ),
    )
    qa_sweep_regression_threshold: float = Field(
        default=0.05,
        description="Score drop threshold (fraction) to flag as regression",
    )
    qa_sweep_checks: list[str] = Field(
        default=["html_validation", "css_support", "css_audit"],
        description="QA checks to run during sweeps",
    )


class DebounceConfig(BaseModel):
    """Distributed debounce settings."""

    enabled: bool = True  # DEBOUNCE__ENABLED
    default_window_ms: int = Field(default=2000, ge=100, le=30000)
    figma_webhook_window_ms: int = 3000  # DEBOUNCE__FIGMA_WEBHOOK_WINDOW_MS
    qa_trigger_window_ms: int = 2000  # DEBOUNCE__QA_TRIGGER_WINDOW_MS
    rendering_trigger_window_ms: int = 2000  # DEBOUNCE__RENDERING_TRIGGER_WINDOW_MS
