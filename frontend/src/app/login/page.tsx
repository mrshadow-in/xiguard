"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, APIError } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await api.post("/auth/login", { username, password });
      router.replace("/dashboard");
    } catch (e) {
      if (e instanceof APIError && e.status === 401) setError("Invalid credentials");
      else setError("Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg">
      <form onSubmit={onSubmit} className="panel w-[360px] space-y-5 p-7">
        <div className="space-y-1 text-center">
          <div className="mx-auto h-4 w-4 rotate-45 bg-state-alert" />
          <div className="text-lg font-semibold">Xiguard</div>
          <div className="text-xs text-ink-mute">MikroTik DDoS Monitoring</div>
        </div>
        <div>
          <label className="label">Username</label>
          <input
            className="input"
            autoFocus
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
        </div>
        <div>
          <label className="label">Password</label>
          <input
            className="input"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        {error && <div className="text-sm text-state-blackhole">{error}</div>}
        <button className="btn btn-primary w-full" disabled={loading} type="submit">
          {loading ? "Signing in…" : "Sign In"}
        </button>
      </form>
    </div>
  );
}
