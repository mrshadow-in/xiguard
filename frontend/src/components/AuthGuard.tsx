"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, APIError } from "@/lib/api";

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [state, setState] = useState<"checking" | "ok">("checking");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await api.get<{ username: string }>("/auth/me");
        if (!cancelled) setState("ok");
      } catch (e) {
        if (e instanceof APIError && e.status === 401) {
          router.replace("/login");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [router]);

  if (state === "checking") {
    return (
      <div className="flex h-screen items-center justify-center text-ink-mute">Loading…</div>
    );
  }
  return <>{children}</>;
}
