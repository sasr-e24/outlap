"""FastAPI app — REST for state/history + WebSocket push of live deltas.

P0 serves a single replay (the synthetic fixture by default, or a FastF1 session
via env vars) so the frontend timing tower has something live to render. The
engine drives the replay in a background task; every state change is fanned out
to connected WebSocket clients.

Run:  uvicorn outlap.api:app --reload
Env:
  OUTLAP_SOURCE = "synthetic" (default) | "fastf1"
  OUTLAP_SPEED  = playback multiplier for the WS stream (default 10)
  OUTLAP_FF1_YEAR / OUTLAP_FF1_GP / OUTLAP_FF1_SESSION (when source=fastf1)
  OUTLAP_FF1_CACHE = fastf1 cache dir
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import List, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .engine import Engine
from .events import Event, LapCompleted, Prediction
from .fixtures import build_synthetic_race
from .sources.replay import ReplaySource


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine
    engine = Engine(_build_source())

    async def fan_out(event: Event, state) -> None:
        frame = {
            "type": "state",
            "circuit": state.circuit,
            "sim_time": round(state.last_sim_time, 2),
            "current_lap": state.current_lap,
            "total_laps": state.total_laps,
            "track_status": state.track_status,
            "tower": state.timing_tower(),
            "last_event": event.kind,
        }
        await hub.broadcast(frame)

    engine.on_change(fan_out)

    async def preds_out(pred: Prediction) -> None:
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


app = FastAPI(title="OUTLAP", version="0.0.1", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "version": "0.0.1"}


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
        # send a snapshot immediately so a late joiner isn't blank
        assert engine is not None
        await ws.send_json(
            {
                "type": "state",
                "circuit": engine.state.circuit,
                "sim_time": round(engine.state.last_sim_time, 2),
                "current_lap": engine.state.current_lap,
                "total_laps": engine.state.total_laps,
                "track_status": engine.state.track_status,
                "tower": engine.state.timing_tower(),
                "last_event": "snapshot",
            }
        )
        while True:
            # we don't expect client messages in P0; keep the socket alive
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(ws)
    except Exception:
        hub.disconnect(ws)
