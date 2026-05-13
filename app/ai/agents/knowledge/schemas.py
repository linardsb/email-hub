"""Knowledge agent request/response schemas."""

from pydantic import BaseModel, Field

from app.ai.agents.types import BaseAgentRequest


class KnowledgeSource(BaseModel):
    """A cited source from the knowledge base."""

    document_id: int
    filename: str
    domain: str
    chunk_content: str
    relevance_score: float


class KnowledgeRequest(BaseAgentRequest):
    """Request to the Knowledge agent."""

    question: str = Field(..., min_length=5, max_length=2000)
    domain: str | None = None  # Optional domain filter (css_support, best_practices, client_quirks)
    stream: bool = False


class KnowledgeResponse(BaseModel):
    """Response from the Knowledge agent."""

    answer: str
    sources: list[KnowledgeSource]
    confidence: float  # 0.0-1.0
    skills_loaded: list[str]
    model: str
