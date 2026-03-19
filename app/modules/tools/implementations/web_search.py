from app.modules.tools.base import BaseTool


class WebSearchTool(BaseTool):
    name = "web_search"

    def run(self, arguments: dict[str, object]) -> str:
        query = str(arguments.get("query", "")).strip()
        if not query:
            return "No query provided."
        return f"Web search is not enabled yet. Query received: {query}"

