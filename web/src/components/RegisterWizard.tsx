"use client";

import { motion, AnimatePresence } from "framer-motion";
import { useRouter } from "next/navigation";
import { useState } from "react";

const steps = ["name", "email", "password"] as const;

export function RegisterWizard() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function finish() {
    setLoading(true);
    setError("");
    const res = await fetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, email, password }),
    });
    const data = await res.json().catch(() => ({}));
    setLoading(false);
    if (!res.ok) {
      setError(data.error || "Could not create account");
      return;
    }
    router.push("/contribute");
    router.refresh();
  }

  function next() {
    setError("");
    if (step === 0 && name.trim().length < 2) {
      setError("Enter your name");
      return;
    }
    if (step === 1 && !email.includes("@")) {
      setError("Enter a valid email");
      return;
    }
    if (step === 2) {
      if (password.length < 8) {
        setError("Use at least 8 characters");
        return;
      }
      void finish();
      return;
    }
    setStep((s) => s + 1);
  }

  return (
    <div className="glass w-full rounded-[28px] p-7 sm:p-9">
      <div className="mb-7 flex gap-2">
        {steps.map((s, i) => (
          <div
            key={s}
            className={`h-1 flex-1 rounded-full ${i <= step ? "bg-[var(--accent)]" : "bg-white/10"}`}
          />
        ))}
      </div>

      <AnimatePresence mode="wait">
        <motion.div
          key={step}
          initial={{ opacity: 0, x: 16 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -16 }}
          transition={{ duration: 0.22 }}
        >
          {step === 0 && (
            <>
              <h2 className="font-display text-3xl">Your name</h2>
              <input
                className="field-input mt-6"
                autoFocus
                placeholder="Name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && next()}
              />
            </>
          )}
          {step === 1 && (
            <>
              <h2 className="font-display text-3xl">Email</h2>
              <input
                className="field-input mt-6"
                autoFocus
                type="email"
                placeholder="you@email.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && next()}
              />
            </>
          )}
          {step === 2 && (
            <>
              <h2 className="font-display text-3xl">Password</h2>
              <input
                className="field-input mt-6"
                autoFocus
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && next()}
              />
            </>
          )}
        </motion.div>
      </AnimatePresence>

      {error && <p className="mt-4 text-sm font-medium text-[#ff8f6b]">{error}</p>}

      <div className="mt-8 flex gap-3">
        {step > 0 && (
          <button type="button" className="btn-ghost" onClick={() => setStep((s) => s - 1)} disabled={loading}>
            Back
          </button>
        )}
        <button type="button" className="btn-primary flex-1" onClick={next} disabled={loading}>
          {loading ? "…" : step === 2 ? "Create account" : "Continue"}
        </button>
      </div>
    </div>
  );
}
