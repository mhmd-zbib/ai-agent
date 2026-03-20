from typing import Literal, Optional

from app.modules.rag.embedders.base import BaseEmbedder
from app.modules.rag.embedders.openai_embedder import DummyEmbedder, OpenAIEmbedder


class EmbedderFactory:
    """Factory for creating embedder instances (Factory Pattern)."""

    @staticmethod
    def create(
        embedder_type: Literal["openai", "dummy"] = "dummy",
        **kwargs,
    ) -> BaseEmbedder:
        """
        Create an embedder instance based on type.

        Args:
            embedder_type: Type of embedder to create ("openai" or "dummy")
            **kwargs: Additional arguments passed to embedder constructor

        Returns:
            Configured embedder instance

        Raises:
            ValueError: If embedder_type is not recognized

        Examples:
            >>> factory = EmbedderFactory()
            >>> embedder = factory.create("dummy", dimension=768)
            >>> embedder = factory.create("openai", model_name="text-embedding-3-small")
        """
        if embedder_type == "openai":
            return OpenAIEmbedder(**kwargs)
        elif embedder_type == "dummy":
            return DummyEmbedder(**kwargs)
        else:
            raise ValueError(
                f"Unknown embedder type: {embedder_type}. "
                f"Supported types: 'openai', 'dummy'"
            )
