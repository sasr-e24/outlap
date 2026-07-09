"use client";

import { useEffect, useRef, useState } from "react";
import type { Frame, StateFrame } from "./types";

const WS_URL =
  process.env.NEXT_PUBLIC_OUTLAP_WS ?? "ws://localhost:8000/ws";

export interface DegInfo {
  slope: number;
  compound: string;
  stderr: number | null;
}

export function useRaceSocket() {
  const [state, setState] = useState<StateFrame | null>(null);
  const [deg, setDeg] = useState<Record<string, DegInfo>>({});
  const [connected, setConnected] = useState(false);
  const [dataAge, setDataAge] = useState<number>(0);
  const lastSimTime = useRef(0);

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
        if (frame.type === "state") {
          lastSimTime.current = frame.sim_time;
          setState(frame);
        } else if (frame.type === "prediction" && frame.metric === "deg_slope_s_per_lap") {
          setDeg((prev) => ({
            ...prev,
            [frame.driver]: {
              slope: frame.value,
              compound: String(frame.payload.compound ?? ""),
              stderr: (frame.payload.slope_stderr as number | null) ?? null,
            },
          }));
        }
      };
    };
    connect();

    const ageTimer = setInterval(() => {
      setDataAge((d) => (state ? d + 0.25 : 0));
    }, 250);

    return () => {
      closed = true;
      clearTimeout(retry);
      clearInterval(ageTimer);
      ws?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { state, deg, connected, dataAge };
}
