"""QA engine sub-configurations (chaos, property testing, deliverability, etc.)."""

from pydantic import BaseModel


class QAChaosConfig(BaseModel):
    """Chaos testing configuration."""

    enabled: bool = False  # QA_CHAOS__ENABLED
    default_profiles: list[str] = [
        "gmail_style_strip",
        "image_blocked",
        "dark_mode_inversion",
        "gmail_clipping",
    ]  # QA_CHAOS__DEFAULT_PROFILES
    resilience_check_enabled: bool = False  # QA_CHAOS__RESILIENCE_CHECK_ENABLED
    resilience_threshold: float = 0.7  # QA_CHAOS__RESILIENCE_THRESHOLD
    auto_document: bool = False  # QA_CHAOS__AUTO_DOCUMENT


class QAPropertyTestingConfig(BaseModel):
    """Property-based testing configuration."""

    enabled: bool = False  # QA_PROPERTY_TESTING__ENABLED
    default_cases: int = 100  # QA_PROPERTY_TESTING__DEFAULT_CASES
    seed: int | None = None  # QA_PROPERTY_TESTING__SEED (fixed seed for CI)


class QAOutlookAnalyzerConfig(BaseModel):
    """Outlook Word-engine dependency analyzer configuration."""

    enabled: bool = True  # QA_OUTLOOK_ANALYZER__ENABLED — default-on (GA); kept for rollback
    default_target: str = "dual_support"  # new_outlook | dual_support | audit_only


class QADeliverabilityConfig(BaseModel):
    """Deliverability prediction scoring. Env prefix: QA_DELIVERABILITY__."""

    enabled: bool = True  # QA_DELIVERABILITY__ENABLED — default-on (GA); kept for rollback
    threshold: int = 70  # 0-100 score, pass if >= threshold


class QAGmailPredictorConfig(BaseModel):
    """Gmail AI summary prediction configuration."""

    enabled: bool = False
    model: str = "gpt-4o-mini"
    api_base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    max_html_chars: int = 8000
    timeout_seconds: float = 30.0


class QABIMIConfig(BaseModel):
    """BIMI readiness check configuration."""

    enabled: bool = False  # QA_BIMI__ENABLED
    svg_fetch_timeout_seconds: float = 10.0  # QA_BIMI__SVG_FETCH_TIMEOUT_SECONDS
    svg_max_size_bytes: int = 32_768  # QA_BIMI__SVG_MAX_SIZE_BYTES (32KB)
    dns_timeout_seconds: float = 5.0  # QA_BIMI__DNS_TIMEOUT_SECONDS


class QASyntheticConfig(BaseModel):
    """Synthetic adversarial email generator configuration."""

    count_per_check: int = 5  # QA_SYNTHETIC__COUNT_PER_CHECK
    output_dir: str = "data/synthetic-adversarial"  # QA_SYNTHETIC__OUTPUT_DIR


class QAMetaEvalConfig(BaseModel):
    """QA check meta-evaluation configuration."""

    enabled: bool = True  # QA_META_EVAL__ENABLED
    fp_threshold: float = 0.10  # QA_META_EVAL__FP_THRESHOLD
    fn_threshold: float = 0.05  # QA_META_EVAL__FN_THRESHOLD
