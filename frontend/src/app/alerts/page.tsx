"use client";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { api } from "@/lib/api";
import { humanBps, relTime } from "@/lib/utils";

interface AlertRow {
  id: string;
  ip_address: string | null;
  pool_cidr: string | null;
  chr_name: string | null;
  type: string;
  severity: string;
  baseline_bps: number | null;
  peak_bps: number | null;
  action_taken: string | null;
  hosting_email_sent: boolean;
  isp_email_sent: boolean;
  acknowledged: boolean;
  acknowledged_by: string | null;
  created_at: string;
}

interface Stats {
  total_24h: number;
  critical_24h: number;
  warning_24h: number;
  info_24h: number;
}

export default function AlertsPage() {
  const [rows, setRows] = useState<AlertRow[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [severity, setSeverity] = useState("");
  const [ipFilter, setIpFilter] = useState("");
  const [selected, setSelected] = useState<AlertRow | null>(null);

  async function refresh() {
    const qs = new URLSearchParams();
    if (severity) qs.set("severity", severity);
    if (ipFilter) qs.set("ip", ipFilter);
    qs.set("limit", "100");
    const [list, s] = await Promise.all([
      api.get<AlertRow[]>(`/alerts?${qs.toString()}`),
      api.get<Stats>("/alerts/stats"),
    ]);
    setRows(list);
    setStats(s);
  }

  useEffect(() => {
    refresh();
  }, [severity, ipFilter]);

  async function ack(id: string) {
    await api.post(`/alerts/${id}/acknowledge`);
    await refresh();
  }

  return (
    <AppShell>
      <div className="space-y-5">
        <h1 className="text-lg font-semibold">Alerts</h1>

        <div className="grid grid-cols-4 gap-3">
          <Stat label="Total (24h)" value={stats?.total_24h ?? 0} />
          <Stat label="Critical" value={stats?.critical_24h ?? 0} color="text-state-blackhole" />
          <Stat label="Warning" value={stats?.warning_24h ?? 0} color="text-state-alert" />
          <Stat label="Info" value={stats?.info_24h ?? 0} color="text-state-recover" />
        </div>

        <div className="panel flex flex-wrap items-end gap-3 p-4">
          <div>
            <label className="label">Severity</label>
            <select
              className="input"
              value={severity}
              onChange={(e) => setSeverity(e.target.value)}
            >
              <option value="">All</option>
              <option value="critical">Critical</option>
              <option value="warning">Warning</option>
              <option value="info">Info</option>
            </select>
          </div>
          <div className="flex-1 min-w-[180px]">
            <label className="label">IP</label>
            <input
              className="input font-mono"
              placeholder="162.141.0.15"
              value={ipFilter}
              onChange={(e) => setIpFilter(e.target.value)}
            />
          </div>
          <button
            className="btn"
            onClick={() => {
              setSeverity("");
              setIpFilter("");
            }}
          >
            Reset
          </button>
        </div>

        <div className="panel overflow-hidden">
          <table className="w-full">
            <thead className="border-b border-bg-border bg-bg-elev">
              <tr>
                <th className="table-th">Time</th>
                <th className="table-th">Sev</th>
                <th className="table-th">IP</th>
                <th className="table-th">Pool</th>
                <th className="table-th">Type</th>
                <th className="table-th">Action</th>
                <th className="table-th">Emails</th>
                <th className="table-th text-right"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((a) => (
                <tr
                  key={a.id}
                  className="cursor-pointer border-b border-bg-border last:border-0 hover:bg-bg-elev"
                  onClick={() => setSelected(a)}
                >
                  <td className="table-td font-mono">{relTime(a.created_at)}</td>
                  <td className="table-td">
                    <span
                      className={
                        a.severity === "critical"
                          ? "text-state-blackhole"
                          : a.severity === "warning"
                            ? "text-state-alert"
                            : "text-ink-mute"
                      }
                    >
                      {a.severity}
                    </span>
                  </td>
                  <td className="table-td font-mono">{a.ip_address ?? "—"}</td>
                  <td className="table-td font-mono">{a.pool_cidr ?? "—"}</td>
                  <td className="table-td">{a.type.replace("_", " ")}</td>
                  <td className="table-td text-ink-mute">{a.action_taken ?? "—"}</td>
                  <td className="table-td font-mono text-xs">
                    H{a.hosting_email_sent ? "✓" : "—"} I{a.isp_email_sent ? "✓" : "—"}
                  </td>
                  <td className="table-td text-right" onClick={(e) => e.stopPropagation()}>
                    {!a.acknowledged && (
                      <button className="btn" onClick={() => ack(a.id)}>
                        ACK
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={8} className="table-td text-center text-ink-mute">
                    No alerts match.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {selected && (
          <div className="panel space-y-2 p-5">
            <div className="text-sm font-semibold">Alert Detail</div>
            <div className="grid grid-cols-2 gap-2 font-mono text-sm">
              <div className="text-ink-mute">ID</div>
              <div>{selected.id}</div>
              <div className="text-ink-mute">IP</div>
              <div>{selected.ip_address ?? "—"}</div>
              <div className="text-ink-mute">Pool</div>
              <div>{selected.pool_cidr ?? "—"}</div>
              <div className="text-ink-mute">CHR</div>
              <div>{selected.chr_name ?? "—"}</div>
              <div className="text-ink-mute">Baseline</div>
              <div>{selected.baseline_bps ? humanBps(selected.baseline_bps) : "—"}</div>
              <div className="text-ink-mute">Peak</div>
              <div>{selected.peak_bps ? humanBps(selected.peak_bps) : "—"}</div>
              <div className="text-ink-mute">Action</div>
              <div>{selected.action_taken ?? "—"}</div>
              <div className="text-ink-mute">Hosting NOC email</div>
              <div>{selected.hosting_email_sent ? "sent" : "—"}</div>
              <div className="text-ink-mute">ISP NOC email</div>
              <div>{selected.isp_email_sent ? "sent" : "—"}</div>
              <div className="text-ink-mute">Acknowledged</div>
              <div>
                {selected.acknowledged
                  ? `by ${selected.acknowledged_by ?? "—"}`
                  : "no"}
              </div>
            </div>
            <div className="text-right">
              <button className="btn" onClick={() => setSelected(null)}>
                Close
              </button>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}

function Stat({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color?: string;
}) {
  return (
    <div className="panel p-4">
      <div className="text-xs uppercase tracking-wider text-ink-mute">{label}</div>
      <div className={`mt-1 font-mono text-2xl ${color ?? ""}`}>{value}</div>
    </div>
  );
}
