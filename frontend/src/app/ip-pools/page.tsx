"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { api, APIError } from "@/lib/api";
import { Plus, ChevronRight, Trash2 } from "lucide-react";

interface CHRNode {
  id: string;
  name: string;
}
interface Pool {
  id: string;
  cidr: string;
  chr_node_id: string;
  description: string | null;
  multiplier: number;
  eval_window_sec: number;
  auto_blackhole: boolean;
  blackhole_duration_sec: number;
  ip_count: number;
  alert_count: number;
  blackhole_count: number;
}

interface FormState {
  cidr: string;
  chr_node_id: string;
  description: string;
  multiplier: number;
  eval_window_sec: number;
  auto_blackhole: boolean;
  blackhole_duration_sec: number;
}

const EMPTY: FormState = {
  cidr: "",
  chr_node_id: "",
  description: "",
  multiplier: 3.0,
  eval_window_sec: 30,
  auto_blackhole: true,
  blackhole_duration_sec: 600,
};

export default function IPPoolsPage() {
  const [nodes, setNodes] = useState<CHRNode[]>([]);
  const [pools, setPools] = useState<Pool[]>([]);
  const [form, setForm] = useState<FormState | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    const [n, p] = await Promise.all([
      api.get<CHRNode[]>("/chr-nodes"),
      api.get<Pool[]>("/ip-pools"),
    ]);
    setNodes(n);
    setPools(p);
  }

  useEffect(() => {
    refresh();
  }, []);

  function startCreate() {
    setForm({ ...EMPTY, chr_node_id: nodes[0]?.id ?? "" });
    setError(null);
  }

  async function save() {
    if (!form) return;
    setError(null);
    try {
      await api.post("/ip-pools", form);
      setForm(null);
      await refresh();
    } catch (e) {
      setError(e instanceof APIError ? `${e.status}: ${JSON.stringify(e.body)}` : "Save failed");
    }
  }

  async function remove(id: string) {
    if (!confirm("Delete pool and all its monitored IPs?")) return;
    await api.delete(`/ip-pools/${id}`);
    await refresh();
  }

  return (
    <AppShell>
      <div className="space-y-5">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-semibold">IP Pools</h1>
          <button className="btn btn-primary" onClick={startCreate} disabled={nodes.length === 0}>
            <Plus className="h-4 w-4" /> Add Pool
          </button>
        </div>

        {nodes.length === 0 && (
          <div className="panel p-4 text-sm text-ink-mute">
            Add a CHR node first before creating pools.
          </div>
        )}

        <div className="panel overflow-hidden">
          <table className="w-full">
            <thead className="border-b border-bg-border bg-bg-elev">
              <tr>
                <th className="table-th">CIDR</th>
                <th className="table-th">CHR</th>
                <th className="table-th">IPs</th>
                <th className="table-th">Multi</th>
                <th className="table-th">Window</th>
                <th className="table-th">Auto-BH</th>
                <th className="table-th">Alerts</th>
                <th className="table-th text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {pools.map((p) => {
                const node = nodes.find((n) => n.id === p.chr_node_id);
                return (
                  <tr key={p.id} className="border-b border-bg-border last:border-0">
                    <td className="table-td font-mono">{p.cidr}</td>
                    <td className="table-td">{node?.name ?? "—"}</td>
                    <td className="table-td font-mono">{p.ip_count}</td>
                    <td className="table-td font-mono">{p.multiplier.toFixed(1)}×</td>
                    <td className="table-td font-mono">{p.eval_window_sec}s</td>
                    <td className="table-td">{p.auto_blackhole ? "✓" : "—"}</td>
                    <td className="table-td font-mono">
                      <span className="text-state-alert">{p.alert_count}A</span>{" "}
                      <span className="text-state-blackhole">{p.blackhole_count}B</span>
                    </td>
                    <td className="table-td text-right">
                      <Link className="btn" href={`/ip-pools/${p.id}`}>
                        <ChevronRight className="h-3.5 w-3.5" />
                      </Link>{" "}
                      <button className="btn btn-danger" onClick={() => remove(p.id)}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </td>
                  </tr>
                );
              })}
              {pools.length === 0 && (
                <tr>
                  <td colSpan={8} className="table-td text-center text-ink-mute">
                    No pools yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {form && (
          <div className="panel space-y-3 p-5">
            <div className="text-sm font-semibold">Add IP Pool</div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label">CIDR</label>
                <input
                  className="input font-mono"
                  placeholder="162.141.0.0/24"
                  value={form.cidr}
                  onChange={(e) => setForm({ ...form, cidr: e.target.value })}
                />
              </div>
              <div>
                <label className="label">CHR Node</label>
                <select
                  className="input"
                  value={form.chr_node_id}
                  onChange={(e) => setForm({ ...form, chr_node_id: e.target.value })}
                >
                  {nodes.map((n) => (
                    <option key={n.id} value={n.id}>
                      {n.name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="label">Multiplier</label>
                <input
                  className="input font-mono"
                  type="number"
                  step="0.1"
                  value={form.multiplier}
                  onChange={(e) => setForm({ ...form, multiplier: Number(e.target.value) })}
                />
              </div>
              <div>
                <label className="label">Eval Window (sec)</label>
                <input
                  className="input font-mono"
                  type="number"
                  value={form.eval_window_sec}
                  onChange={(e) => setForm({ ...form, eval_window_sec: Number(e.target.value) })}
                />
              </div>
              <div>
                <label className="label">Blackhole Duration (sec)</label>
                <input
                  className="input font-mono"
                  type="number"
                  value={form.blackhole_duration_sec}
                  onChange={(e) =>
                    setForm({ ...form, blackhole_duration_sec: Number(e.target.value) })
                  }
                />
              </div>
              <div className="flex items-end pb-1.5">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={form.auto_blackhole}
                    onChange={(e) => setForm({ ...form, auto_blackhole: e.target.checked })}
                  />
                  Auto-blackhole on detection
                </label>
              </div>
              <div className="col-span-2">
                <label className="label">Description</label>
                <input
                  className="input"
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                />
              </div>
            </div>
            {error && <div className="text-sm text-state-blackhole">{error}</div>}
            <div className="flex justify-end gap-2">
              <button className="btn" onClick={() => setForm(null)}>
                Cancel
              </button>
              <button className="btn btn-primary" onClick={save}>
                Save Pool
              </button>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
