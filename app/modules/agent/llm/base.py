from __future__ import annotations

from abc import ABC, abstractmethod

from app.modules.agent.schemas import AgentInput
from app.shared.schemas import AIResponse


class BaseLLM(ABC):
    @abstractmethod
    def generate(self, payload: AgentInput) -> AIResponse:
        raise NotImplementedError

