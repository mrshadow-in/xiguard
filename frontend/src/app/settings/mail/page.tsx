"use client";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { api, APIError } from "@/lib/api";
import { cn } from "@/lib/utils";

type ConfigType = "hosting_noc" | "isp_noc";

interface MailConfig {
  id: string;
  config_type: ConfigType;
  smtp_host: string;
  smtp_port: number;
  smtp_user: string | null;
  from_address: string;
  to_addresses: string[];
  cc_addresses: string[];
  use_tls: boolean;
  enabled: boolean;
  has_password: boolean;
}

interface Form extends Omit<MailConfig, "id" | "config_type" | "to_addresses" | "cc_addresses" | "has_password"> {
  to_addresses: string;
  cc_addresses: string;
  smtp_password: string;
}

const EMPTY_FORM: Form = {
  smtp_host: "",
  smtp_port: 587,
  smtp_user: "",
  from_address: "",
  to_addresses: "",
  cc_addresses: "",
  use_tls: true,
  enabled: false,
  smtp_password: "",
};

function toForm(c: MailConfig): Form {
  return {
    smtp_host: c.smtp_host,
    smtp_port: c.smtp_port,
    smtp_user: c.smtp_user ?? "",
    from_address: c.from_address,
    to_addresses: c.to_addresses.join("\n"),
    cc_addresses: c.cc_addresses.join("\n"),
    use_tls: c.use_tls,
    enabled: c.enabled,
    smtp_password: "",
  };
}

export default function MailSettingsPage() {
  const [tab, setTab] = useState<ConfigType>("hosting_noc");
  const [configs, setConfigs] = useState<Record<ConfigType, Form>>({
    hosting_noc: EMPTY_FORM,
    isp_noc: EMPTY_FORM,
  });
  const [status, setStatus] = useState<string | null>(null);

  async function refresh() {
    const list = await api.get<MailConfig[]>("/settings/mail");
    const next = { ...configs };
    for (const c of list) next[c.config_type] = toForm(c);
    setConfigs(next);
  }

  useEffect(() => {
    refresh();
  }, []);

  const f = configs[tab];
  const setF = (patch: Partial<Form>) =>
    setConfigs({ ...configs, [tab]: { ...f, ...patch } });

  async function save() {
    setStatus("Saving…");
    try {
      const body = {
        smtp_host: f.smtp_host,
        smtp_port: f.smtp_port,
        smtp_user: f.smtp_user || null,
        from_address: f.from_address,
        to_addresses: f.to_addresses.split(/\r?\n/).map((s) => s.trim()).filter(Boolean),
        cc_addresses: f.cc_addresses.split(/\r?\n/).map((s) => s.trim()).filter(Boolean),
        use_tls: f.use_tls,
        enabled: f.enabled,
        smtp_password: f.smtp_password || null,
      };
      await api.put(`/settings/mail/${tab}`, body);
      setStatus("Saved.");
      await refresh();
    } catch (e) {
      setStatus(e instanceof APIError ? `Error ${e.status}` : "Save failed");
    }
  }

  async function sendTest() {
    setStatus("Sending test…");
    const r = await api.post<{ ok: boolean; error: string | null }>(
      `/settings/mail/${tab}/test`,
    );
    setStatus(r.ok ? "Test email sent." : `Failed: ${r.error}`);
  }

  return (
    <AppShell>
      <div className="space-y-5">
        <h1 className="text-lg font-semibold">Settings → Mail</h1>

        <div className="flex gap-1 border-b border-bg-border">
          {(["hosting_noc", "isp_noc"] as const).map((ct) => (
            <button
              key={ct}
              onClick={() => setTab(ct)}
              className={cn(
                "border-b-2 px-4 py-2 text-sm",
                tab === ct
                  ? "border-state-recover text-ink"
                  : "border-transparent text-ink-mute hover:text-ink",
              )}
            >
              {ct === "hosting_noc" ? "Hosting NOC" : "ISP NOC"}
            </button>
          ))}
        </div>

        <div className="panel space-y-4 p-5">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={f.enabled}
              onChange={(e) => setF({ enabled: e.target.checked })}
            />
            Enabled
          </label>

          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <label className="label">SMTP Host</label>
              <input
                className="input font-mono"
                value={f.smtp_host}
                onChange={(e) => setF({ smtp_host: e.target.value })}
              />
            </div>
            <div>
              <label className="label">SMTP Port</label>
              <input
                className="input font-mono"
                type="number"
                value={f.smtp_port}
                onChange={(e) => setF({ smtp_port: Number(e.target.value) })}
              />
            </div>
            <div className="flex items-end pb-1.5">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={f.use_tls}
                  onChange={(e) => setF({ use_tls: e.target.checked })}
                />
                Use STARTTLS
              </label>
            </div>
            <div>
              <label className="label">Username</label>
              <input
                className="input"
                value={f.smtp_user ?? ""}
                onChange={(e) => setF({ smtp_user: e.target.value })}
              />
            </div>
            <div>
              <label className="label">Password</label>
              <input
                className="input"
                type="password"
                placeholder="(unchanged)"
                value={f.smtp_password}
                onChange={(e) => setF({ smtp_password: e.target.value })}
              />
            </div>
            <div className="col-span-2">
              <label className="label">From Address</label>
              <input
                className="input font-mono"
                value={f.from_address}
                onChange={(e) => setF({ from_address: e.target.value })}
              />
            </div>
            <div className="col-span-2">
              <label className="label">To (one per line)</label>
              <textarea
                className="input h-24 font-mono"
                value={f.to_addresses}
                onChange={(e) => setF({ to_addresses: e.target.value })}
              />
            </div>
            <div className="col-span-2">
              <label className="label">CC (optional)</label>
              <textarea
                className="input h-16 font-mono"
                value={f.cc_addresses}
                onChange={(e) => setF({ cc_addresses: e.target.value })}
              />
            </div>
          </div>

          {status && <div className="text-sm text-ink-mute">{status}</div>}

          <div className="flex justify-end gap-2">
            <button className="btn" onClick={sendTest}>
              Send Test Email
            </button>
            <button className="btn btn-primary" onClick={save}>
              Save
            </button>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
