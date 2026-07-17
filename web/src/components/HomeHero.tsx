"use client";

import Link from "next/link";
import { motion } from "framer-motion";

export function HomeHero() {
  return (
    <main className="relative min-h-screen overflow-hidden">
      <div className="pointer-events-none absolute inset-0">
        <motion.div
          className="absolute -right-24 top-16 h-[420px] w-[420px] rounded-full"
          style={{
            background: "radial-gradient(circle, rgba(30,200,176,0.32) 0%, transparent 68%)",
            filter: "blur(8px)",
          }}
          animate={{ scale: [1, 1.08, 1], opacity: [0.5, 0.78, 0.5] }}
          transition={{ duration: 10, repeat: Infinity, ease: "easeInOut" }}
        />
        <motion.div
          className="absolute bottom-[20%] left-[6%] h-px w-[50%] origin-left bg-gradient-to-r from-transparent via-[var(--accent)] to-transparent opacity-70"
          initial={{ scaleX: 0 }}
          animate={{ scaleX: 1 }}
          transition={{ duration: 1.35, delay: 0.3, ease: [0.22, 1, 0.36, 1] }}
        />
      </div>

      <div className="page-shell justify-end">
        <motion.p
          className="font-brand leading-[0.82] tracking-[-0.04em]"
          style={{ fontSize: "clamp(3.25rem, 12vw, 11rem)" }}
          initial={{ opacity: 0, y: 28 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
        >
          Lebne
        </motion.p>

        <motion.h1
          className="font-display max-w-[18ch] font-medium leading-[1.15]"
          style={{ marginTop: "var(--space-3)", fontSize: "clamp(1.35rem, 1rem + 2.2vw, 2.5rem)" }}
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.12, ease: [0.22, 1, 0.36, 1] }}
        >
          Put the wallet into Hassaniya.
        </motion.h1>

        <motion.p
          className="max-w-md text-[var(--muted)]"
          style={{ marginTop: "var(--space-2)", fontSize: "var(--ui-text)" }}
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.65, delay: 0.22 }}
        >
          Read each phrase. Say it the way people speak. Record it. Next.
        </motion.p>

        <motion.div
          className="flex flex-wrap items-center"
          style={{ marginTop: "var(--space-4)", gap: "var(--space-2)" }}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.32 }}
        >
          <Link href="/register" className="btn-primary">
            Start
          </Link>
          <Link href="/login" className="btn-ghost">
            Sign in
          </Link>
        </motion.div>
      </div>
    </main>
  );
}
