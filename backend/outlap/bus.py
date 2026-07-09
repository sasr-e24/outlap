"""In-process async event bus.

v1 is a simple asyncio pub/sub — one process, no external broker. The interface
is deliberately minimal so it can be swapped for Redis Streams later (the
architecture doc's "asyncio in-proc → Redis later") without touching publishers
or subscribers.

Subscribers receive events by type. A subscriber registered for `Event` (the
base class) receives everything, which is how the ingestion/persistence sinks and
the WebSocket fan-out attach themselves.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Awaitable, Callable, DefaultDict, Type

from .events import Event

Handler = Callable[[Event], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._subs: DefaultDict[Type[Event], list[Handler]] = defaultdict(list)
        self._seq = 0

    def subscribe(self, event_type: Type[Event], handler: Handler) -> None:
        """Register `handler` for `event_type` (and all its subclasses)."""
        self._subs[event_type].append(handler)

    def next_seq(self) -> int:
        self._seq += 1
        return self._seq

    async def publish(self, event: Event) -> None:
        """Deliver an event to every matching subscriber.

        Matching is by isinstance against the registered type, so subscribing to
        the base `Event` receives the full firehose. Handlers are awaited
        sequentially to preserve ordering guarantees within a single publish.
        """
        for registered_type, handlers in self._subs.items():
            if isinstance(event, registered_type):
                for handler in handlers:
                    await handler(event)

    async def publish_all(self, events) -> None:
        for event in events:
            await self.publish(event)
