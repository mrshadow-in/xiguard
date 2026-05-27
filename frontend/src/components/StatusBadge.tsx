import { cn } from "@/lib/utils";

const STYLES: Record<string, string> = {
  NORMAL: "text-state-normal border-state-normal/40 bg-state-normal/10",
  ALERT: "text-state-alert border-state-alert/40 bg-state-alert/10 animate-pulse-alert",
  BLACKHOLED: "text-state-blackhole border-state-blackhole/40 bg-state-blackhole/15",
  RECOVERING: "text-state-recover border-state-recover/40 bg-state-recover/10",
  online: "text-state-normal border-state-normal/40 bg-state-normal/10",
  offline: "text-state-offline border-state-offline/40 bg-state-offline/15",
  unknown: "text-ink-mute border-bg-border bg-bg-elev",
};

export function StatusBadge({ state }: { state: string }) {
  const cls = STYLES[state] ?? STYLES.unknown;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 font-mono text-[11px] font-semibold uppercase",
        cls,
      )}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {state}
    </span>
  );
}
