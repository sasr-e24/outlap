export interface TowerRow {
  position: number;
  driver: string;
  lap: number;
  last_lap_time: number | null;
  compound: string;
  tyre_age: number;
  gap_to_leader: number | null;
  interval_ahead: number | null;
  in_pit: boolean;
  pit_stops: number;
}

export interface StateFrame {
  type: "state";
  circuit: string;
  sim_time: number;
  current_lap: number;
  total_laps: number;
  track_status: string;
  tower: TowerRow[];
  last_event: string;
}

export interface PredictionFrame {
  type: "prediction";
  sim_time: number;
  model: string;
  driver: string;
  metric: string;
  value: number;
  payload: Record<string, unknown>;
}

export type Frame = StateFrame | PredictionFrame;
