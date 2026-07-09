"""Race engine — wires a DataSource into the bus, state, models and sinks.

    source.events() ─▶ bus.publish ─▶ [ state.apply, model workers, sinks ]
                                          │                │
                                          │                └─▶ Prediction ─▶ bus ─▶ ledger + sinks
                                          └─▶ canonical RaceState

The engine is source-agnostic: hand it a ReplaySource today, an OpenF1LiveSource
at P4, nothing else changes. Sinks (e.g. the WebSocket fan-out) subscribe to the
bus for the events/predictions they care about.
"""

from __future__ import annotations

import asyncio
from typing import List, Optional

from .bus import EventBus
from .events import Event, Prediction
from .models.base import ModelWorker
from .models.deg import DegFitter
from .sources.base import DataSource
from .state import RaceState


class PredictionLedger:
    """In-memory prediction store for P0. Postgres-backed at P1+.

    Every published probability lands here with its timestamp so it can be scored
    against the known outcome on replays (Brier score + calibration → Models page).
    """

    def __init__(self) -> None:
        self.rows: List[Prediction] = []

    async def record(self, event: Event) -> None:
        if isinstance(event, Prediction):
            self.rows.append(event)

    def latest_by_driver(self, model: str, metric: str) -> dict:
        out: dict = {}
        for p in self.rows:
            if p.model == model and p.metric == metric:
                out[p.driver] = p
        return out


class Engine:
    def __init__(self, source: DataSource):
        self.source = source
        self.bus = EventBus()
        self.state = RaceState()
        self.ledger = PredictionLedger()
        self.models: List[ModelWorker] = []
        self._on_change_cbs: list = []

        # canonical state is a bus subscriber
        self.bus.subscribe(Event, self._apply_to_state)
        self.bus.subscribe(Prediction, self.ledger.record)

        # default model set (P0 ships the deg fitter as a worked example)
        self._register_default_models()

    def _register_default_models(self) -> None:
        for cls in (DegFitter,):
            worker = cls(self.bus, self.state)
            worker.attach()
            self.models.append(worker)

    async def _apply_to_state(self, event: Event) -> None:
        if isinstance(event, Prediction):
            return
        self.state.apply(event)
        for cb in self._on_change_cbs:
            await cb(event, self.state)

    def on_change(self, cb) -> None:
        """Register async callback(event, state) — used by the WS fan-out."""
        self._on_change_cbs.append(cb)

    async def run(self, max_events: Optional[int] = None) -> RaceState:
        """Drive the source to completion (or `max_events`)."""
        n = 0
        async for event in self.source.events():
            seq = self.bus.next_seq()
            event = _with_seq(event, seq)
            await self.bus.publish(event)
            n += 1
            if max_events is not None and n >= max_events:
                break
        return self.state


def _with_seq(event: Event, seq: int) -> Event:
    from dataclasses import replace

    return replace(event, seq=seq)


async def run_replay(source: DataSource) -> Engine:
    engine = Engine(source)
    await engine.run()
    return engine
