from app.modules.tools.base import BaseTool


class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Searches the web for information. Queries search engines to find relevant web pages and content."
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query to look up on the web"
            }
        },
        "required": ["query"]
    }

    def run(self, arguments: dict[str, object]) -> str:
        query = str(arguments.get("query", "")).strip()
        if not query:
            return "No query provided."
        return f"Web search is not enabled yet. Query received: {query}"

