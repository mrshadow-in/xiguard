"use client";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { StatusBadge } from "@/components/StatusBadge";
import { api } from "@/lib/api";
import { relTime } from "@/lib/utils";

interface TaskStat {
  name: string;
  label: string;
  schedule_human: string;
  schedule_sec: number | null;
  last_run_at: string | null;
  duration_ms: number | null;
  next_run_eta_sec: number | null;
  count: number;
  last_result: Record<string, unknown> | null;
}

interface ExporterStat {
  exporter: string;
  packets: number;
  last_packet_at: string | null;
}

interface CHRFlow {
  id: string;
  name: string;
  host: string;
  status: string;
  last_seen_at: string | null;
  monitored_ip_count: number;
  actively_flowing: number;
}

interface PollingStatus {
  poll_interval_sec: number;
  last_poll_at: string | null;
  last_poll_duration_ms: number | null;
  last_poll_ips_evaluated: number | null;
  last_poll_ips_with_data: number | null;
  next_poll_eta_sec: number | null;
  cycles_total: number;
  flow_packets_total: number;
  flow_records_total: number;
  flow_active_ips: number;
  last_flow_at: string | null;
  flow_exporters: ExporterStat[];
  tasks: TaskStat[];
  chrs: CHRFlow[];
}

function StatCard({
  label,
  value,
  sub,
  warn,
}: {
  label: string;
  value: string;
  sub?: string;
  warn?: boolean;
}) {
  return (
    <div className="panel p-4">
      <div className="text-[11px] uppercase tracking-wider text-ink-mute">{label}</div>
      <div
        className={`mt-1 font-mono text-2xl ${
          warn ? "text-state-blackhole" : "text-ink"
        }`}
      >
        {value}
      </div>
      {sub && <div className="mt-0.5 text-xs text-ink-mute">{sub}</div>}
    </div>
  );
}

function fmtDur(ms: number | null): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

function fmtEta(sec: number | null): string {
  if (sec == null) return "—";
  if (sec < 1) return "now";
  if (sec < 60) return `${sec.toFixed(1)}s`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ${Math.floor(sec % 60)}s`;
  return `${Math.floor(sec / 3600)}h`;
}

function fmtNum(n: number): string {
  return n.toLocaleString("en-US");
}

export default function PollingPage() {
  const [s, setS] = useState<PollingStatus | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const refresh = async () => setS(await api.get<PollingStatus>("/polling-status"));
    refresh();
    const id = setInterval(refresh, 2500);
    return () => clearInterval(id);
  }, []);

  // 1s tick to count down "next poll in" between server refreshes
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, []);

  if (!s) {
    return (
      <AppShell>
        <div className="text-ink-mute">Loading…</div>
      </AppShell>
    );
  }

  // Live ETA between API refreshes
  const liveEta = (() => {
    if (s.next_poll_eta_sec == null || !s.last_poll_at) return s.next_poll_eta_sec;
    const elapsed = (Date.now() - new Date(s.last_poll_at).getTime()) / 1000;
    return Math.max(0, s.poll_interval_sec - elapsed);
  })();

  const flowAgeSec = s.last_flow_at
    ? (Date.now() - new Date(s.last_flow_at).getTime()) / 1000
    : null;
  const pollAgeSec = s.last_poll_at
    ? (Date.now() - new Date(s.last_poll_at).getTime()) / 1000
    : null;
  void tick;

  return (
    <AppShell>
      <div className="space-y-5">
        <div>
          <h1 className="text-lg font-semibold">Polling Status</h1>
          <p className="text-xs text-ink-mute">
            Live worker activity. Auto-refresh every 2.5s.
          </p>
        </div>

        {/* Top: last poll + next poll */}
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          <StatCard
            label="Last Poll"
            value={pollAgeSec == null ? "never" : `${pollAgeSec.toFixed(1)}s ago`}
            sub={s.last_poll_at ? new Date(s.last_poll_at).toLocaleTimeString() : "—"}
            warn={pollAgeSec != null && pollAgeSec > s.poll_interval_sec * 3}
          />
          <StatCard
            label="Next Poll In"
            value={fmtEta(liveEta)}
            sub={`interval ${s.poll_interval_sec}s`}
          />
          <StatCard
            label="Last Duration"
            value={fmtDur(s.last_poll_duration_ms)}
            sub={`budget ${s.poll_interval_sec}s`}
            warn={
              s.last_poll_duration_ms != null &&
              s.last_poll_duration_ms > s.poll_interval_sec * 1000
            }
          />
          <StatCard
            label="IPs Evaluated"
            value={fmtNum(s.last_poll_ips_evaluated ?? 0)}
            sub={`${fmtNum(s.last_poll_ips_with_data ?? 0)} with data`}
          />
          <StatCard label="Cycles Total" value={fmtNum(s.cycles_total)} />
        </div>

        {/* Flow collector */}
        <div className="panel p-4">
          <div className="mb-3 flex items-center justify-between">
            <div className="text-sm font-semibold">NetFlow Collector</div>
            <span
              className={`chip ${
                flowAgeSec == null || flowAgeSec > 30
                  ? "border-state-offline/40 text-state-offline"
                  : "border-state-normal/40 text-state-normal"
              }`}
            >
              {flowAgeSec == null
                ? "no traffic yet"
                : flowAgeSec > 30
                  ? `quiet ${Math.floor(flowAgeSec)}s`
                  : `live · last ${flowAgeSec.toFixed(1)}s ago`}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatCard label="Packets received" value={fmtNum(s.flow_packets_total)} />
            <StatCard label="Records parsed" value={fmtNum(s.flow_records_total)} />
            <StatCard label="Active IP counters" value={fmtNum(s.flow_active_ips)} />
            <StatCard
              label="Exporters"
              value={fmtNum(s.flow_exporters.length)}
              sub="distinct CHR sources"
            />
          </div>

          <div className="mt-4 overflow-hidden rounded border border-bg-border">
            <table className="w-full">
              <thead className="border-b border-bg-border bg-bg-elev">
                <tr>
                  <th className="table-th">Exporter IP</th>
                  <th className="table-th">Packets</th>
                  <th className="table-th">Last packet</th>
                </tr>
              </thead>
              <tbody>
                {s.flow_exporters.map((e) => (
                  <tr key={e.exporter} className="border-b border-bg-border last:border-0">
                    <td className="table-td font-mono">{e.exporter}</td>
                    <td className="table-td font-mono">{fmtNum(e.packets)}</td>
                    <td className="table-td text-ink-mute">{relTime(e.last_packet_at)}</td>
                  </tr>
                ))}
                {s.flow_exporters.length === 0 && (
                  <tr>
                    <td colSpan={3} className="table-td text-center text-ink-mute">
                      No NetFlow packets received yet. Check{" "}
                      <code>/ip traffic-flow target print</code> on each CHR.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Per-CHR flow visibility */}
        <div className="panel p-4">
          <div className="mb-3 text-sm font-semibold">CHR ↔ Flow Visibility</div>
          <div className="overflow-hidden rounded border border-bg-border">
            <table className="w-full">
              <thead className="border-b border-bg-border bg-bg-elev">
                <tr>
                  <th className="table-th">CHR</th>
                  <th className="table-th">Host</th>
                  <th className="table-th">Status</th>
                  <th className="table-th">Health</th>
                  <th className="table-th">IPs</th>
                  <th className="table-th">Flowing now</th>
                  <th className="table-th">Coverage</th>
                </tr>
              </thead>
              <tbody>
                {s.chrs.map((c) => {
                  const pct =
                    c.monitored_ip_count > 0
                      ? Math.round((c.actively_flowing / c.monitored_ip_count) * 100)
                      : 0;
                  return (
                    <tr key={c.id} className="border-b border-bg-border last:border-0">
                      <td className="table-td">{c.name}</td>
                      <td className="table-td font-mono">{c.host}</td>
                      <td className="table-td">
                        <StatusBadge state={c.status} />
                      </td>
                      <td className="table-td text-ink-mute">{relTime(c.last_seen_at)}</td>
                      <td className="table-td font-mono">{fmtNum(c.monitored_ip_count)}</td>
                      <td className="table-td font-mono">{fmtNum(c.actively_flowing)}</td>
                      <td className="table-td">
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 w-24 overflow-hidden rounded bg-bg-border">
                            <div
                              className={`h-full ${
                                pct > 50
                                  ? "bg-state-normal"
                                  : pct > 0
                                    ? "bg-state-alert"
                                    : "bg-state-offline"
                              }`}
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                          <span className="font-mono text-xs text-ink-mute">{pct}%</span>
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {s.chrs.length === 0 && (
                  <tr>
                    <td colSpan={7} className="table-td text-center text-ink-mute">
                      No CHRs configured.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Scheduled tasks */}
        <div className="panel p-4">
          <div className="mb-3 text-sm font-semibold">Scheduled Tasks (Celery Beat)</div>
          <div className="overflow-hidden rounded border border-bg-border">
            <table className="w-full">
              <thead className="border-b border-bg-border bg-bg-elev">
                <tr>
                  <th className="table-th">Task</th>
                  <th className="table-th">Schedule</th>
                  <th className="table-th">Last run</th>
                  <th className="table-th">Duration</th>
                  <th className="table-th">Next in</th>
                  <th className="table-th">Runs</th>
                  <th className="table-th">Last result</th>
                </tr>
              </thead>
              <tbody>
                {s.tasks.map((t) => {
                  // Live countdown for interval tasks
                  let nextEta = t.next_run_eta_sec;
                  if (t.schedule_sec != null && t.last_run_at) {
                    const elapsed =
                      (Date.now() - new Date(t.last_run_at).getTime()) / 1000;
                    nextEta = Math.max(0, t.schedule_sec - elapsed);
                  }
                  return (
                    <tr key={t.name} className="border-b border-bg-border last:border-0">
                      <td className="table-td">
                        <div>{t.label}</div>
                        <div className="font-mono text-[11px] text-ink-mute">{t.name}</div>
                      </td>
                      <td className="table-td text-ink-mute">{t.schedule_human}</td>
                      <td className="table-td text-ink-mute">{relTime(t.last_run_at)}</td>
                      <td className="table-td font-mono">{fmtDur(t.duration_ms)}</td>
                      <td className="table-td font-mono">{fmtEta(nextEta)}</td>
                      <td className="table-td font-mono">{fmtNum(t.count)}</td>
                      <td className="table-td">
                        {t.last_result && Object.keys(t.last_result).length > 0 ? (
                          <code className="text-[11px] text-ink-mute">
                            {Object.entries(t.last_result)
                              .map(([k, v]) => `${k}=${v}`)
                              .join(" ")}
                          </code>
                        ) : (
                          <span className="text-ink-dim">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
