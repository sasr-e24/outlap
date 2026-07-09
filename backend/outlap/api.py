"""FastAPI app — REST for state/track/predictions + WebSocket push of live deltas.

P0 serves a single replay (the synthetic fixture by default, or a FastF1 session
via env vars) so the frontend has something live to render. The engine drives the
replay in a background task; changes are fanned out to WebSocket clients.

Three frame types go over the socket:
  * ``state``      - timing tower + lap/flag context. Sent on race events only.
  * ``cars``       - positions + telemetry for the track map. Sent once per
                     position tick, not once per sample (6 drivers x 2 events).
  * ``prediction`` - any model output (deg, pit_window, undercut).

The track outline is static for a session, so it is served over REST rather than
pushed every frame.

Run:  uvicorn outlap.api:app --reload
Env:
  OUTLAP_SOURCE = "synthetic" (default) | "fastf1"
  OUTLAP_SPEED  = playback multiplier (default 10)
  OUTLAP_FF1_YEAR / OUTLAP_FF1_GP / OUTLAP_FF1_SESSION (when source=fastf1)
  OUTLAP_FF1_CACHE = fastf1 cache dir
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .engine import Engine
from .events import (
    Event,
    GapUpdate,
    LapCompleted,
    PitEntry,
    PitExit,
    PositionSample,
    Prediction,
    RaceControl,
    SessionInfo,
    StintChange,
    TelemetrySample,
)
from .fixtures import build_synthetic_race
from .sources.replay import ReplaySource

# events that change the timing tower / race context
_STATE_EVENTS = (LapCompleted, GapUpdate, PitEntry, PitExit, RaceControl, StintChange, SessionInfo)
_CAR_EVENTS = (PositionSample, TelemetrySample)


class Hub:
    """Tracks connected WebSocket clients and broadcasts JSON frames."""

    def __init__(self) -> None:
        self.clients: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.clients.discard(ws)

    async def broadcast(self, frame: dict) -> None:
        dead = []
        for ws in self.clients:
            try:
                await ws.send_json(frame)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


def _build_source() -> ReplaySource:
    speed = float(os.getenv("OUTLAP_SPEED", "10"))
    if os.getenv("OUTLAP_SOURCE", "synthetic") == "fastf1":
        return ReplaySource.from_fastf1(
            year=int(os.getenv("OUTLAP_FF1_YEAR", "2024")),
            gp=os.getenv("OUTLAP_FF1_GP", "Abu Dhabi"),
            session=os.getenv("OUTLAP_FF1_SESSION", "R"),
            speed=speed,
            cache_dir=os.getenv("OUTLAP_FF1_CACHE"),
        )
    return ReplaySource.from_event_log(build_synthetic_race(), speed=speed)


hub = Hub()
engine: Engine | None = None


def _state_frame(state) -> dict:
    return {
        "type": "state",
        "circuit": state.circuit,
        "sim_time": round(state.last_sim_time, 2),
        "current_lap": state.current_lap,
        "total_laps": state.total_laps,
        "track_status": state.track_status,
        "tower": state.timing_tower(),
        "last_event": "snapshot",
    }


def _cars_frame(state) -> dict:
    return {"type": "cars", "sim_time": round(state.last_sim_time, 2), "cars": state.cars()}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine
    engine = Engine(_build_source())

    # Position/telemetry arrive as a burst of samples sharing one sim_time. We
    # flush a `cars` frame only when the tick advances, so every broadcast shows
    # the whole field at a single instant rather than a half-updated grid.
    tick: dict = {"t": None}

    async def fan_out(event: Event, state) -> None:
        if isinstance(event, _CAR_EVENTS):
            if tick["t"] is not None and event.sim_time != tick["t"]:
                await hub.broadcast(_cars_frame(state))
            tick["t"] = event.sim_time
            return
        if isinstance(event, _STATE_EVENTS):
            frame = _state_frame(state)
            frame["last_event"] = event.kind
            await hub.broadcast(frame)

    engine.on_change(fan_out)

    async def preds_out(pred: Event) -> None:
        if not isinstance(pred, Prediction):
            return
        await hub.broadcast(
            {
                "type": "prediction",
                "sim_time": round(pred.sim_time, 2),
                "model": pred.model,
                "driver": pred.driver,
                "metric": pred.metric,
                "value": pred.value,
                "payload": pred.payload,
            }
        )

    engine.bus.subscribe(Prediction, preds_out)

    task = asyncio.create_task(engine.run())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="OUTLAP", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "version": "0.1.0"}


@app.get("/api/track")
async def get_track() -> dict:
    """Circuit outline. Static for a session, so fetched once by the client."""
    assert engine is not None
    return {"circuit": engine.state.circuit, "outline": engine.state.track_outline}


@app.get("/api/state")
async def get_state() -> dict:
    assert engine is not None
    s = engine.state
    return {
        "circuit": s.circuit,
        "session": s.session,
        "current_lap": s.current_lap,
        "total_laps": s.total_laps,
        "track_status": s.track_status,
        "sim_time": round(s.last_sim_time, 2),
        "tower": s.timing_tower(),
    }


@app.get("/api/cars")
async def get_cars() -> dict:
    assert engine is not None
    return _cars_frame(engine.state)


@app.get("/api/predictions/{model}/{metric}")
async def get_predictions(model: str, metric: str) -> dict:
    assert engine is not None
    latest = engine.ledger.latest_by_driver(model, metric)
    return {
        "model": model,
        "metric": metric,
        "drivers": {
            drv: {"value": p.value, "payload": p.payload, "sim_time": round(p.sim_time, 2)}
            for drv, p in latest.items()
        },
    }


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await hub.connect(ws)
    try:
        assert engine is not None
        # snapshot immediately so a late joiner isn't staring at a blank screen
        await ws.send_json(_state_frame(engine.state))
        await ws.send_json(_cars_frame(engine.state))
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(ws)
    except Exception:
        hub.disconnect(ws)
