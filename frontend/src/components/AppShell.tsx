"use client";
import { AuthGuard } from "@/components/AuthGuard";
import { Sidebar } from "@/components/Sidebar";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useAlertStore } from "@/stores/alertStore";

function StatusBar() {
  const { connected } = useWebSocket();
  const alertCount = useAlertStore((s) => s.recent.filter((a) => a.severity !== "info").length);
  return (
    <div className="flex items-center justify-between border-b border-bg-border bg-bg-panel px-5 py-2 text-xs">
      <div className="flex items-center gap-4">
        <span className="flex items-center gap-2">
          <span
            className={`h-2 w-2 rounded-full ${connected ? "bg-state-normal" : "bg-state-offline"}`}
          />
          {connected ? "Live" : "Reconnecting"}
        </span>
        {alertCount > 0 && (
          <span className="text-state-alert">{alertCount} active alerts</span>
        )}
      </div>
      <div className="text-ink-mute">admin</div>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <div className="flex h-screen">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <StatusBar />
          <main className="flex-1 overflow-y-auto p-6">{children}</main>
        </div>
      </div>
    </AuthGuard>
  );
}
