"""Request/response Pydantic models for Tolgee integration."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

# BCP-47 locale tag pattern (e.g., "en", "de-AT", "zh-Hans-CN")
BCP47_PATTERN = r"^[a-zA-Z]{2,3}(-[a-zA-Z0-9]{1,8})*$"
BCP47Locale = Annotated[str, StringConstraints(pattern=BCP47_PATTERN)]

# --- Tolgee API response models ---


class TolgeeProject(BaseModel):
    id: int
    name: str
    description: str = ""


class TolgeeLanguage(BaseModel):
    id: int
    tag: str  # BCP-47 tag: "en", "de", "ar"
    name: str  # "English", "German", "Arabic"
    original_name: str = ""
    flag_emoji: str = ""
    base: bool = False


class TranslationKey(BaseModel):
    key: str  # e.g., "template_42.hero.heading"
    source_text: str  # Original English text
    context: str | None = None  # Optional context hint for translators
    namespace: str = "email"  # Tolgee namespace


class PushResult(BaseModel):
    created: int = 0
    updated: int = 0
    skipped: int = 0


class ImportResult(BaseModel):
    imported_count: int = 0
    errors: list[str] = Field(default_factory=list)


# --- Request schemas ---


class TolgeeConnectionRequest(BaseModel):
    """Create a Tolgee connection (reuses ESPConnection model)."""

    name: str = Field(min_length=1, max_length=200)
    project_id: int
    tolgee_project_id: int  # Tolgee-side project ID
    base_url: str | None = None  # Override default base URL
    pat: str = Field(min_length=1)  # Personal Access Token (will be encrypted)


class TranslationSyncRequest(BaseModel):
    """Push translatable keys from a template to Tolgee."""

    connection_id: int
    template_id: int  # Hub template ID (to extract keys from latest version)
    namespace: str = "email"


class TranslationPullRequest(BaseModel):
    """Pull translations from Tolgee for specified locales."""

    connection_id: int
    tolgee_project_id: int
    locales: list[BCP47Locale] = Field(min_length=1, max_length=20)  # BCP-47 tags
    namespace: str | None = None


class LocaleBuildRequest(BaseModel):
    """Build email template in multiple locales."""

    connection_id: int
    template_id: int  # Hub template ID
    tolgee_project_id: int
    locales: list[BCP47Locale] = Field(min_length=1, max_length=20)
    namespace: str | None = None
    is_production: bool = False


# --- Response schemas ---


class TranslationSyncResponse(BaseModel):
    keys_extracted: int
    push_result: PushResult
    template_id: int


class TranslationPullResponse(BaseModel):
    locale: str
    translations_count: int
    translations: dict[str, str]  # key → translated text


class LocaleBuildResult(BaseModel):
    locale: str
    html: str
    build_time_ms: float
    gmail_clipping_warning: bool = False  # True if >102KB
    text_direction: str = "ltr"  # "ltr" or "rtl"


class LocaleBuildResponse(BaseModel):
    template_id: int
    results: list[LocaleBuildResult]
    total_build_time_ms: float


class TolgeeConnectionResponse(BaseModel):
    id: int
    name: str
    status: str
    credentials_hint: str
    tolgee_project_id: int | None = None
    project_id: int
    last_synced_at: datetime | None = None
    created_at: datetime
