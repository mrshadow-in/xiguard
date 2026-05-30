"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { StatusBadge } from "@/components/StatusBadge";
import { api } from "@/lib/api";
import { humanBps, relTime } from "@/lib/utils";
import { useTrafficStore } from "@/stores/trafficStore";
import { useAlertStore } from "@/stores/alertStore";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

interface AggregatePoint {
  bucket: string;
  bps_in: number;
  bps_out: number;
  pps_in: number;
  pps_out: number;
  ip_count: number;
}
interface AggregateSeries {
  hours: number;
  bucket_seconds: number;
  points: AggregatePoint[];
  current_total_bps_in: number;
  current_total_bps_out: number;
}

interface CHRNode {
  id: string;
  name: string;
  host: string;
  status: string;
  last_seen_at: string | null;
  monitored_ip_count: number;
}

interface Overview {
  total_chr_nodes: number;
  online_chr_nodes: number;
  total_ips: number;
  alert_count: number;
  blackhole_count: number;
}

interface IPSummary {
  id: string;
  ip_address: string;
  state: string;
  baseline_bps: number;
  current_bps: number;
}

interface AlertRow {
  id: string;
  ip_address: string | null;
  type: string;
  severity: string;
  baseline_bps: number | null;
  peak_bps: number | null;
  created_at: string;
}

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="panel p-4">
      <div className="text-[11px] uppercase tracking-wider text-ink-mute">{label}</div>
      <div className="mt-1 font-mono text-2xl text-ink">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-ink-mute">{sub}</div>}
    </div>
  );
}

function CHRHealthBar({ nodes }: { nodes: CHRNode[] }) {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
      {nodes.map((n) => (
        <div key={n.id} className="panel flex items-center justify-between p-3">
          <div>
            <div className="text-sm font-medium">{n.name}</div>
            <div className="font-mono text-xs text-ink-mute">{n.host}</div>
            <div className="mt-1 text-xs text-ink-mute">
              {n.monitored_ip_count} IPs · last {relTime(n.last_seen_at)}
            </div>
          </div>
          <StatusBadge state={n.status} />
        </div>
      ))}
      {nodes.length === 0 && (
        <div className="panel col-span-full p-6 text-center text-sm text-ink-mute">
          No CHR nodes yet. Add one in CHR Nodes.
        </div>
      )}
    </div>
  );
}

function IPStatusGrid({ rows }: { rows: IPSummary[] }) {
  const visible = rows.slice(0, 12);
  return (
    <div className="panel p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="text-sm font-semibold">IP Status</div>
        <div className="text-xs text-ink-mute">
          {rows.length} IPs · top {visible.length} by current bps
        </div>
      </div>
      <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
        {visible.map((ip) => {
          const ratio = ip.baseline_bps > 0 ? ip.current_bps / ip.baseline_bps : 0;
          const pct = Math.min(100, ratio * 20);
          return (
            <Link
              key={ip.id}
              href={`/ips/${encodeURIComponent(ip.ip_address)}`}
              className="block rounded-md border border-bg-border bg-bg-elev p-3 transition hover:border-state-recover/50 hover:bg-bg-border"
            >
              <div className="flex items-center justify-between">
                <div className="font-mono text-sm">{ip.ip_address}</div>
                <StatusBadge state={ip.state} />
              </div>
              <div className="mt-2 h-1.5 w-full overflow-hidden rounded bg-bg-border">
                <div
                  className={`h-full ${
                    ip.state === "BLACKHOLED"
                      ? "bg-state-blackhole"
                      : ip.state === "ALERT"
                        ? "bg-state-alert"
                        : "bg-state-normal"
                  }`}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <div className="mt-1.5 flex justify-between font-mono text-[11px] text-ink-mute">
                <span>cur {humanBps(ip.current_bps)}</span>
                <span>base {humanBps(ip.baseline_bps)}</span>
                <span>{ratio > 0 ? `${ratio.toFixed(1)}×` : "—"}</span>
              </div>
            </Link>
          );
        })}
        {visible.length === 0 && (
          <div className="col-span-full p-6 text-center text-sm text-ink-mute">
            Waiting for traffic samples…
          </div>
        )}
      </div>
    </div>
  );
}

function AlertFeed({ rows }: { rows: AlertRow[] }) {
  return (
    <div className="panel flex h-full flex-col p-4">
      <div className="mb-3 text-sm font-semibold">Live Alert Feed</div>
      <div className="-mx-1 flex-1 space-y-1.5 overflow-y-auto px-1">
        {rows.map((a) => (
          <div key={a.id} className="rounded-md border border-bg-border bg-bg-elev p-2.5">
            <div className="flex items-center justify-between text-[11px]">
              <span
                className={`font-semibold uppercase ${
                  a.severity === "critical"
                    ? "text-state-blackhole"
                    : a.severity === "warning"
                      ? "text-state-alert"
                      : "text-ink-mute"
                }`}
              >
                {a.severity}
              </span>
              <span className="font-mono text-ink-mute">{relTime(a.created_at)}</span>
            </div>
            <div className="mt-0.5 font-mono text-sm">{a.ip_address ?? "—"}</div>
            <div className="text-xs text-ink-mute">
              {a.type.replace("_", " ")}{" "}
              {a.peak_bps && a.baseline_bps
                ? `· ${(a.peak_bps / a.baseline_bps).toFixed(1)}× baseline`
                : ""}
            </div>
          </div>
        ))}
        {rows.length === 0 && (
          <div className="p-6 text-center text-sm text-ink-mute">No alerts in the last 24h.</div>
        )}
      </div>
    </div>
  );
}

const HOUR_RANGES = [
  { label: "1h", hours: 1 },
  { label: "6h", hours: 6 },
  { label: "24h", hours: 24 },
  { label: "7d", hours: 24 * 7 },
];

function AggregateChart() {
  const [hours, setHours] = useState(1);
  const [series, setSeries] = useState<AggregateSeries | null>(null);

  useEffect(() => {
    let alive = true;
    const refresh = async () => {
      try {
        const s = await api.get<AggregateSeries>(`/monitoring/aggregate?hours=${hours}`);
        if (alive) setSeries(s);
      } catch {
        /* ignore transient errors */
      }
    };
    refresh();
    const iv = setInterval(refresh, hours <= 1 ? 5000 : 15000);
    return () => {
      alive = false;
      clearInterval(iv);
    };
  }, [hours]);

  const chartData = useMemo(
    () =>
      (series?.points ?? []).map((p) => ({
        t: new Date(p.bucket).getTime(),
        bps_in: p.bps_in,
        bps_out: p.bps_out,
        ip_count: p.ip_count,
      })),
    [series],
  );

  return (
    <div className="panel p-4">
      <div className="mb-2 flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold">Aggregate Traffic — All Monitored IPs</div>
          <div className="text-xs text-ink-mute">
            now: <span className="font-mono text-state-recover">↓ {humanBps(series?.current_total_bps_in ?? 0)}</span>
            {" · "}
            <span className="font-mono text-state-normal">↑ {humanBps(series?.current_total_bps_out ?? 0)}</span>
            {" · "}
            bucket {series?.bucket_seconds ?? 5}s · {chartData.length} pts
          </div>
        </div>
        <div className="flex items-center gap-1 text-xs">
          {HOUR_RANGES.map((r) => (
            <button
              key={r.label}
              onClick={() => setHours(r.hours)}
              className={`rounded-md border px-2 py-1 ${
                hours === r.hours
                  ? "border-state-recover bg-state-recover/15 text-ink"
                  : "border-bg-border text-ink-mute hover:bg-bg-elev"
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData}>
            <defs>
              <linearGradient id="agg-in" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.5} />
                <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="agg-out" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#22c55e" stopOpacity={0.3} />
                <stop offset="100%" stopColor="#22c55e" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2733" />
            <XAxis
              dataKey="t"
              tickFormatter={(t) => {
                const d = new Date(t as number);
                return hours <= 24
                  ? d.toLocaleTimeString().slice(0, 5)
                  : `${d.getMonth() + 1}/${d.getDate()}`;
              }}
              stroke="#7b8597"
              tick={{ fontSize: 11 }}
            />
            <YAxis
              tickFormatter={(v) => humanBps(v as number)}
              stroke="#7b8597"
              tick={{ fontSize: 11 }}
              width={72}
            />
            <Tooltip
              labelFormatter={(t) => new Date(t as number).toLocaleString()}
              formatter={(v) => humanBps(v as number)}
              contentStyle={{ backgroundColor: "#11161d", border: "1px solid #1f2733" }}
            />
            <Area
              type="monotone"
              dataKey="bps_in"
              stroke="#3b82f6"
              fill="url(#agg-in)"
              name="Inbound"
            />
            <Area
              type="monotone"
              dataKey="bps_out"
              stroke="#22c55e"
              fill="url(#agg-out)"
              name="Outbound"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [nodes, setNodes] = useState<CHRNode[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [ips, setIps] = useState<IPSummary[]>([]);
  const [alerts, setAlerts] = useState<AlertRow[]>([]);
  const liveTraffic = useTrafficStore((s) => s.byIp);
  const liveAlerts = useAlertStore((s) => s.recent);

  useEffect(() => {
    const refresh = async () => {
      const [n, o, t, a] = await Promise.all([
        api.get<CHRNode[]>("/chr-nodes"),
        api.get<Overview>("/monitoring/overview"),
        api.get<IPSummary[]>("/monitoring/traffic?limit=50"),
        api.get<AlertRow[]>("/alerts?limit=20"),
      ]);
      setNodes(n);
      setOverview(o);
      setIps(t);
      setAlerts(a);
    };
    refresh();
    const id = setInterval(refresh, 15000);
    return () => clearInterval(id);
  }, []);

  // Merge WebSocket live values into the base list so cards animate without polling.
  const mergedIps = useMemo(() => {
    return ips.map((ip) => {
      const live = liveTraffic[ip.ip_address];
      if (!live) return ip;
      return {
        ...ip,
        current_bps: live.bps_in,
        baseline_bps: live.baseline_bps,
        state: live.state,
      };
    });
  }, [ips, liveTraffic]);

  const mergedAlerts = useMemo<AlertRow[]>(() => {
    const seen = new Set(alerts.map((a) => a.id));
    const live: AlertRow[] = liveAlerts
      .filter((a) => !seen.has(a.id))
      .map((a) => ({
        id: a.id,
        ip_address: a.ip,
        type: a.type,
        severity: a.severity,
        baseline_bps: a.baseline_bps,
        peak_bps: a.peak_bps,
        created_at: a.timestamp,
      }));
    return [...live, ...alerts].slice(0, 30);
  }, [alerts, liveAlerts]);

  return (
    <AppShell>
      <div className="space-y-5">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          <StatCard
            label="CHR Online"
            value={`${overview?.online_chr_nodes ?? 0}/${overview?.total_chr_nodes ?? 0}`}
          />
          <StatCard label="Monitored IPs" value={String(overview?.total_ips ?? 0)} />
          <StatCard label="Active Alerts" value={String(overview?.alert_count ?? 0)} />
          <StatCard label="Blackholed" value={String(overview?.blackhole_count ?? 0)} />
          <StatCard label="Poll Interval" value="5s" sub="EWMA span 720" />
        </div>

        <CHRHealthBar nodes={nodes} />

        <AggregateChart />

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr]">
          <IPStatusGrid rows={mergedIps} />
          <AlertFeed rows={mergedAlerts} />
        </div>
      </div>
    </AppShell>
  );
}
