import json
from collections.abc import Callable
from typing import Any


class RabbitMQPublisher:
    """Publishes JSON messages to a named exchange."""

    def __init__(
        self,
        *,
        amqp_url: str,
        exchange: str,
        routing_key: str,
        exchange_type: str = "topic",
    ) -> None:
        self._amqp_url = amqp_url
        self._exchange = exchange
        self._routing_key = routing_key
        self._exchange_type = exchange_type

    def publish_json(self, payload: dict[str, Any]) -> None:
        import pika

        connection = pika.BlockingConnection(pika.URLParameters(self._amqp_url))
        try:
            channel = connection.channel()
            channel.exchange_declare(
                exchange=self._exchange,
                exchange_type=self._exchange_type,
                durable=True,
            )
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


def publish_to_queue(amqp_url: str, queue_name: str, payload: dict[str, Any]) -> None:
    """
    Publish a single JSON payload to a named queue via the default exchange.

    Used for single-message inter-stage publishing (Stage 1→2, 3→4).
    For publishing multiple messages in one go use :func:`publish_batch_to_queue`.
    """
    publish_batch_to_queue(amqp_url, queue_name, [payload])


def publish_batch_to_queue(
    amqp_url: str,
    queue_name: str,
    payloads: list[dict[str, Any]],
) -> None:
    """
    Publish multiple JSON payloads to a named queue using a single connection.

    Opens one TCP connection, publishes all messages on the same channel, then
    closes. Used by the chunk consumer to avoid opening N connections for N
    chunks — which would serialize connection overhead with document size.
    """
    if not payloads:
        return

    import pika

    props = pika.BasicProperties(delivery_mode=2, content_type="application/json")
    connection = pika.BlockingConnection(pika.URLParameters(amqp_url))
    try:
        channel = connection.channel()
        for payload in payloads:
            channel.basic_publish(
                exchange="",
                routing_key=queue_name,
                body=json.dumps(payload).encode("utf-8"),
                properties=props,
            )
    finally:
        connection.close()


def setup_pipeline_topology(
    amqp_url: str,
    fanout_exchange: str,
    queues: list[tuple[str, str]],
) -> None:
    """
    Declare the full pipeline topology (idempotent).

    Args:
        amqp_url: RabbitMQ connection URL.
        fanout_exchange: Fanout exchange name (Stage 0 publishes here).
        queues: List of ``(queue_name, dlq_name)`` pairs for all four stages.
                The first queue is bound to *fanout_exchange*; the rest use the
                default exchange (direct queue publish).
    """
    import pika

    connection = pika.BlockingConnection(pika.URLParameters(amqp_url))
    try:
        channel = connection.channel()

        # Fanout exchange — Stage 0 publishes document.uploaded events here
        channel.exchange_declare(
            exchange=fanout_exchange,
            exchange_type="fanout",
            durable=True,
        )

        for i, (queue_name, dlq_name) in enumerate(queues):
            # DLQ — plain durable queue, no special arguments
            channel.queue_declare(queue=dlq_name, durable=True)

            # Main queue — dead-letters go to the DLQ via default exchange
            channel.queue_declare(
                queue=queue_name,
                durable=True,
                arguments={
                    "x-dead-letter-exchange": "",
                    "x-dead-letter-routing-key": dlq_name,
                },
            )

            # Bind first queue to the fanout exchange (Stage 0 → Stage 1)
            if i == 0:
                channel.queue_bind(exchange=fanout_exchange, queue=queue_name)
    finally:
        connection.close()


class RabbitMQConsumer:
    """
    Blocking consumer for a single pipeline stage queue.

    Handles DLQ setup, prefetch, ack/nack, and graceful shutdown.
    """

    def __init__(
        self,
        *,
        amqp_url: str,
        queue_name: str,
        dlq_name: str,
        prefetch_count: int = 1,
    ) -> None:
        self._amqp_url = amqp_url
        self._queue_name = queue_name
        self._dlq_name = dlq_name
        self._prefetch_count = prefetch_count

    def consume_forever(
        self,
        handler: Callable[[dict[str, Any]], None],
    ) -> None:
        """
        Start blocking consumption. *handler* is called with the decoded JSON
        payload. Acks on success, nacks to DLQ on any exception.
        """
        import pika

        connection = pika.BlockingConnection(pika.URLParameters(self._amqp_url))
        channel = connection.channel()

        # Ensure DLQ exists
        channel.queue_declare(queue=self._dlq_name, durable=True)

        # Ensure main queue exists with DLQ routing
        channel.queue_declare(
            queue=self._queue_name,
            durable=True,
            arguments={
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": self._dlq_name,
            },
        )

        channel.basic_qos(prefetch_count=self._prefetch_count)

        def _callback(
            channel: Any,
            method: Any,
            _properties: Any,
            body: bytes,
        ) -> None:
            try:
                payload = json.loads(body.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("Expected JSON object payload")
                handler(payload)
                channel.basic_ack(delivery_tag=method.delivery_tag)
            except Exception:
                channel.basic_nack(
                    delivery_tag=method.delivery_tag,
                    requeue=False,
                )

        channel.basic_consume(queue=self._queue_name, on_message_callback=_callback)
        channel.start_consuming()
