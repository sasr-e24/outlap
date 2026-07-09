"""Synthetic circuit geometry for the offline fixture.

A closed parametric curve standing in for a real track. Real replays get their
outline from FastF1 (fastest lap X/Y telemetry), so this exists purely so the
track map, moving cars and telemetry panel are all exercisable with no network.

Speed is derived from the *actual local curvature* of the curve rather than
being invented per-corner: tight radius -> slow, straight -> fast. That means
the fixture's telemetry is at least internally consistent with its own geometry,
which is what makes it a useful visual harness rather than noise.
"""

from __future__ import annotations

import math
from typing import List, Tuple

OUTLINE_POINTS = 400


def point_at(u: float) -> Tuple[float, float]:
    """Position at lap fraction u in [0, 1). Closed curve, arbitrary units."""
    t = 2.0 * math.pi * (u % 1.0)
    x = 1000.0 * math.cos(t) + 300.0 * math.cos(3.0 * t)
    y = 700.0 * math.sin(t) + 150.0 * math.sin(2.0 * t)
    return x, y


def outline() -> List[Tuple[float, float]]:
    return [point_at(i / OUTLINE_POINTS) for i in range(OUTLINE_POINTS)]


def _menger_radius(u: float, h: float = 1e-3) -> float:
    """Radius of the circle through three nearby points (Menger curvature)."""
    ax, ay = point_at(u - h)
    bx, by = point_at(u)
    cx, cy = point_at(u + h)
    ab = math.hypot(bx - ax, by - ay)
    bc = math.hypot(cx - bx, cy - by)
    ca = math.hypot(ax - cx, ay - cy)
    # twice the triangle area via the cross product
    area2 = abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax))
    if area2 < 1e-9:
        return float("inf")  # collinear => straight
    return (ab * bc * ca) / (2.0 * area2)


SPEED_MIN = 75.0
SPEED_MAX = 330.0


def speed_at(u: float) -> float:
    """km/h from local radius, clamped to a plausible F1 range."""
    r = _menger_radius(u)
    if r == float("inf"):
        return SPEED_MAX
    return max(SPEED_MIN, min(SPEED_MAX, SPEED_MIN + 0.16 * r))


def telemetry_at(u: float, du: float = 2e-3) -> dict:
    """Speed/throttle/brake/gear/rpm at lap fraction u.

    Throttle and brake come from whether the car is accelerating or decelerating
    into the next sample - crude, but it tracks the geometry honestly.
    """
    v = speed_at(u)
    v_next = speed_at(u + du)
    dv = v_next - v
    if dv < -1.0:
        brake, throttle = min(100.0, -dv * 4.0), 0.0
    else:
        brake, throttle = 0.0, min(100.0, 25.0 + dv * 6.0 + (v / SPEED_MAX) * 60.0)
    gear = max(1, min(8, 1 + int((v - SPEED_MIN) / ((SPEED_MAX - SPEED_MIN) / 7.5))))
    rpm = 6000.0 + 6000.0 * ((v - SPEED_MIN) / (SPEED_MAX - SPEED_MIN))
    return {
        "speed": round(v, 1),
        "throttle": round(throttle, 1),
        "brake": round(brake, 1),
        "gear": gear,
        "rpm": round(rpm, 0),
    }
