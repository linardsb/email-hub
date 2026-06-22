"""F070 — assert all agent request schemas inherit BaseAgentRequest."""

from __future__ import annotations

from typing import Any

import pytest

from app.ai.agents.accessibility.schemas import AccessibilityRequest
from app.ai.agents.code_reviewer.schemas import CodeReviewRequest
from app.ai.agents.content.schemas import ContentRequest
from app.ai.agents.dark_mode.schemas import DarkModeRequest
from app.ai.agents.innovation.schemas import InnovationRequest
from app.ai.agents.knowledge.schemas import KnowledgeRequest
from app.ai.agents.outlook_fixer.schemas import OutlookFixerRequest
from app.ai.agents.personalisation.schemas import PersonalisationRequest
from app.ai.agents.scaffolder.schemas import ScaffolderRequest
from app.ai.agents.types import BaseAgentRequest
from app.ai.agents.visual_qa.schemas import VisualQARequest

_MIN_HTML = "<html><body>" + ("x" * 50) + "</body></html>"


@pytest.mark.parametrize(
    ("schema_cls", "kwargs"),
    [
        (ScaffolderRequest, {"brief": "Generate a welcome email for new users."}),
        (DarkModeRequest, {"html": _MIN_HTML}),
        (ContentRequest, {"operation": "subject_line", "text": "A campaign brief"}),
        (AccessibilityRequest, {"html": _MIN_HTML}),
        (CodeReviewRequest, {"html": _MIN_HTML}),
        (
            PersonalisationRequest,
            {"html": _MIN_HTML, "platform": "braze", "requirements": "hello"},
        ),
        (OutlookFixerRequest, {"html": _MIN_HTML}),
        (KnowledgeRequest, {"question": "What is preheader?"}),
        (InnovationRequest, {"technique": "CSS checkbox tabs"}),
        (
            VisualQARequest,
            {"screenshots": {"gmail_web": "iVBORw0K"}, "html": _MIN_HTML},
        ),
    ],
)
def test_request_schemas_inherit_base_agent_request(
    schema_cls: type[BaseAgentRequest], kwargs: dict[str, Any]
) -> None:
    assert issubclass(schema_cls, BaseAgentRequest)
    instance = schema_cls(**kwargs)
    assert isinstance(instance, BaseAgentRequest)


def test_orchestrator_fields_default_to_none() -> None:
    req = ScaffolderRequest(brief="Generate a welcome email for new users.")
    assert req.user_id is None
    assert req.blueprint_run_id is None
    assert req.prompt_version is None
    assert req.client_id is None


def test_orchestrator_fields_accept_string_injection() -> None:
    req = ScaffolderRequest(
        brief="Generate a welcome email for new users.",
        user_id="user-42",
        blueprint_run_id="run-1",
        prompt_version="v3",
        client_id="gmail_web",
    )
    assert req.user_id == "user-42"
    assert req.blueprint_run_id == "run-1"
    assert req.prompt_version == "v3"
    assert req.client_id == "gmail_web"
