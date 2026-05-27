import { create } from "zustand";
import type { AlertEvent } from "@/lib/ws";

interface AlertState {
  recent: AlertEvent[];
  push: (a: AlertEvent) => void;
  clear: () => void;
}

const MAX = 50;

export const useAlertStore = create<AlertState>((set) => ({
  recent: [],
  push: (a) =>
    set((s) => ({
      recent: [a, ...s.recent.filter((x) => x.id !== a.id)].slice(0, MAX),
    })),
  clear: () => set({ recent: [] }),
}));
