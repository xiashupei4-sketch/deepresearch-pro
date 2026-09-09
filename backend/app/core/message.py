"""Agent communication messages (local protocol; A2A adapter reserved)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MessageType(str, Enum):
    TASK = "TASK"
    RESULT = "RESULT"
    FEEDBACK = "FEEDBACK"
    ERROR = "ERROR"
    EVENT = "EVENT"


class AgentMessage(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    sender: str
    receiver: str
    type: MessageType = MessageType.EVENT
    payload: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=utcnow)


class MessageBus:
    """Minimal in-process pub/sub used by the runtime and the event pipeline."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list] = {}

    def subscribe(self, topic: str, callback):  # callback: async fn(AgentMessage) -> None
        self._subscribers.setdefault(topic, []).append(callback)

    def unsubscribe_all(self, topic: str) -> None:
        self._subscribers.pop(topic, None)

    async def publish(self, topic: str, message: AgentMessage) -> None:
        for cb in self._subscribers.get(topic, []):
            try:
                await cb(message)
            except Exception:  # noqa: BLE001 — a broken subscriber must not break the bus
                continue
