from typing import Any, Protocol

from app.infrastructure.messaging.rabbitmq import RabbitMQPublisher


class IDocumentEventRepository(Protocol):
    def publish_json(self, payload: dict[str, Any]) -> None: ...


class RabbitMQDocumentEventRepository:
    def __init__(self, publisher: RabbitMQPublisher) -> None:
        self._publisher = publisher

    def publish_json(self, payload: dict[str, Any]) -> None:
        self._publisher.publish_json(payload)
