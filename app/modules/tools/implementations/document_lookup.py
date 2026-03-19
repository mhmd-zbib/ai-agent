from app.modules.tools.base import BaseTool


class DocumentLookupTool(BaseTool):
    name = "document_lookup"

    def run(self, arguments: dict[str, object]) -> str:
        query = str(arguments.get("query", "")).strip()
        if not query:
            return "No query provided."
        return f"RAG document lookup is not enabled yet. Query received: {query}"

