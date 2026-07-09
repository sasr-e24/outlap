"""Model worker base.

Workers subscribe to the bus, read (never mutate) RaceState, and publish
`Prediction` events back onto the bus. Every prediction is logged to the ledger
and scored post-race. This keeps the LLM/statistical split clean: models compute
consequences; nothing downstream trusts a model to mutate the canonical state.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from ..bus import EventBus
from ..events import Event, Prediction
from ..state import RaceState


class ModelWorker(ABC):
    name: str = "model"

    def __init__(self, bus: EventBus, state: RaceState):
        self.bus = bus
        self.state = state

    @abstractmethod
    async def on_event(self, event: Event) -> List[Prediction]:
        """React to an event; return zero or more predictions to publish."""
        raise NotImplementedError

    async def _handle(self, event: Event) -> None:
        # ignore our own predictions to avoid feedback loops
        if isinstance(event, Prediction):
            return
        for pred in await self.on_event(event):
            await self.bus.publish(pred)

    def attach(self) -> None:
        self.bus.subscribe(Event, self._handle)
