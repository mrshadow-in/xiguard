"use client";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AppShell } from "@/components/AppShell";
import { StatusBadge } from "@/components/StatusBadge";
import { api } from "@/lib/api";
import { humanBps, humanPps, relTime } from "@/lib/utils";
import { useTrafficStore } from "@/stores/trafficStore";

interface Point {
  sampled_at: string;
  bps_in: number;
  bps_out: number;
  pps_in: number;
  pps_out: number;
}
interface History {
  ip_id: string;
  ip_address: string;
  state: string;
  baseline_bps: number;
  current_bps: number;
  pool_cidr: string | null;
  chr_name: string | null;
  chr_id: string | null;
  blackholed_at: string | null;
  last_spike_at: string | null;
  points: Point[];
}

const RANGES: { label: string; hours: number }[] = [
  { label: "15 min", hours: 1 },
  { label: "1 hour", hours: 1 },
  { label: "6 hours", hours: 6 },
  { label: "24 hours", hours: 24 },
  { label: "7 days", hours: 24 * 7 },
];

function Stat({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: string;
  sub?: string;
  color?: string;
}) {
  return (
    <div className="panel p-4">
      <div className="text-[11px] uppercase tracking-wider text-ink-mute">{label}</div>
      <div className={`mt-1 font-mono text-2xl ${color ?? "text-ink"}`}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-ink-mute">{sub}</div>}
    </div>
  );
}

export default function IPDetailPage() {
  const params = useParams<{ ip: string }>();
  const ip = decodeURIComponent(params.ip);
  const [hours, setHours] = useState(1);
  const [data, setData] = useState<History | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const live = useTrafficStore((s) => s.byIp[ip]);

  useEffect(() => {
    let alive = true;
    const refresh = async () => {
      try {
        const h = await api.get<History>(`/monitoring/traffic/${ip}?hours=${hours}`);
        if (alive) setData(h);
      } catch (e) {
        if (alive) setErr(String(e));
      }
    };
    refresh();
    const i = setInterval(refresh, 5000);
    return () => {
      alive = false;
      clearInterval(i);
    };
  }, [ip, hours]);

  const chartData = useMemo(() => {
    if (!data) return [];
    const baseline = live?.baseline_bps ?? data.baseline_bps;
    return data.points.map((p) => ({
      t: new Date(p.sampled_at).getTime(),
      bps_in: p.bps_in,
      bps_out: p.bps_out,
      pps_in: p.pps_in,
      pps_out: p.pps_out,
      baseline,
    }));
  }, [data, live?.baseline_bps]);

  const currentBpsIn = live?.bps_in ?? data?.current_bps ?? 0;
  const currentBpsOut = live?.bps_out ?? 0;
  const currentPpsIn = live?.pps_in ?? 0;
  const baseline = live?.baseline_bps ?? data?.baseline_bps ?? 0;
  const state = live?.state ?? data?.state ?? "NORMAL";
  const ratio = baseline > 0 ? currentBpsIn / baseline : 0;

  async function action(verb: "blackhole" | "unblackhole") {
    if (!confirm(`${verb} ${ip}?`)) return;
    await api.post(`/actions/${verb}`, { ip });
  }

  return (
    <AppShell>
      <div className="space-y-5">
        <div className="flex items-baseline justify-between">
          <div>
            <div className="text-xs text-ink-mute">
              {data?.pool_cidr && (
                <>
                  <Link
                    href="/ip-pools"
                    className="hover:text-ink"
                  >
                    IP Pools
                  </Link>{" "}
                  · <span className="font-mono">{data.pool_cidr}</span>{" "}
                  · {data.chr_name ?? "—"}
                </>
              )}
            </div>
            <h1 className="font-mono text-2xl font-semibold">{ip}</h1>
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge state={state} />
            {state === "BLACKHOLED" ? (
              <button className="btn" onClick={() => action("unblackhole")}>
                Unblackhole
              </button>
            ) : (
              <button className="btn btn-danger" onClick={() => action("blackhole")}>
                Blackhole
              </button>
            )}
          </div>
        </div>

        {err && <div className="panel p-3 text-sm text-state-blackhole">{err}</div>}

        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          <Stat
            label="Current In"
            value={humanBps(currentBpsIn)}
            sub={humanPps(currentPpsIn)}
            color={ratio >= 3 ? "text-state-alert" : "text-state-normal"}
          />
          <Stat label="Current Out" value={humanBps(currentBpsOut)} />
          <Stat label="Baseline" value={humanBps(baseline)} />
          <Stat
            label="× Baseline"
            value={ratio > 0 ? `${ratio.toFixed(2)}×` : "—"}
            color={ratio >= 3 ? "text-state-blackhole" : undefined}
          />
          <Stat
            label="Last Spike"
            value={data?.last_spike_at ? relTime(data.last_spike_at) : "never"}
            sub={data?.blackholed_at ? `BH ${relTime(data.blackholed_at)}` : undefined}
          />
        </div>

        <div className="panel p-4">
          <div className="mb-3 flex items-center justify-between">
            <div className="text-sm font-semibold">Traffic over time</div>
            <div className="flex items-center gap-1 text-xs">
              {RANGES.map((r) => (
                <button
                  key={r.label + r.hours}
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
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="ip-in" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.5} />
                    <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="ip-out" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#22c55e" stopOpacity={0.35} />
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
                  formatter={(v: number, name: string) =>
                    name.startsWith("pps") ? humanPps(v) : humanBps(v)
                  }
                  contentStyle={{
                    backgroundColor: "#11161d",
                    border: "1px solid #1f2733",
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Area
                  type="monotone"
                  dataKey="bps_in"
                  stroke="#3b82f6"
                  fill="url(#ip-in)"
                  name="Inbound"
                />
                <Area
                  type="monotone"
                  dataKey="bps_out"
                  stroke="#22c55e"
                  fill="url(#ip-out)"
                  name="Outbound"
                />
                <Line
                  type="monotone"
                  dataKey="baseline"
                  stroke="#f59e0b"
                  strokeDasharray="4 4"
                  dot={false}
                  name="Baseline"
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 flex justify-between text-[11px] text-ink-mute">
            <span>{chartData.length} samples</span>
            <span>Auto-refresh every 5s · WebSocket live overlay</span>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
