"use client";

import { useEffect, useRef } from "react";

const IDLE_MS = Number(process.env.NEXT_PUBLIC_CROWD_IDLE_SECONDS || 600) * 1000;

/**
 * Client watchdog: if the tab was hidden / unfocused longer than the idle
 * window, force logout when the user returns (covers no BFF traffic).
 */
export function IdleGuard() {
  const hiddenAtRef = useRef<number | null>(null);

  useEffect(() => {
    function markHidden() {
      if (document.visibilityState === "hidden") {
        hiddenAtRef.current = Date.now();
      }
    }

    async function maybeExpire() {
      const started = hiddenAtRef.current;
      hiddenAtRef.current = null;
      if (started == null) return;
      if (Date.now() - started <= IDLE_MS) return;
      try {
        await fetch("/api/auth/logout", { method: "POST" });
      } catch {
        /* ignore */
      }
      window.location.href = "/login";
    }

    function onVisibility() {
      if (document.visibilityState === "hidden") markHidden();
      else void maybeExpire();
    }

    function onBlur() {
      hiddenAtRef.current = Date.now();
    }

    function onFocus() {
      void maybeExpire();
    }

    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("blur", onBlur);
    window.addEventListener("focus", onFocus);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("blur", onBlur);
      window.removeEventListener("focus", onFocus);
    };
  }, []);

  return null;
}
