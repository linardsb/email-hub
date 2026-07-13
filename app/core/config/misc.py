"""Miscellaneous settings groups not yet warranting their own module.

When any of these grow, promote to a dedicated file under app/core/config/.
"""

from pydantic import BaseModel, Field


class OntologySyncConfig(BaseModel):
    """Can I Email ontology sync settings."""

    enabled: bool = False
    interval_hours: int = 168  # Weekly default
    github_repo: str = "hteumeuleu/caniemail"
    github_branch: str = "main"
    github_token: str = ""  # Optional — increases rate limit from 60/hr to 5000/hr
    request_timeout_seconds: int = 30
    max_features_per_sync: int = 500  # Safety cap
    dry_run: bool = True  # Dry run by default until manually verified


class VoiceConfig(BaseModel):
    """Voice brief input pipeline settings."""

    enabled: bool = False  # VOICE__ENABLED — master toggle
    transcriber: str = "whisper_api"  # VOICE__TRANSCRIBER — "whisper_api" or "whisper_local"
    whisper_model: str = "whisper-1"  # VOICE__WHISPER_MODEL — API model name
    whisper_local_model: str = "base"  # VOICE__WHISPER_LOCAL_MODEL — local model size
    extraction_model: str = ""  # VOICE__EXTRACTION_MODEL — empty = use default AI model
    max_duration_s: int = 300  # VOICE__MAX_DURATION_S — 5 min max
    max_file_size_mb: int = 25  # VOICE__MAX_FILE_SIZE_MB
    confidence_threshold: float = 0.7  # VOICE__CONFIDENCE_THRESHOLD — below = raw transcript
    rate_limit_transcribe: str = "5/minute"  # VOICE__RATE_LIMIT_TRANSCRIBE
    rate_limit_brief: str = "3/minute"  # VOICE__RATE_LIMIT_BRIEF
    rate_limit_run: str = "2/minute"  # VOICE__RATE_LIMIT_RUN


class MCPConfig(BaseModel):
    """MCP (Model Context Protocol) server settings."""

    enabled: bool = False  # MCP__ENABLED
    max_response_tokens: int = 4000  # MCP__MAX_RESPONSE_TOKENS — truncate responses beyond this
    tool_timeout_s: int = 120  # MCP__TOOL_TIMEOUT_S
    audit_log_enabled: bool = True  # MCP__AUDIT_LOG_ENABLED
    # Tool allowlist — empty means all tools exposed
    # Operators can restrict to e.g. ["qa_*", "knowledge_*"]
    tool_allowlist: list[str] = []  # MCP__TOOL_ALLOWLIST
    cache_enabled: bool = True  # MCP__CACHE_ENABLED — in-memory response cache
    cache_max_size: int = 100  # MCP__CACHE_MAX_SIZE — max cached responses
    cache_ttl: int = 300  # MCP__CACHE_TTL — seconds before cache entries expire
    compress_schemas: bool = True  # MCP__COMPRESS_SCHEMAS — strip verbose schema fields


class EmailEngineConfig(BaseModel):
    """Email engine settings."""

    css_compiler_enabled: bool = False  # EMAIL_ENGINE__CSS_COMPILER_ENABLED
    css_compiler_target_clients: list[str] = [
        "gmail_web",
        "outlook_2019",
        "apple_mail",
        "yahoo_mail",
    ]  # EMAIL_ENGINE__CSS_COMPILER_TARGET_CLIENTS
    schema_injection_enabled: bool = False  # EMAIL_ENGINE__SCHEMA_INJECTION_ENABLED
    schema_injection_types: list[str] = [  # EMAIL_ENGINE__SCHEMA_INJECTION_TYPES
        "promotional",
        "transactional",
        "event",
    ]


class CorrectionTrackerConfig(BaseModel):
    """Correction pattern tracking settings (Phase 35.7)."""

    enabled: bool = False
    min_occurrences: int = 5
    min_confidence: float = 0.9
    max_log_entries: int = 10_000


class WebSocketConfig(BaseModel):
    """WebSocket streaming settings."""

    enabled: bool = True
    heartbeat_interval_seconds: int = 30
    max_connections: int = 100
    max_connections_per_user: int = 5


class CollabWebSocketConfig(BaseModel):
    """Collaboration WebSocket settings."""

    enabled: bool = False
    max_connections_per_room: int = 20
    max_rooms_per_user: int = 10
    heartbeat_interval_seconds: int = 30
    auth_timeout_seconds: int = 10
    max_message_bytes: int = 1_048_576  # 1 MB
    # CRDT settings (Phase 24.2)
    crdt_enabled: bool = False
    crdt_compaction_threshold: int = 100  # compact after N updates
    crdt_compaction_interval_s: int = 300  # or after N seconds
    crdt_max_document_size_mb: int = 5  # reject updates beyond this


class KestraConfig(BaseModel):
    """Kestra workflow orchestration settings."""

    enabled: bool = False  # KESTRA__ENABLED
    api_url: str = "http://localhost:8080"  # KESTRA__API_URL
    api_token: str = ""  # KESTRA__API_TOKEN
    namespace: str = "email-hub"  # KESTRA__NAMESPACE
    default_retry_attempts: int = 3  # KESTRA__DEFAULT_RETRY_ATTEMPTS
    default_retry_backoff_s: int = 30  # KESTRA__DEFAULT_RETRY_BACKOFF_S
    request_timeout_s: float = 30.0  # KESTRA__REQUEST_TIMEOUT_S


class ReportingConfig(BaseModel):
    """Typst PDF report generation settings."""

    enabled: bool = False  # REPORTING__ENABLED
    typst_binary: str = "typst"  # REPORTING__TYPST_BINARY
    cache_ttl_h: int = 24  # REPORTING__CACHE_TTL_H
    max_report_size_mb: int = 50  # REPORTING__MAX_REPORT_SIZE_MB
    compilation_timeout_s: int = 10  # REPORTING__COMPILATION_TIMEOUT_S


class PluginsConfig(BaseModel):
    """Plugin architecture settings."""

    enabled: bool = False  # PLUGINS__ENABLED
    directory: str = "plugins/"  # PLUGINS__DIRECTORY
    hot_reload: bool = False  # PLUGINS__HOT_RELOAD
    default_timeout_s: int = 30  # PLUGINS__DEFAULT_TIMEOUT_S
    health_check_interval_s: int = 60  # PLUGINS__HEALTH_CHECK_INTERVAL_S
    max_consecutive_failures: int = 3  # PLUGINS__MAX_CONSECUTIVE_FAILURES


class SkillExtractionConfig(BaseModel):
    """Configuration for automatic skill extraction from templates."""

    enabled: bool = False  # SKILL_EXTRACTION__ENABLED
    min_confidence: float = 0.7  # Only extract patterns with >= this confidence
    max_amendments_per_upload: int = 20  # Cap to prevent skill file spam
    auto_eval_after_apply: bool = True  # Trigger eval run after amendment applied


class TemplatesUploadConfig(BaseModel):
    """Template upload pipeline settings."""

    upload_enabled: bool = False  # TEMPLATES__UPLOAD_ENABLED
    max_file_size_bytes: int = 2 * 1024 * 1024  # TEMPLATES__MAX_FILE_SIZE_BYTES (2MB)
    max_uploads_per_hour: int = 5  # TEMPLATES__MAX_UPLOADS_PER_HOUR
    auto_knowledge_inject: bool = True  # TEMPLATES__AUTO_KNOWLEDGE_INJECT
    auto_eval_generate: bool = True  # TEMPLATES__AUTO_EVAL_GENERATE
    import_images: bool = True  # TEMPLATES__IMPORT_IMAGES
    max_image_download_size: int = 5 * 1024 * 1024  # 5MB per image
    max_images_per_template: int = 50
    image_download_timeout: float = 5.0  # Per-image timeout
    image_storage_path: str = "data/upload-assets"


class VariantsConfig(BaseModel):
    """Multi-variant campaign assembly settings."""

    max_variants: int = 5
    rate_limit_per_hour: int = 3


class ProgressConfig(BaseModel):
    """Progress tracking settings."""

    max_retention_seconds: int = 300
    cleanup_interval_seconds: int = 60


class ExportConfig(BaseModel):
    """Export pipeline gate settings."""

    qa_gate_mode: str = "warn"  # enforce | warn | skip
    qa_blocking_checks: list[str] = Field(
        default_factory=lambda: [
            "html_validation",
            "link_validation",
            "spam_score",
            "personalisation_syntax",
            "liquid_syntax",
        ]
    )
    qa_warning_checks: list[str] = Field(
        default_factory=lambda: [
            "accessibility",
            "dark_mode",
            "image_optimization",
            "file_size",
        ]
    )
