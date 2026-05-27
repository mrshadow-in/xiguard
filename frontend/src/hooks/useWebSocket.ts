"use client";
import { useEffect, useRef } from "react";
import { buildWsUrl, type WSMessage } from "@/lib/ws";
import { useTrafficStore } from "@/stores/trafficStore";
import { useAlertStore } from "@/stores/alertStore";

export function useWebSocket(): { connected: boolean } {
  const ref = useRef<WebSocket | null>(null);
  const connectedRef = useRef(false);
  const upsertTraffic = useTrafficStore((s) => s.upsert);
  const pushAlert = useAlertStore((s) => s.push);

  useEffect(() => {
    let stopped = false;
    let backoff = 1000;
    let pingTimer: ReturnType<typeof setInterval> | null = null;

    const connect = () => {
      if (stopped) return;
      const ws = new WebSocket(buildWsUrl());
      ref.current = ws;

      ws.onopen = () => {
        connectedRef.current = true;
        backoff = 1000;
        pingTimer = setInterval(() => {
          try {
            ws.send("ping");
          } catch {
            /* noop */
          }
        }, 25_000);
      };

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data) as WSMessage;
          if (msg.type === "traffic_update") upsertTraffic(msg.data);
          else if (msg.type === "alert") pushAlert(msg.data);
          // state_change / chr_status: consumers can subscribe via window events if needed
        } catch {
          /* ignore non-json */
        }
      };

      ws.onclose = () => {
        connectedRef.current = false;
        if (pingTimer) clearInterval(pingTimer);
        if (!stopped) {
          setTimeout(connect, backoff);
          backoff = Math.min(backoff * 2, 15_000);
        }
      };

      ws.onerror = () => {
        try {
          ws.close();
        } catch {
          /* noop */
        }
      };
    };

    connect();
    return () => {
      stopped = true;
      if (pingTimer) clearInterval(pingTimer);
      try {
        ref.current?.close();
      } catch {
        /* noop */
      }
    };
  }, [pushAlert, upsertTraffic]);

  return { connected: connectedRef.current };
}
