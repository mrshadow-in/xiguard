export type WSMessage =
  | { type: "traffic_update"; data: TrafficUpdate }
  | { type: "alert"; data: AlertEvent }
  | { type: "state_change"; data: StateChangeEvent }
  | { type: "chr_status"; data: ChrStatusEvent };

export interface TrafficUpdate {
  ip: string;
  bps_in: number;
  bps_out: number;
  pps_in: number;
  baseline_bps: number;
  state: string;
  chr_node: string;
  pool: string;
}

export interface AlertEvent {
  id: string;
  ip: string;
  severity: "critical" | "warning" | "info";
  type: string;
  baseline_bps: number;
  peak_bps: number;
  multiplier: number;
  action_taken: string;
  timestamp: string;
}

export interface StateChangeEvent {
  ip: string;
  old_state: string;
  new_state: string;
  timestamp: string;
}

export interface ChrStatusEvent {
  chr_id: string;
  name: string;
  status: "online" | "offline";
}

export function buildWsUrl(): string {
  if (typeof window === "undefined") return "";
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/api/ws`;
}
