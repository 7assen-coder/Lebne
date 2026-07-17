"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useRef, useState } from "react";
import { IdleGuard } from "./IdleGuard";
import { ProgressRing } from "./ProgressRing";
import { VoiceRecorder, type VoiceRecorderHandle } from "./VoiceRecorder";

const VIEW_LOCALES = ["fr", "ar", "en"] as const;

type Prompt = {
  id: number;
  intent: string;
  sourceLocale: string;
  view: string;
  text: string;
};

type Progress = { done: number; total: number; percent: number };

export function ContributeClient({
  userName,
  isReviewer,
}: {
  userName: string;
  isReviewer: boolean;
}) {
  const [viewLocale, setViewLocale] = useState<(typeof VIEW_LOCALES)[number]>("fr");
  const [prompt, setPrompt] = useState<Prompt | null>(null);
  const [progress, setProgress] = useState<Progress>({ done: 0, total: 0, percent: 0 });
  const [hassaniya, setHassaniya] = useState("");
  const [audioId, setAudioId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [viewLoading, setViewLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [doneAll, setDoneAll] = useState(false);
  const [voiceBusy, setVoiceBusy] = useState(false);
  const [error, setError] = useState("");
  const voiceRef = useRef<VoiceRecorderHandle | null>(null);

  const canSubmit = hassaniya.trim().length >= 2 || Boolean(audioId);
  const voiceLocked = voiceBusy;

  const loadNext = useCallback(async (view: string) => {
    setLoading(true);
    setHassaniya("");
    setAudioId(null);
    setError("");
    const res = await fetch(`/api/contribute/next?view=${view}`);
    const data = await res.json();
    setLoading(false);
    if (!res.ok) return;
    setProgress(data.progress);
    setPrompt(data.prompt);
    setDoneAll(Boolean(data.done));
  }, []);

  useEffect(() => {
    void loadNext(viewLocale);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function switchView(loc: (typeof VIEW_LOCALES)[number]) {
    if (loc === viewLocale && prompt) return;
    setViewLocale(loc);
    if (!prompt) {
      await loadNext(loc);
      return;
    }
    setViewLoading(true);
    const res = await fetch(`/api/contribute/view?promptId=${prompt.id}&view=${loc}`);
    const data = await res.json();
    setViewLoading(false);
    if (res.ok && data.prompt) setPrompt(data.prompt);
  }

  async function submit() {
    if (!prompt || saving) return;
    setSaving(true);
    setError("");

    let nextAudioId = audioId;
    const recorder = voiceRef.current;
    if (recorder && (recorder.recording || recorder.busy)) {
      nextAudioId = await recorder.stopAndFlush();
      if (nextAudioId) setAudioId(nextAudioId);
    }

    const text = hassaniya.trim();
    if (text.length < 2 && !nextAudioId) {
      setError("Type Hassaniya or finish recording before Next");
      setSaving(false);
      return;
    }

    const res = await fetch("/api/contribute/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        promptId: prompt.id,
        text: text || undefined,
        audioId: nextAudioId || undefined,
      }),
    });
    setSaving(false);
    if (!res.ok) {
      setError("Could not save — try again");
      return;
    }
    await loadNext(viewLocale);
  }

  async function skip() {
    if (!prompt || saving || voiceLocked) return;
    setSaving(true);
    setError("");
    const res = await fetch("/api/contribute/skip", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ promptId: prompt.id }),
    });
    setSaving(false);
    if (!res.ok) return;
    await loadNext(viewLocale);
  }

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.href = "/";
  }

  return (
    <div className="page-shell">
      <IdleGuard />
      <nav
        className="flex flex-wrap items-end justify-between"
        style={{ marginBottom: "var(--space-4)", gap: "var(--space-3)" }}
      >
        <div className="min-w-0">
          <a href="/" className="font-brand type-brand tracking-tight">
            Lebne
          </a>
          <p
            className="truncate text-[var(--muted)]"
            style={{ marginTop: "var(--space-2)", fontSize: "var(--ui-text)" }}
          >
            {userName}
          </p>
        </div>
        <div className="flex flex-wrap items-center" style={{ gap: "var(--space-2)" }}>
          <ProgressRing {...progress} size="lg" />
          {isReviewer && (
            <a href="/admin" className="btn-primary">
              Admin
            </a>
          )}
          <button type="button" className="btn-ghost" onClick={logout}>
            Out
          </button>
        </div>
      </nav>

      {loading ? (
        <p
          className="text-center text-[var(--muted)]"
          style={{ paddingBlock: "var(--space-5)", fontSize: "var(--ui-text)" }}
        >
          Loading…
        </p>
      ) : doneAll || !prompt ? (
        <div
          className="flex flex-1 flex-col justify-center border border-dashed border-[var(--line)]"
          style={{
            borderRadius: "var(--radius)",
            padding: "var(--space-5)",
          }}
        >
          <p className="font-display type-source">Done for now</p>
          <p
            className="max-w-2xl leading-relaxed text-[var(--muted)]"
            style={{ marginTop: "var(--space-3)", fontSize: "var(--ui-text)" }}
          >
            No more items in your queue right now.
          </p>
          {isReviewer && (
            <a
              href="/admin"
              className="btn-primary"
              style={{ marginTop: "var(--space-4)", width: "fit-content" }}
            >
              Open admin
            </a>
          )}
        </div>
      ) : (
        <div className="flex flex-1 flex-col">
          <div
            className="flex flex-wrap items-end border-b border-[var(--line)]"
            style={{ marginBottom: "var(--space-4)", gap: "var(--space-1)" }}
          >
            {VIEW_LOCALES.map((loc) => {
              const on = viewLocale === loc;
              return (
                <button
                  key={loc}
                  type="button"
                  disabled={viewLoading || voiceLocked}
                  onClick={() => void switchView(loc)}
                  className={`relative font-bold uppercase tracking-[0.12em] transition ${
                    on ? "text-[var(--accent)]" : "text-[var(--muted)] hover:text-[var(--ink)]"
                  }`}
                  style={{
                    padding: `var(--space-2) clamp(0.75rem, 0.5rem + 1.5vw, 1.5rem)`,
                    paddingBottom: "var(--space-3)",
                    fontSize: "clamp(1rem, 0.85rem + 1.2vw, 1.85rem)",
                  }}
                >
                  {loc}
                  {on && (
                    <motion.span
                      layoutId="view-underline-xl"
                      className="absolute inset-x-[20%] bottom-0 h-1 rounded-full bg-[var(--accent)]"
                    />
                  )}
                </button>
              );
            })}
            <span
              className="type-label ml-auto max-w-full truncate text-[var(--muted)]"
              style={{ paddingBottom: "var(--space-3)" }}
            >
              {prompt.intent}
            </span>
          </div>

          <AnimatePresence mode="wait">
            <motion.div
              key={`${prompt.id}-${prompt.view}`}
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.3 }}
              style={{ marginBottom: "var(--space-4)" }}
            >
              <p className="type-label text-[var(--muted)]" style={{ marginBottom: "var(--space-2)" }}>
                Source · {viewLocale}
                {viewLoading ? " · …" : ""}
              </p>
              <p className="font-display type-source font-medium" dir="auto">
                {prompt.text}
              </p>
            </motion.div>
          </AnimatePresence>

          <section style={{ marginTop: "auto" }}>
            <p className="type-label text-[var(--muted)]" style={{ marginBottom: "var(--space-2)" }}>
              Your Hassaniya — type, speak, or both
            </p>

            <div className="action-grid">
              <div className="action-tile" data-kind="type" data-active={hassaniya.trim().length >= 2}>
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="type-label text-[var(--accent)]">Type</p>
                    <p className="type-ui text-[var(--muted)]" style={{ marginTop: "0.25rem" }}>
                      Write the Hassaniya here
                    </p>
                  </div>
                  <span
                    className="rounded-full px-3 py-1 font-bold"
                    style={{
                      fontSize: "var(--label-text)",
                      background: hassaniya.trim().length >= 2 ? "var(--accent)" : "rgba(255,255,255,0.06)",
                      color: hassaniya.trim().length >= 2 ? "var(--accent-ink)" : "var(--muted)",
                    }}
                  >
                    {hassaniya.trim().length >= 2 ? "Ready" : "Optional"}
                  </span>
                </div>
                <textarea
                  className="field-input type-panel min-h-[8rem] resize-none border-0 bg-black/25 focus:shadow-none"
                  style={{ minHeight: "clamp(7rem, 5rem + 12vw, 14rem)" }}
                  dir="auto"
                  placeholder="اكتبها بالحسانية…"
                  value={hassaniya}
                  onChange={(e) => setHassaniya(e.target.value)}
                  onKeyDown={(e) => {
                    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") void submit();
                  }}
                />
              </div>

              <div className="action-tile" data-kind="voice" data-active={Boolean(audioId)}>
                <VoiceRecorder
                  ref={voiceRef}
                  audioId={audioId}
                  onAudioId={setAudioId}
                  onTranscript={(t) => setHassaniya((prev) => prev || t)}
                  onStateChange={({ recording, busy }) => setVoiceBusy(recording || busy)}
                  withStt
                  label="Voice"
                />
              </div>
            </div>

            {error ? (
              <p className="text-sm text-[#e85d4c]" style={{ marginTop: "var(--space-2)" }}>
                {error}
              </p>
            ) : null}

            <div
              className="flex flex-wrap items-stretch"
              style={{ marginTop: "var(--space-4)", gap: "var(--space-2)" }}
            >
              <button
                type="button"
                className="btn-ghost"
                style={{ flex: "1 1 8rem" }}
                disabled={saving || voiceLocked}
                onClick={() => void skip()}
              >
                Skip
              </button>
              <button
                type="button"
                className="btn-primary"
                style={{ flex: "2 1 12rem" }}
                disabled={saving || (!canSubmit && !voiceLocked)}
                onClick={() => void submit()}
              >
                {saving ? "…" : voiceLocked ? "Saving voice…" : "Next"}
              </button>
            </div>
            <p
              className="text-[var(--muted)]"
              style={{ marginTop: "var(--space-2)", fontSize: "var(--label-text)" }}
            >
              Skip does not count as progress. Type, voice, or both → Next.
            </p>
          </section>
        </div>
      )}
    </div>
  );
}
