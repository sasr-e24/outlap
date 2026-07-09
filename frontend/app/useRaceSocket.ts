"use client";

import { useEffect, useRef, useState } from "react";
import type {
  Car,
  DegInfo,
  Frame,
  PitInfo,
  StateFrame,
  UndercutInfo,
} from "./types";

const WS_URL = process.env.NEXT_PUBLIC_OUTLAP_WS ?? "ws://localhost:8000/ws";
const API_URL = process.env.NEXT_PUBLIC_OUTLAP_API ?? "http://localhost:8000";

export function useRaceSocket() {
  const [state, setState] = useState<StateFrame | null>(null);
  const [cars, setCars] = useState<Car[]>([]);
  const [outline, setOutline] = useState<[number, number][]>([]);
  const [deg, setDeg] = useState<Record<string, DegInfo>>({});
  const [pit, setPit] = useState<Record<string, PitInfo>>({});
  const [undercut, setUndercut] = useState<Record<string, UndercutInfo>>({});
  const [connected, setConnected] = useState(false);
  const [dataAge, setDataAge] = useState(0);
  const lastFrameAt = useRef<number>(Date.now());

  // the circuit outline is static for a session, so fetch it once over REST
  useEffect(() => {
    fetch(`${API_URL}/api/track`)
      .then((r) => r.json())
      .then((d) => setOutline(d.outline ?? []))
      .catch(() => setOutline([]));
  }, []);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    let retry: ReturnType<typeof setTimeout>;

    const connect = () => {
      ws = new WebSocket(WS_URL);
      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        if (!closed) retry = setTimeout(connect, 1500);
      };
      ws.onmessage = (ev) => {
        const frame = JSON.parse(ev.data) as Frame;
        lastFrameAt.current = Date.now();
        if (frame.type === "state") {
          setState(frame);
        } else if (frame.type === "cars") {
          setCars(frame.cars);
        } else if (frame.type === "prediction") {
          const p = frame.payload;
          if (frame.metric === "deg_slope_s_per_lap") {
            setDeg((prev) => ({
              ...prev,
              [frame.driver]: {
                slope: frame.value,
                compound: String(p.compound ?? ""),
                stderr: (p.slope_stderr as number | null) ?? null,
              },
            }));
          } else if (frame.metric === "laps_to_optimal_stop") {
            setPit((prev) => ({
              ...prev,
              [frame.driver]: {
                lapsToStop: frame.value,
                open: Boolean(p.open),
                optimalLap: Number(p.optimal_lap ?? 0),
                assumed: Boolean(p.next_slope_assumed),
                extendDeltas: (p.extend_deltas_s as Record<string, number>) ?? {},
              },
            }));
          } else if (frame.metric === "p_undercut") {
            setUndercut((prev) => ({
              ...prev,
              [frame.driver]: {
                p: frame.value,
                defender: String(p.defender ?? ""),
                gap: Number(p.gap_s ?? 0),
                delta: Number(p.delta_s ?? 0),
              },
            }));
          }
        }
      };
    };
    connect();

    const ageTimer = setInterval(
      () => setDataAge((Date.now() - lastFrameAt.current) / 1000),
      200,
    );

    return () => {
      closed = true;
      clearTimeout(retry);
      clearInterval(ageTimer);
      ws?.close();
    };
  }, []);

  return { state, cars, outline, deg, pit, undercut, connected, dataAge };
}
