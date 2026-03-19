from app.modules.rag.embedders.base import BaseEmbedder


class OpenAIEmbedder(BaseEmbedder):
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 10 for _ in texts]

