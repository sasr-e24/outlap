"""DataSource port.

Every adapter (replay, OpenF1 live, raw SignalR) implements this one interface
and emits the same normalized `Event` stream. Downstream code depends only on
this port, never on a concrete source — going live is a config change plus one
adapter, not a rewrite.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from ..events import Event


class DataSource(ABC):
    """A source of normalized race events."""

    #: human-readable id used in logs and the UI data-age badge
    name: str = "base"

    @abstractmethod
    async def events(self) -> AsyncIterator[Event]:
        """Yield normalized events in sim_time order.

        Live sources yield indefinitely as data arrives. Replay sources yield a
        finite, ordered log (optionally pacing themselves to `speed`).
        """
        raise NotImplementedError
        yield  # pragma: no cover  (makes this an async generator)
