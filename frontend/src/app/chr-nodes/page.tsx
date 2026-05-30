"use client";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { StatusBadge } from "@/components/StatusBadge";
import { api, APIError } from "@/lib/api";
import { relTime } from "@/lib/utils";
import { Plus, Pencil, Trash2 } from "lucide-react";

interface CHRNode {
  id: string;
  name: string;
  host: string;
  api_port: number;
  username: string;
  use_ssl: boolean;
  description: string | null;
  status: string;
  last_seen_at: string | null;
  pool_count: number;
  monitored_ip_count: number;
}

interface FormState {
  id?: string;
  name: string;
  host: string;
  api_port: number;
  username: string;
  password: string;
  use_ssl: boolean;
  description: string;
}

const EMPTY: FormState = {
  name: "",
  host: "",
  api_port: 8728,
  username: "",
  password: "",
  use_ssl: false,
  description: "",
};

export default function CHRNodesPage() {
  const [rows, setRows] = useState<CHRNode[]>([]);
  const [form, setForm] = useState<FormState | null>(null);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setRows(await api.get<CHRNode[]>("/chr-nodes"));
  }

  useEffect(() => {
    refresh();
  }, []);

  function startCreate() {
    setForm({ ...EMPTY });
    setTestResult(null);
    setError(null);
  }

  function startEdit(n: CHRNode) {
    setForm({
      id: n.id,
      name: n.name,
      host: n.host,
      api_port: n.api_port,
      username: n.username,
      password: "",
      use_ssl: n.use_ssl,
      description: n.description ?? "",
    });
    setTestResult(null);
    setError(null);
  }

  async function save() {
    if (!form) return;
    setSaving(true);
    setError(null);
    try {
      if (form.id) {
        const body: Record<string, unknown> = {
          name: form.name,
          host: form.host,
          api_port: form.api_port,
          username: form.username,
          use_ssl: form.use_ssl,
          description: form.description || null,
        };
        if (form.password) body.password = form.password;
        await api.put(`/chr-nodes/${form.id}`, body);
      } else {
        await api.post("/chr-nodes", { ...form, description: form.description || null });
      }
      setForm(null);
      await refresh();
    } catch (e) {
      setError(e instanceof APIError ? `${e.status}: ${JSON.stringify(e.body)}` : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function testConnection(id: string) {
    setTestResult("Testing…");
    const res = await api.post<{
      ok: boolean;
      routeros_version: string | null;
      uptime: string | null;
      error: string | null;
    }>(`/chr-nodes/${id}/test`);
    if (res.ok) {
      setTestResult(`OK — RouterOS ${res.routeros_version}, uptime ${res.uptime}`);
    } else {
      setTestResult(`Failed: ${res.error}`);
    }
  }

  async function testBlackhole(id: string) {
    setTestResult("Testing blackhole on 192.0.2.123 (TEST-NET-1)…");
    try {
      const res = await api.post<{
        ok: boolean;
        test_ip: string;
        steps: Array<{ step: string; ok: boolean; [k: string]: unknown }>;
      }>(`/chr-nodes/${id}/test-blackhole`);
      const lines = res.steps.map(
        (s) => `${s.ok ? "✓" : "✗"} ${s.step}: ${JSON.stringify({ ...s, step: undefined, ok: undefined })}`,
      );
      setTestResult(
        (res.ok ? `Blackhole pipeline OK for ${res.test_ip}` : `BLACKHOLE PIPELINE BROKEN`) +
          "\n" +
          lines.join("\n"),
      );
    } catch (e) {
      setTestResult(`Test failed: ${String(e)}`);
    }
  }

  async function remove(id: string) {
    if (!confirm("Delete this CHR node? All its pools and IPs will be removed.")) return;
    await api.delete(`/chr-nodes/${id}`);
    await refresh();
  }

  return (
    <AppShell>
      <div className="space-y-5">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-semibold">CHR Nodes</h1>
          <button className="btn btn-primary" onClick={startCreate}>
            <Plus className="h-4 w-4" /> Add Node
          </button>
        </div>

        <div className="panel overflow-hidden">
          <table className="w-full">
            <thead className="border-b border-bg-border bg-bg-elev">
              <tr>
                <th className="table-th">Name</th>
                <th className="table-th">Host</th>
                <th className="table-th">Port</th>
                <th className="table-th">Pools</th>
                <th className="table-th">IPs</th>
                <th className="table-th">Status</th>
                <th className="table-th">Last Seen</th>
                <th className="table-th text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((n) => (
                <tr key={n.id} className="border-b border-bg-border last:border-0">
                  <td className="table-td">{n.name}</td>
                  <td className="table-td font-mono">{n.host}</td>
                  <td className="table-td font-mono">{n.api_port}</td>
                  <td className="table-td font-mono">{n.pool_count}</td>
                  <td className="table-td font-mono">{n.monitored_ip_count}</td>
                  <td className="table-td">
                    <StatusBadge state={n.status} />
                  </td>
                  <td className="table-td text-ink-mute">{relTime(n.last_seen_at)}</td>
                  <td className="table-td text-right">
                    <button
                      className="btn"
                      onClick={() => testBlackhole(n.id)}
                      title="Push, verify, remove a TEST-NET-1 blackhole route on this CHR"
                    >
                      Test BH
                    </button>{" "}
                    <button
                      className="btn"
                      onClick={() => testConnection(n.id)}
                      title="Test connection"
                    >
                      Test
                    </button>{" "}
                    <button className="btn" onClick={() => startEdit(n)}>
                      <Pencil className="h-3.5 w-3.5" />
                    </button>{" "}
                    <button className="btn btn-danger" onClick={() => remove(n.id)}>
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={8} className="table-td text-center text-ink-mute">
                    No CHR nodes yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {testResult && (
          <div className="panel p-3 font-mono text-xs whitespace-pre-wrap">
            <span className="text-ink-mute">test result:</span>
            {"\n"}
            {testResult}
          </div>
        )}

        {form && (
          <div className="panel space-y-3 p-5">
            <div className="text-sm font-semibold">
              {form.id ? "Edit CHR Node" : "Add CHR Node"}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label">Name</label>
                <input
                  className="input"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </div>
              <div>
                <label className="label">Host</label>
                <input
                  className="input font-mono"
                  value={form.host}
                  onChange={(e) => setForm({ ...form, host: e.target.value })}
                />
              </div>
              <div>
                <label className="label">API Port</label>
                <input
                  className="input font-mono"
                  type="number"
                  value={form.api_port}
                  onChange={(e) => setForm({ ...form, api_port: Number(e.target.value) })}
                />
              </div>
              <div className="flex items-end pb-1.5">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={form.use_ssl}
                    onChange={(e) => setForm({ ...form, use_ssl: e.target.checked })}
                  />
                  Use SSL (port 8729)
                </label>
              </div>
              <div>
                <label className="label">Username</label>
                <input
                  className="input"
                  value={form.username}
                  onChange={(e) => setForm({ ...form, username: e.target.value })}
                />
              </div>
              <div>
                <label className="label">Password {form.id && <span className="text-ink-dim">(leave blank to keep)</span>}</label>
                <input
                  className="input"
                  type="password"
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                />
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
              <button className="btn btn-primary" onClick={save} disabled={saving}>
                {saving ? "Saving…" : "Save Node"}
              </button>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
