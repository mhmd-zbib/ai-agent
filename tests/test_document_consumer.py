import json

from app.workers.document_uploaded_consumer import _build_callback


class _FakeChannel:
    def __init__(self) -> None:
        self.acked: list[int] = []
        self.nacked: list[tuple[int, bool]] = []

    def basic_ack(self, delivery_tag: int) -> None:
        self.acked.append(delivery_tag)

    def basic_nack(self, delivery_tag: int, requeue: bool) -> None:
        self.nacked.append((delivery_tag, requeue))


class _FakeMethod:
    delivery_tag = 42


def test_consumer_callback_acks_on_valid_payload() -> None:
    captured: list[dict[str, object]] = []

    def handler(payload: dict[str, object]) -> None:
        captured.append(payload)

    callback = _build_callback(handler)
    channel = _FakeChannel()
    body = json.dumps({"event_id": "e1", "upload_id": "u1"}).encode("utf-8")

    callback(channel, _FakeMethod(), None, body)

    assert len(captured) == 1
    assert channel.acked == [42]
    assert channel.nacked == []


def test_consumer_callback_nacks_on_invalid_payload() -> None:
    def handler(payload: dict[str, object]) -> None:  # noqa: ARG001
        return

    callback = _build_callback(handler)
    channel = _FakeChannel()

    callback(channel, _FakeMethod(), None, b"not-json")

    assert channel.acked == []
    assert channel.nacked == [(42, False)]

