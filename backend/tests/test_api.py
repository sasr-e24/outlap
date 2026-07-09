"""API smoke test — the replay drives the WS stream and REST returns a tower."""

import os

os.environ.setdefault("OUTLAP_SOURCE", "synthetic")
os.environ.setdefault("OUTLAP_SPEED", "0")  # run the replay as fast as possible

from fastapi.testclient import TestClient  # noqa: E402

from outlap.api import app  # noqa: E402


def test_health_and_state():
    with TestClient(app) as client:
        assert client.get("/health").json()["ok"] is True

        # WS delivers at least a snapshot frame carrying the full contract the
        # frontend StateFrame type depends on (a missing key here is a silent
        # break in the UI, so pin every field).
        with client.websocket_connect("/ws") as ws:
            frame = ws.receive_json()
            assert frame["type"] == "state"
            for key in (
                "circuit",
                "sim_time",
                "current_lap",
                "total_laps",
                "track_status",
                "tower",
                "last_event",
            ):
                assert key in frame, f"WS state frame missing {key!r}"

        state = client.get("/api/state").json()
        assert state["total_laps"] > 0
        assert isinstance(state["tower"], list)
