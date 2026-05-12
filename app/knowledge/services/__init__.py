"""Knowledge service decomposition (F052).

The original `KnowledgeService` god class is now a façade in
`app/knowledge/service.py` that composes these four single-responsibility
services. New code should import the specific service it needs.
"""

from app.knowledge.services.graph import GraphSearchService
from app.knowledge.services.ingestion import IngestionService
from app.knowledge.services.search import SearchService
from app.knowledge.services.tags import TagService

__all__ = [
    "GraphSearchService",
    "IngestionService",
    "SearchService",
    "TagService",
]
