"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, Cpu, Network, Bell, Settings, Radio } from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: Activity },
  { href: "/chr-nodes", label: "CHR Nodes", icon: Cpu },
  { href: "/ip-pools", label: "IP Pools", icon: Network },
  { href: "/polling", label: "Polling", icon: Radio },
  { href: "/alerts", label: "Alerts", icon: Bell },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="flex h-screen w-60 shrink-0 flex-col border-r border-bg-border bg-bg-panel">
      <div className="flex items-center gap-2 border-b border-bg-border px-5 py-4">
        <div className="h-3 w-3 rotate-45 bg-state-alert" />
        <div>
          <div className="font-semibold tracking-wide">Xiguard</div>
          <div className="text-[11px] uppercase tracking-wider text-ink-mute">DDoS Monitor</div>
        </div>
      </div>
      <nav className="flex-1 space-y-1 p-3">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active =
            pathname === href ||
            pathname.startsWith(href + "/") ||
            // /ips/<ip> is the per-IP drill-down — keep "IP Pools" lit since
            // that's where the page is reached from.
            (href === "/ip-pools" && pathname.startsWith("/ips/"));
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition",
                active
                  ? "bg-bg-elev text-ink"
                  : "text-ink-mute hover:bg-bg-elev hover:text-ink",
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
