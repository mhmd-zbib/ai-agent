from __future__ import annotations

from api.modules.tools.base import BaseTool
from api.modules.tools.exceptions import ToolConfigurationError, ToolValidationError


class DocumentLookupTool(BaseTool):
    name = "document_lookup"
    description = (
        "Searches the user's uploaded documents using semantic similarity. "
        "Use this whenever the user asks about content from their documents."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The question or topic to search for in the documents",
            }
        },
        "required": ["query"],
    }

    def __init__(self, vector_client=None, embedding_client=None) -> None:
        self._vector_client = vector_client
        self._embedding_client = embedding_client

    def run(self, arguments: dict) -> str:
        query = str(arguments.get("query", "")).strip()
        if not query:
            raise ToolValidationError(tool_id=self.name, validation_errors=["Query is required"])

        if self._vector_client is None or self._embedding_client is None:
            raise ToolConfigurationError(
                tool_id=self.name,
                issue="Vector or embedding client not configured",
            )

        user_id = str(arguments.get("user_id", ""))

        query_vector = self._embedding_client.embed(query)
        results = self._vector_client.query(
            vector=query_vector,
            top_k=5,
            namespace=user_id,
        )

        if not results:
            return "No relevant documents found for that query."

        chunks = []
        for i, hit in enumerate(results, 1):
            meta = hit.get("metadata", {})
            text = meta.get("chunk_text", "").strip()
            file_name = meta.get("file_name", "unknown")
            score = hit.get("score", 0.0)
            if text:
                chunks.append(
                    f"[{i}] From '{file_name}' (relevance: {score:.3f}):\n{text}"
                )

        return "\n\n---\n\n".join(chunks) if chunks else "No relevant content found."
