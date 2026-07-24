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

type AssistPhrase = { phrase: string; kind?: string; tier?: string; count?: number };

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
  const [showFromSource, setShowFromSource] = useState(false);
  const [showMyRepeats, setShowMyRepeats] = useState(false);
  const [sourcePhrases, setSourcePhrases] = useState<AssistPhrase[]>([]);
  const [myPhrases, setMyPhrases] = useState<AssistPhrase[]>([]);
  const [sourceBusy, setSourceBusy] = useState(false);
  const [mineBusy, setMineBusy] = useState(false);
  const [mineLoaded, setMineLoaded] = useState(false);
  const voiceRef = useRef<VoiceRecorderHandle | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const canSubmit = hassaniya.trim().length >= 2 || Boolean(audioId);
  const voiceLocked = voiceBusy;

  const loadNext = useCallback(async (view: string) => {
    setLoading(true);
    setHassaniya("");
    setAudioId(null);
    setError("");
    setSourcePhrases([]);
    setShowFromSource(false);
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

  const loadFromSource = useCallback(async (text: string) => {
    setSourceBusy(true);
    try {
      const res = await fetch(
        `/api/contribute/assist?q=${encodeURIComponent(text)}&limit=5`,
      );
      const data = await res.json();
      const words: AssistPhrase[] = Array.isArray(data.sourceWords)
        ? data.sourceWords
            .map((w: AssistPhrase) => ({
              phrase: String(w.phrase || "").trim(),
              kind: w.kind,
              tier: w.tier,
            }))
            .filter((w: AssistPhrase) => w.phrase.length >= 2)
        : [];
      // Fallback compose if older API without sourceWords
      if (words.length === 0) {
        const seen = new Set<string>();
        const add = (phrase: string, kind: string, tier?: string) => {
          const p = phrase.trim();
          if (p.length < 2 || seen.has(p)) return;
          seen.add(p);
          words.push({ phrase: p, kind, tier });
        };
        if (data.draft?.text) add(String(data.draft.text), "line", data.draft.source);
        for (const it of data.items || []) add(String(it.hassaniya || ""), "line", it.tier);
        for (const h of data.hassaniyaLines || []) add(String(h.text || ""), "line", "hassaniya_corpus");
        for (const b of data.bankingHints || []) add(String(b.text || ""), "banking", "banking");
        for (const d of data.dialectHints || []) add(String(d.text || ""), "dialect", "dialect_hint");
        for (const c of data.chips || []) add(String(c.phrase || ""), "chip", c.tier);
      }
      setSourcePhrases(words.slice(0, 28));
    } catch {
      setSourcePhrases([]);
    } finally {
      setSourceBusy(false);
    }
  }, []);

  async function toggleFromSource() {
    const next = !showFromSource;
    setShowFromSource(next);
    if (next && prompt?.text) await loadFromSource(prompt.text);
  }

  async function toggleMyRepeats() {
    const next = !showMyRepeats;
    setShowMyRepeats(next);
    if (!next || mineLoaded) return;
    setMineBusy(true);
    try {
      const res = await fetch("/api/contribute/assist?mine=1&limit=40");
      const data = await res.json();
      setMyPhrases(
        Array.isArray(data.phrases)
          ? data.phrases
              .map((p: AssistPhrase) => ({
                phrase: String(p.phrase || "").trim(),
                count: p.count,
                tier: "mine",
              }))
              .filter((p: AssistPhrase) => p.phrase.length >= 2)
          : [],
      );
      setMineLoaded(true);
    } catch {
      setMyPhrases([]);
    } finally {
      setMineBusy(false);
    }
  }

  function insertPhrase(phrase: string) {
    setHassaniya((prev) => {
      const cur = prev.trim();
      if (!cur) return phrase;
      if (cur.includes(phrase)) return cur;
      return `${cur} ${phrase}`.replace(/\s+/g, " ").trim();
    });
    window.setTimeout(() => textareaRef.current?.focus(), 0);
  }

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
              Your Hassaniya — tap helpers (optional), then type or speak
            </p>

            <div
              className="flex flex-wrap"
              style={{ gap: "var(--space-2)", marginBottom: "var(--space-2)" }}
            >
              <button
                type="button"
                className="btn-ghost"
                style={{
                  flex: "1 1 10rem",
                  minHeight: "2.75rem",
                  borderColor: showFromSource ? "var(--accent)" : undefined,
                  color: showFromSource ? "var(--accent)" : undefined,
                }}
                disabled={voiceLocked || !prompt}
                onClick={() => void toggleFromSource()}
              >
                {showFromSource ? "Hide · From source" : "From source"}
              </button>
              <button
                type="button"
                className="btn-ghost"
                style={{
                  flex: "1 1 10rem",
                  minHeight: "2.75rem",
                  borderColor: showMyRepeats ? "var(--accent)" : undefined,
                  color: showMyRepeats ? "var(--accent)" : undefined,
                }}
                disabled={voiceLocked}
                onClick={() => void toggleMyRepeats()}
              >
                {showMyRepeats ? "Hide · My repeats" : "My repeats"}
              </button>
            </div>

            {showFromSource ? (
              <div
                className="border border-[var(--line)] bg-black/15"
                style={{
                  marginBottom: "var(--space-3)",
                  borderRadius: "var(--radius)",
                  padding: "var(--space-3)",
                  maxHeight: "min(40vh, 16rem)",
                  overflowY: "auto",
                }}
              >
                <p className="type-label text-[var(--muted)]" style={{ marginBottom: "0.5rem" }}>
                  RIM / DAH / DTCD / stories + banking Arabic — tap to insert, then edit
                </p>
                {sourceBusy ? (
                  <p className="text-sm text-[var(--muted)]">Loading…</p>
                ) : sourcePhrases.length === 0 ? (
                  <p className="text-sm text-[var(--muted)]">No suggestions for this line yet.</p>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {sourcePhrases.map((p) => {
                      const tier = p.tier || "";
                      const isBanking = tier === "banking" || p.kind === "banking";
                      const isDialect = tier === "dialect_hint" || p.kind === "dialect";
                      return (
                        <button
                          key={`${p.kind}-${p.phrase}`}
                          type="button"
                          className="rounded-full border border-[var(--line)] bg-black/25 px-3 py-1.5 text-sm leading-snug text-[var(--ink)]"
                          style={{
                            maxWidth: "100%",
                            borderStyle: isDialect || isBanking ? "dashed" : "solid",
                            opacity: isBanking ? 0.92 : 1,
                          }}
                          title={
                            isBanking
                              ? "Banking Arabic — adapt into Mauritanian Hassaniya"
                              : isDialect
                                ? "Dialect hint — rewrite toward Mauritanian Hassaniya"
                                : tier === "hassaniya_corpus"
                                  ? "Hassaniya corpus (RIM / DAH / DTCD / stories)"
                                  : "Insert into input"
                          }
                          onClick={() => insertPhrase(p.phrase)}
                        >
                          <span dir="auto">{p.phrase}</span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            ) : null}

            {showMyRepeats ? (
              <div
                className="border border-[var(--line)] bg-black/15"
                style={{
                  marginBottom: "var(--space-3)",
                  borderRadius: "var(--radius)",
                  padding: "var(--space-3)",
                  maxHeight: "min(40vh, 16rem)",
                  overflowY: "auto",
                }}
              >
                <p className="type-label text-[var(--muted)]" style={{ marginBottom: "0.5rem" }}>
                  Your repeated Hassaniya — tap to insert, then edit
                </p>
                {mineBusy ? (
                  <p className="text-sm text-[var(--muted)]">Loading…</p>
                ) : myPhrases.length === 0 ? (
                  <p className="text-sm text-[var(--muted)]">
                    No repeats yet — after you submit a few lines, frequent words show here.
                  </p>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {myPhrases.map((p) => (
                      <button
                        key={`mine-${p.phrase}`}
                        type="button"
                        className="rounded-full border border-[var(--line)] bg-black/25 px-3 py-1.5 text-sm leading-snug text-[var(--ink)]"
                        style={{ maxWidth: "100%" }}
                        onClick={() => insertPhrase(p.phrase)}
                      >
                        <span dir="auto">{p.phrase}</span>
                        {p.count && p.count > 1 ? (
                          <span className="ml-1 text-[var(--muted)]">×{p.count}</span>
                        ) : null}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : null}

            <div className="action-grid">
              <div className="action-tile" data-kind="type" data-active={hassaniya.trim().length >= 2}>
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="type-label text-[var(--accent)]">Type</p>
                    <p className="type-ui text-[var(--muted)]" style={{ marginTop: "0.25rem" }}>
                      Write or finish the Hassaniya here
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
                  ref={textareaRef}
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
              Skip does not count. Optional: From source / My repeats → tap chips → edit → Next.
            </p>
          </section>
        </div>
      )}
    </div>
  );
}
