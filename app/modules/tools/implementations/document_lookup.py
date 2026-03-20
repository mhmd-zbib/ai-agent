from app.modules.tools.base import BaseTool


class DocumentLookupTool(BaseTool):
    name = "document_lookup"
    description = "Looks up information from documents using Retrieval-Augmented Generation (RAG). Searches through indexed documents to find relevant information."
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The query to search for in the document knowledge base"
            }
        },
        "required": ["query"]
    }

    def run(self, arguments: dict[str, object]) -> str:
        query = str(arguments.get("query", "")).strip()
        if not query:
            return "No query provided."
        return f"RAG document lookup is not enabled yet. Query received: {query}"

