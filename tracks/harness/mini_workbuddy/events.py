from __future__ import annotations

import json
import queue
import threading
from dataclasses import dataclass
from typing import Any, Iterator


@dataclass
class Event:
    name: str
    data: dict[str, Any]

    def to_sse(self) -> bytes:
        payload = json.dumps(self.data, ensure_ascii=False)
        return f"event: {self.name}\ndata: {payload}\n\n".encode("utf-8")


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[queue.Queue[Event]] = []
        self._lock = threading.Lock()

    def publish(self, name: str, data: dict[str, Any]) -> None:
        event = Event(name, data)
        with self._lock:
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            subscriber.put(event)

    def subscribe(self) -> Iterator[Event]:
        subscriber: queue.Queue[Event] = queue.Queue()
        with self._lock:
            self._subscribers.append(subscriber)
        try:
            while True:
                yield subscriber.get()
        finally:
            with self._lock:
                if subscriber in self._subscribers:
                    self._subscribers.remove(subscriber)

