"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function LoginForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json().catch(() => ({}));
    setLoading(false);
    if (!res.ok) {
      setError(data.error || "Wrong email or password");
      return;
    }
    router.push("/contribute");
    router.refresh();
  }

  return (
    <form onSubmit={onSubmit} className="glass w-full rounded-[28px] p-7 sm:p-9">
      <h2 className="font-display text-3xl">Sign in</h2>
      <label className="mt-7 block text-sm font-semibold text-[var(--muted)]">Email</label>
      <input
        className="field-input mt-2"
        type="email"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
      />
      <label className="mt-4 block text-sm font-semibold text-[var(--muted)]">Password</label>
      <input
        className="field-input mt-2"
        type="password"
        required
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      {error && <p className="mt-4 text-sm font-medium text-[#ff8f6b]">{error}</p>}
      <button type="submit" className="btn-primary mt-8 w-full" disabled={loading}>
        {loading ? "…" : "Continue"}
      </button>
    </form>
  );
}
