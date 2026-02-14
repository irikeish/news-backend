"""Abstract LLM adapter interface."""

from abc import ABC, abstractmethod

from app.models.article import Article
from app.models.intent import ParsedIntent


class LLMAdapter(ABC):
    """Abstract interface for LLM operations."""

    @abstractmethod
    async def parse_query(self, query: str) -> ParsedIntent:
        """Parse user query into structured intent."""
        ...

    @abstractmethod
    async def summarize_articles(self, articles: list[Article]) -> list[str]:
        """Generate 1-2 sentence summary for each article. Returns list in same order."""
        ...
