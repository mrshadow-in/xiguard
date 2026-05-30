"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { StatusBadge } from "@/components/StatusBadge";
import { api } from "@/lib/api";
import { humanBps } from "@/lib/utils";

interface Pool {
  id: string;
  cidr: string;
  multiplier: number;
  eval_window_sec: number;
  auto_blackhole: boolean;
  blackhole_duration_sec: number;
  ip_count: number;
  alert_count: number;
  blackhole_count: number;
}

interface IPRow {
  id: string;
  ip_address: string;
  state: string;
  baseline_bps: number;
  current_bps: number;
}

export default function PoolDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [pool, setPool] = useState<Pool | null>(null);
  const [ips, setIps] = useState<IPRow[]>([]);
  const [filter, setFilter] = useState<string>("");
  const [syncing, setSyncing] = useState(false);

  async function refresh() {
    const [p, list] = await Promise.all([
      api.get<Pool>(`/ip-pools/${id}`),
      api.get<IPRow[]>(`/ip-pools/${id}/ips${filter ? `?state=${filter}` : ""}`),
    ]);
    setPool(p);
    setIps(list);
  }

  useEffect(() => {
    refresh();
    const i = setInterval(refresh, 10_000);
    return () => clearInterval(i);
  }, [id, filter]);

  async function action(verb: "blackhole" | "unblackhole", ip: string) {
    if (!confirm(`${verb} ${ip}?`)) return;
    await api.post(`/actions/${verb}`, { ip });
    await refresh();
  }

  async function resync() {
    setSyncing(true);
    try {
      await api.post(`/ip-pools/${id}/sync`);
      await refresh();
    } finally {
      setSyncing(false);
    }
  }

  if (!pool) return <AppShell><div className="text-ink-mute">Loading…</div></AppShell>;

  return (
    <AppShell>
      <div className="space-y-5">
        <div>
          <h1 className="text-lg font-semibold font-mono">{pool.cidr}</h1>
          <div className="text-xs text-ink-mute">
            multiplier {pool.multiplier}× · eval {pool.eval_window_sec}s · auto-BH{" "}
            {pool.auto_blackhole ? "on" : "off"} · BH duration {pool.blackhole_duration_sec}s
          </div>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div className="panel p-4">
            <div className="text-xs uppercase tracking-wider text-ink-mute">Total IPs</div>
            <div className="mt-1 font-mono text-2xl">{pool.ip_count}</div>
          </div>
          <div className="panel p-4">
            <div className="text-xs uppercase tracking-wider text-ink-mute">Alerting</div>
            <div className="mt-1 font-mono text-2xl text-state-alert">{pool.alert_count}</div>
          </div>
          <div className="panel p-4">
            <div className="text-xs uppercase tracking-wider text-ink-mute">Blackholed</div>
            <div className="mt-1 font-mono text-2xl text-state-blackhole">
              {pool.blackhole_count}
            </div>
          </div>
        </div>

        <div className="flex items-center justify-between">
          <select
            className="input max-w-xs"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            <option value="">All states</option>
            <option value="NORMAL">NORMAL</option>
            <option value="ALERT">ALERT</option>
            <option value="BLACKHOLED">BLACKHOLED</option>
            <option value="RECOVERING">RECOVERING</option>
          </select>
          <button className="btn" onClick={resync} disabled={syncing}>
            {syncing ? "Syncing…" : "Re-sync IPs from CIDR"}
          </button>
        </div>

        <div className="panel overflow-hidden">
          <table className="w-full">
            <thead className="border-b border-bg-border bg-bg-elev">
              <tr>
                <th className="table-th">IP Address</th>
                <th className="table-th">State</th>
                <th className="table-th">Current</th>
                <th className="table-th">Baseline</th>
                <th className="table-th">Multi</th>
                <th className="table-th text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {ips.map((ip) => {
                const ratio = ip.baseline_bps > 0 ? ip.current_bps / ip.baseline_bps : 0;
                return (
                  <tr key={ip.id} className="border-b border-bg-border last:border-0">
                    <td className="table-td font-mono">
                      <Link
                        href={`/ips/${encodeURIComponent(ip.ip_address)}`}
                        className="text-state-recover hover:underline"
                      >
                        {ip.ip_address}
                      </Link>
                    </td>
                    <td className="table-td">
                      <StatusBadge state={ip.state} />
                    </td>
                    <td className="table-td font-mono">{humanBps(ip.current_bps)}</td>
                    <td className="table-td font-mono">{humanBps(ip.baseline_bps)}</td>
                    <td className="table-td font-mono">
                      {ratio > 0 ? `${ratio.toFixed(1)}×` : "—"}
                    </td>
                    <td className="table-td text-right">
                      {ip.state === "BLACKHOLED" ? (
                        <button
                          className="btn"
                          onClick={() => action("unblackhole", ip.ip_address)}
                        >
                          Unblackhole
                        </button>
                      ) : (
                        <button
                          className="btn btn-danger"
                          onClick={() => action("blackhole", ip.ip_address)}
                        >
                          Blackhole
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
              {ips.length === 0 && (
                <tr>
                  <td colSpan={6} className="table-td text-center text-ink-mute">
                    No IPs match.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </AppShell>
  );
}
