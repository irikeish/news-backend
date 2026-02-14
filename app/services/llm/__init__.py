"""LLM adapter factory."""

from app.config import settings
from app.services.llm.adapter import LLMAdapter
from app.services.llm.openai import OpenAIAdapter


def get_llm_adapter() -> LLMAdapter:
    """Return configured LLM adapter."""
    return OpenAIAdapter(api_key=settings.openai_api_key, model=settings.openai_model)
