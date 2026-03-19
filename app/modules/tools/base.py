from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ToolInput:
    values: dict[str, Any]


@dataclass(slots=True)
class ToolOutput:
    value: str


class BaseTool(ABC):
    name: str

    @abstractmethod
    def run(self, arguments: dict[str, Any]) -> str:
        raise NotImplementedError

