from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import urlopen

from ..base import BaseTool
from ..exceptions import ToolExecutionError, ToolValidationError


class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Searches the web and returns a concise summary with related links."
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query to look up on the web",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of links to include (1-5)",
                "minimum": 1,
                "maximum": 5,
                "default": 3,
            },
        },
        "required": ["query"],
    }

    def run(self, arguments: dict[str, object]) -> str:
        query = str(arguments.get("query", "")).strip()
        if not query:
            raise ToolValidationError(tool_id=self.name, validation_errors=["Query is required"])

        max_results_raw = arguments.get("max_results", 3)
        try:
            max_results = int(max_results_raw)
        except (TypeError, ValueError):
            max_results = 3
        max_results = max(1, min(max_results, 5))

        params = urlencode(
            {"q": query, "format": "json", "no_html": 1, "no_redirect": 1}
        )
        url = f"https://api.duckduckgo.com/?{params}"

        try:
            with urlopen(url, timeout=8) as response:  # nosec B310
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as e:
            raise ToolExecutionError(
                tool_id=self.name,
                reason=f"Search API connection failed: {str(e)}",
                user_message="I couldn't reach the search service right now. Please try again later.",
            )

        abstract = str(payload.get("AbstractText") or "").strip()
        heading = str(payload.get("Heading") or "").strip()

        links: list[str] = []
        for topic in payload.get("RelatedTopics", []):
            if isinstance(topic, dict) and "FirstURL" in topic and "Text" in topic:
                links.append(f"- {topic['Text']}: {topic['FirstURL']}")
            elif isinstance(topic, dict) and "Topics" in topic:
                for nested in topic.get("Topics", []):
                    if (
                        isinstance(nested, dict)
                        and "FirstURL" in nested
                        and "Text" in nested
                    ):
                        links.append(f"- {nested['Text']}: {nested['FirstURL']}")
            if len(links) >= max_results:
                break

        parts: list[str] = []
        if heading:
            parts.append(f"Top result: {heading}")
        if abstract:
            parts.append(f"Summary: {abstract}")
        if links:
            parts.append("Related links:\n" + "\n".join(links[:max_results]))

        if not parts:
            return f"No clear results found for '{query}'."

        return "\n\n".join(parts)
