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

export interface Car {
  driver: string;
  position: number;
  x: number | null;
  y: number | null;
  speed: number | null;
  throttle: number | null;
  brake: number | null;
  gear: number | null;
  rpm: number | null;
  in_pit: boolean;
  compound: string;
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

export interface CarsFrame {
  type: "cars";
  sim_time: number;
  cars: Car[];
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

export type Frame = StateFrame | CarsFrame | PredictionFrame;

export interface DegInfo {
  slope: number;
  compound: string;
  stderr: number | null;
}

export interface PitInfo {
  lapsToStop: number;
  open: boolean;
  optimalLap: number;
  assumed: boolean;
  extendDeltas: Record<string, number>;
}

export interface UndercutInfo {
  p: number;
  defender: string;
  gap: number;
  delta: number;
}
