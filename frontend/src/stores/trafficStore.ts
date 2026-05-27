import { create } from "zustand";
import type { TrafficUpdate } from "@/lib/ws";

interface TrafficState {
  byIp: Record<string, TrafficUpdate>;
  upsert: (u: TrafficUpdate) => void;
  setMany: (rows: TrafficUpdate[]) => void;
  clear: () => void;
}

export const useTrafficStore = create<TrafficState>((set) => ({
  byIp: {},
  upsert: (u) => set((s) => ({ byIp: { ...s.byIp, [u.ip]: u } })),
  setMany: (rows) => {
    const next: Record<string, TrafficUpdate> = {};
    for (const r of rows) next[r.ip] = r;
    set({ byIp: next });
  },
  clear: () => set({ byIp: {} }),
}));
