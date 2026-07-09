"""FastF1 → normalized event log.

Kept separate and imported lazily so the core package does not depend on
fastf1/pandas. Turns a real session into the same `Event` stream the synthetic
fixture produces, so downstream code cannot tell them apart.

Lap-resolution events (LapCompleted, GapUpdate, Pit*, StintChange, Weather,
RaceControl) plus, when `with_telemetry` is on, the circuit outline and
downsampled car positions/telemetry that drive the track map.
"""

from __future__ import annotations

from typing import List, Optional

from ..events import (
    Compound,
    Event,
    GapUpdate,
    LapCompleted,
    PitEntry,
    PitExit,
    PositionSample,
    RaceControl,
    SessionInfo,
    StintChange,
    TelemetrySample,
    TrackOutline,
    Weather,
)

#: seconds between position/telemetry samples pulled from FastF1. The raw feed is
#: far denser (~4 Hz position, ~3.7 Hz car data); we downsample so a 2-hour race
#: doesn't become millions of events.
POSITION_DT_S = 1.0


def _compound(raw) -> Compound:
    if raw is None:
        return Compound.UNKNOWN
    try:
        return Compound(str(raw).upper())
    except ValueError:
        return Compound.UNKNOWN


def _secs(td) -> Optional[float]:
    """pandas Timedelta / NaT → float seconds or None."""
    if td is None:
        return None
    try:
        import pandas as pd

        if pd.isna(td):
            return None
    except Exception:
        pass
    try:
        return float(td.total_seconds())
    except AttributeError:
        try:
            return float(td)
        except (TypeError, ValueError):
            return None


def load_fastf1_event_log(
    year: int,
    gp,
    session: str = "R",
    cache_dir: Optional[str] = None,
    with_telemetry: bool = True,
) -> List[Event]:
    import fastf1

    if cache_dir:
        fastf1.Cache.enable_cache(cache_dir)

    ses = fastf1.get_session(year, gp, session)
    ses.load(telemetry=with_telemetry, weather=True, messages=True)

    events: List[Event] = []
    t0 = ses.laps["LapStartTime"].min() if "LapStartTime" in ses.laps else None

    def rel(t) -> float:
        s = _secs(t)
        base = _secs(t0) if t0 is not None else 0.0
        return (s or 0.0) - (base or 0.0)

    total_laps = int(ses.total_laps) if getattr(ses, "total_laps", None) else 0
    events.append(
        SessionInfo(
            sim_time=0.0,
            year=year,
            round=int(getattr(ses.event, "RoundNumber", 0) or 0),
            circuit=str(getattr(ses.event, "EventName", "") or ""),
            session=session,
            total_laps=total_laps,
        )
    )

    laps = ses.laps.sort_values("LapStartTime")
    seen_stint: dict = {}
    for _, lap in laps.iterrows():
        drv = str(lap.get("Driver") or lap.get("Abbreviation") or "")
        if not drv:
            continue
        lap_no = int(lap["LapNumber"]) if lap.get("LapNumber") == lap.get("LapNumber") else 0
        start = rel(lap.get("LapStartTime"))
        stint_no = int(lap["Stint"]) if lap.get("Stint") == lap.get("Stint") else 0
        comp = _compound(lap.get("Compound"))

        key = (drv, stint_no)
        if stint_no and key not in seen_stint:
            seen_stint[key] = True
            events.append(
                StintChange(
                    sim_time=start,
                    driver=drv,
                    stint_number=stint_no,
                    compound=comp,
                    start_lap=lap_no,
                )
            )

        pit_in = _secs(lap.get("PitInTime"))
        pit_out = _secs(lap.get("PitOutTime"))
        if pit_in is not None:
            events.append(PitEntry(sim_time=rel(lap.get("PitInTime")), driver=drv, lap_number=lap_no))
        if pit_out is not None:
            events.append(
                PitExit(
                    sim_time=rel(lap.get("PitOutTime")),
                    driver=drv,
                    lap_number=lap_no,
                    new_compound=comp,
                )
            )

        end = rel(lap.get("LapStartTime")) + (_secs(lap.get("LapTime")) or 0.0)
        events.append(
            LapCompleted(
                sim_time=end,
                driver=drv,
                lap_number=lap_no,
                lap_time=_secs(lap.get("LapTime")),
                position=int(lap["Position"]) if lap.get("Position") == lap.get("Position") else 0,
                compound=comp,
                tyre_age=int(lap["TyreLife"]) if lap.get("TyreLife") == lap.get("TyreLife") else 0,
                is_pit_lap=pit_in is not None or pit_out is not None,
            )
        )

    # weather
    if ses.weather_data is not None:
        for _, w in ses.weather_data.iterrows():
            events.append(
                Weather(
                    sim_time=rel(w.get("Time")),
                    air_temp=float(w["AirTemp"]) if w.get("AirTemp") == w.get("AirTemp") else None,
                    track_temp=float(w["TrackTemp"]) if w.get("TrackTemp") == w.get("TrackTemp") else None,
                    rainfall=bool(w.get("Rainfall")),
                )
            )

    # race control
    if ses.race_control_messages is not None:
        for _, m in ses.race_control_messages.iterrows():
            events.append(
                RaceControl(
                    sim_time=rel(m.get("Time")),
                    message=str(m.get("Message") or ""),
                    category=str(m.get("Category") or ""),
                    flag=str(m["Flag"]) if m.get("Flag") == m.get("Flag") else None,
                )
            )

    if with_telemetry:
        events.extend(_geometry_events(ses, rel))

    events.sort(key=lambda e: e.sim_time)
    return events


def _geometry_events(ses, rel) -> List[Event]:
    """Track outline (from the fastest lap's X/Y) + downsampled car positions.

    FastF1 exposes position and car-data channels per driver. We resample onto a
    fixed grid so the event rate is predictable and the replay stays light.
    """
    out: List[Event] = []

    # circuit outline: the fastest lap traces the racing line, which is close
    # enough to the track shape for a map.
    try:
        fastest = ses.laps.pick_fastest()
        tel = fastest.get_telemetry()
        pts = [(float(x), float(y)) for x, y in zip(tel["X"], tel["Y"])]
        # thin to keep the payload sane
        step = max(1, len(pts) // 500)
        out.append(TrackOutline(sim_time=0.0, points=tuple(pts[::step])))
    except Exception:
        pass  # no telemetry for this session; the map simply won't render

    for drv in ses.drivers:
        try:
            abbr = ses.get_driver(drv)["Abbreviation"]
            pos = ses.pos_data[drv]
            car = ses.car_data[drv]
        except Exception:
            continue

        last_t = None
        for _, row in pos.iterrows():
            t = rel(row.get("Date")) if "Date" in row else None
            t = _secs(row.get("SessionTime")) if t is None else t
            if t is None:
                continue
            if last_t is not None and (t - last_t) < POSITION_DT_S:
                continue
            last_t = t
            out.append(
                PositionSample(sim_time=t, driver=abbr, x=float(row["X"]), y=float(row["Y"]))
            )

        last_t = None
        for _, row in car.iterrows():
            t = _secs(row.get("SessionTime"))
            if t is None:
                continue
            if last_t is not None and (t - last_t) < POSITION_DT_S:
                continue
            last_t = t
            out.append(
                TelemetrySample(
                    sim_time=t,
                    driver=abbr,
                    speed=float(row.get("Speed") or 0.0),
                    throttle=float(row.get("Throttle") or 0.0),
                    brake=100.0 if row.get("Brake") else 0.0,
                    gear=int(row.get("nGear") or 0),
                    rpm=float(row.get("RPM") or 0.0),
                )
            )

    return out
