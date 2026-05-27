"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { api } from "@/lib/api";

interface Settings {
  default_multiplier: number;
  default_eval_window_sec: number;
  default_blackhole_duration_sec: number;
  baseline_ewma_span: number;
  alert_dedup_window_sec: number;
  poll_interval_sec: number;
  traffic_retention_days: number;
  alert_retention_days: number;
  audit_retention_days: number;
  org_name: string;
  org_as_number: number;
}

export default function SettingsPage() {
  const [s, setS] = useState<Settings | null>(null);
  useEffect(() => {
    api.get<Settings>("/settings/general").then(setS);
  }, []);

  return (
    <AppShell>
      <div className="space-y-5">
        <h1 className="text-lg font-semibold">Settings</h1>

        <div className="panel p-5">
          <div className="mb-3 text-sm font-semibold">Mail Configuration</div>
          <Link className="btn btn-primary" href="/settings/mail">
            Configure SMTP for Hosting NOC + ISP NOC →
          </Link>
        </div>

        <div className="panel p-5">
          <div className="mb-3 text-sm font-semibold">
            General Defaults <span className="text-ink-mute">(read-only — set via .env)</span>
          </div>
          {s ? (
            <div className="grid grid-cols-2 gap-x-8 gap-y-2 font-mono text-sm">
              <Row k="Default multiplier" v={`${s.default_multiplier}×`} />
              <Row k="Default eval window" v={`${s.default_eval_window_sec}s`} />
              <Row k="Blackhole duration" v={`${s.default_blackhole_duration_sec}s`} />
              <Row k="Baseline EWMA span" v={`${s.baseline_ewma_span} samples`} />
              <Row k="Alert dedup window" v={`${s.alert_dedup_window_sec}s`} />
              <Row k="Poll interval" v={`${s.poll_interval_sec}s`} />
              <Row k="Traffic retention" v={`${s.traffic_retention_days} days`} />
              <Row k="Alert retention" v={`${s.alert_retention_days} days`} />
              <Row k="Audit retention" v={`${s.audit_retention_days} days`} />
              <Row k="Organization" v={s.org_name} />
              <Row k="AS number" v={`AS${s.org_as_number}`} />
            </div>
          ) : (
            <div className="text-ink-mute">Loading…</div>
          )}
        </div>
      </div>
    </AppShell>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <>
      <div className="text-ink-mute">{k}</div>
      <div>{v}</div>
    </>
  );
}
