from __future__ import annotations

from abc import ABC, abstractmethod

from app.modules.agent.schemas import AgentInput, AgentOutput


class BaseLLM(ABC):
    @abstractmethod
    def generate(self, payload: AgentInput) -> AgentOutput:
        raise NotImplementedError

