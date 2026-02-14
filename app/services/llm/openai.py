"""
OpenAI LLM adapter implementation using function/tool calling.
"""

import json
import logging
from typing import List

from openai import AsyncOpenAI

from app.exceptions import LLMUnavailableError
from app.models.article import Article
from app.models.intent import ParsedIntent
from app.services.llm.adapter import LLMAdapter
from app.services.category import get_categories

CLASSIFY_NEWS_QUERY_TOOL = {
    "type": "function",
    "function": {
        "name": "classify_news_query",
        "description": "Classify news query into structured intent and entities",
        "parameters": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "category",
                            "source",
                            "search",
                            "score",
                            "nearby",
                            "trending",
                        ],
                    },
                },
                "entities": {
                    "type": "object",
                    "properties": {
                        "category": {"type": ["string", "null"]},
                        "source": {"type": ["string", "null"]},
                        "keywords": {"type": ["string", "null"]},
                        "threshold": {"type": ["number", "null"]},
                        "location_name": {"type": ["string", "null"]},
                        "radius_km": {"type": ["number", "null"]},
                    },
                },
            },
            "required": ["intent", "entities"],
        },
    },
}

SUMMARIZE_ARTICLES_TOOL = {
    "type": "function",
    "function": {
        "name": "summarize_articles",
        "description": "Generate concise summaries for a batch of articles",
        "parameters": {
            "type": "object",
            "properties": {
                "summaries": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "description": "2 sentence summary of the article",
                    },
                }
            },
            "required": ["summaries"],
        },
    },
}


SYSTEM_PROMPTS = {
    "classify_news_query": lambda category_str: (
        f"""
You classify news queries into structured intent and entities.
You MUST always call the provided function.

VALID CATEGORIES:
{category_str}

GENERAL RULES:
- Extract the main topic into entities.keywords.
- entities.keywords may be null if the query only specifies:
  category, source, location, or generic news words.
- Remove category and location words from keywords.
- Multiple intents may be present.
- If a structured intent (category or source) appears together with other topic words,
include both the structured intent and "search".

CATEGORY:
- If a category is mentioned, include "category" in intent.
- entities.category MUST match one VALID CATEGORY.
- Map typos/synonyms to the closest valid category.

SOURCE:
- If a publisher is mentioned (e.g., Reuters, NYT), include "source".
- Normalize names (e.g., NYT → New York Times).

LOCATION:
- If phrases like "near <location>", "in <location>", "around <location>" appear, include "nearby".
- Extract entities.location_name from the location phrase.
- Only set entities.radius_km if distance is explicitly provided.
- Otherwise radius_km must be null.
- Do not guess a default radius.

KEYWORDS:
- Start from the original query.
- Remove category words, location words, and the following such stop words:
  wherever they appear:
  - news, latest, updates, headlines,
  - a, an, the,
  - in, on, at, from, near, around, within,
  - and, or
- After removal, trim extra spaces.
- If at least one word remains, use the remaining words as entities.keywords.
- Only set entities.keywords to null if no words remain.
    """
    ),
    "summarize_articles": """
        You summarize news articles in exactly 2 concise sentences.
        You MUST call the provided function.
    """,
}


class OpenAIAdapter(LLMAdapter):
    """OpenAI implementation of LLMAdapter using tool calling."""

    def __init__(self, api_key: str = "", model: str = "gpt-4o-mini"):
        self._client = AsyncOpenAI(api_key=api_key) if api_key else None
        self._model = model

    async def parse_query(self, query: str) -> ParsedIntent:
        """Parse user query into structured ParsedIntent using OpenAI function calling."""

        if not self._client or not self._client.api_key:
            raise LLMUnavailableError("OpenAI API key not configured")

        try:
            categories = await get_categories()
            category_str = ", ".join(categories)

            response = await self._client.chat.completions.create(
                model=self._model,
                temperature=0,
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPTS["classify_news_query"](category_str),
                    },
                    {"role": "user", "content": query},
                ],
                tools=[CLASSIFY_NEWS_QUERY_TOOL],
                tool_choice={
                    "type": "function",
                    "function": {"name": "classify_news_query"},
                },
            )

            message = response.choices[0].message

            if not message.tool_calls:
                raise ValueError("No tool call returned from OpenAI")

            arguments = json.loads(message.tool_calls[0].function.arguments)
            entities = arguments.get("entities") or {}

            parsed = ParsedIntent(
                intent=arguments.get("intent") or ["search"],
                category=entities.get("category"),
                source=entities.get("source"),
                keywords=entities.get("keywords"),
                threshold=entities.get("threshold"),
                location_name=entities.get("location_name"),
                radius_km=entities.get("radius_km"),
            )

            if not parsed.intent:
                parsed.intent = ["search"]
            if not parsed.keywords and "search" in parsed.intent:
                parsed.keywords = query

            return parsed

        except Exception:
            logging.exception("LLM parse_query failed. Falling back to search.")
            return ParsedIntent(
                intent=["search"],
                keywords=query,
            )

    async def summarize_articles(self, articles: List[Article]) -> List[str]:
        """
        Generate summaries.
        Returns list of summaries aligned with input order.
        """

        if not self._client or not self._client.api_key:
            raise LLMUnavailableError("OpenAI API key not configured")

        if not articles:
            return []

        results = [a.llm_summary or "" for a in articles]
        to_summarize = [(i, a) for i, a in enumerate(articles) if not a.llm_summary]

        if not to_summarize:
            return results

        try:
            payload = [
                {
                    "title": article.title,
                    "description": article.description,
                }
                for _, article in to_summarize
            ]

            response = await self._client.chat.completions.create(
                model=self._model,
                temperature=0,
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPTS["summarize_articles"],
                    },
                    {
                        "role": "user",
                        "content": json.dumps(payload),
                    },
                ],
                tools=[SUMMARIZE_ARTICLES_TOOL],
                tool_choice={
                    "type": "function",
                    "function": {"name": "summarize_articles"},
                },
            )

            message = response.choices[0].message

            if not message.tool_calls:
                raise ValueError("No tool call returned from OpenAI")

            arguments = json.loads(message.tool_calls[0].function.arguments)
            summaries = arguments.get("summaries", [])

            for (original_index, _), summary in zip(to_summarize, summaries):
                results[original_index] = summary.strip()

        except Exception:
            logging.exception("Batch summarization failed.")
            raise
        return results
