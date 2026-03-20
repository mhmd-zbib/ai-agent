import json
from typing import Any


class RabbitMQPublisher:
    def __init__(
        self,
        *,
        amqp_url: str,
        exchange: str,
        routing_key: str,
    ) -> None:
        self._amqp_url = amqp_url
        self._exchange = exchange
        self._routing_key = routing_key

    def publish_json(self, payload: dict[str, Any]) -> None:
        import pika

        connection = pika.BlockingConnection(pika.URLParameters(self._amqp_url))
        try:
            channel = connection.channel()
            channel.exchange_declare(exchange=self._exchange, exchange_type="topic", durable=True)
            channel.basic_publish(
                exchange=self._exchange,
                routing_key=self._routing_key,
                body=json.dumps(payload).encode("utf-8"),
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    content_type="application/json",
                ),
            )
        finally:
            connection.close()

    def close(self) -> None:
        return

