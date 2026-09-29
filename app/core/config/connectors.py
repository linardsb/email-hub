"""ESP sync, credential pool, brief and Tolgee TMS settings."""

from pydantic import BaseModel, Field


class ESPSyncConfig(BaseModel):
    """ESP bidirectional sync settings — base URLs for mock or production ESPs."""

    braze_base_url: str = "http://mock-esp:3002/braze"
    sfmc_base_url: str = "http://mock-esp:3002/sfmc"
    adobe_base_url: str = "http://mock-esp:3002/adobe"
    taxi_base_url: str = "http://mock-esp:3002/taxi"
    klaviyo_base_url: str = "http://mock-esp:3002/klaviyo"
    hubspot_base_url: str = "http://mock-esp:3002/hubspot"
    mailchimp_base_url: str = "http://mock-esp:3002/mailchimp"
    sendgrid_base_url: str = "http://mock-esp:3002/sendgrid"
    activecampaign_base_url: str = "http://mock-esp:3002/activecampaign"
    iterable_base_url: str = "http://mock-esp:3002/iterable"
    brevo_base_url: str = "http://mock-esp:3002/brevo"


class CredentialsConfig(BaseModel):
    """Credential pool rotation and cooldown settings."""

    enabled: bool = False  # CREDENTIALS__ENABLED
    cooldown_initial_seconds: int = 30  # CREDENTIALS__COOLDOWN_INITIAL_SECONDS
    cooldown_max_seconds: int = 300  # CREDENTIALS__COOLDOWN_MAX_SECONDS
    failure_threshold: int = 3  # CREDENTIALS__FAILURE_THRESHOLD
    unhealthy_ttl_seconds: int = 3600  # CREDENTIALS__UNHEALTHY_TTL_SECONDS
    pools: dict[str, list[str]] = Field(
        default_factory=dict,
        description="service name -> list of API keys",
    )  # CREDENTIALS__POOLS (JSON via env)


class BriefsConfig(BaseModel):
    """Brief connection settings."""

    enabled: bool = True
    sync_timeout: float = 30.0  # HTTP timeout for platform API calls
    max_items_per_sync: int = 500  # Safety cap on items fetched per sync
    provider_base_urls: dict[
        str, str
    ] = {}  # Override API URLs, e.g. {"asana": "http://localhost:3002/briefs/asana"}


class TolgeeConfig(BaseModel):
    """Tolgee TMS integration settings."""

    enabled: bool = False  # TOLGEE__ENABLED
    base_url: str = "http://localhost:25432"  # TOLGEE__BASE_URL
    # Extra base URLs a connection's `base_url` override may target; the default
    # `base_url` is always allowed. Anything else is rejected (SSRF guard).
    allowed_base_urls: list[str] = []  # TOLGEE__ALLOWED_BASE_URLS (JSON via env)
    default_locale: str = "en"  # TOLGEE__DEFAULT_LOCALE
    max_locales_per_build: int = 20  # TOLGEE__MAX_LOCALES_PER_BUILD
    request_timeout: float = 30.0  # TOLGEE__REQUEST_TIMEOUT
