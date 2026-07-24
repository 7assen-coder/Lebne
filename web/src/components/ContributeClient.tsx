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

type Chip = { phrase: string; tier?: string };

type Template = {
  id?: string;
  pattern: string;
  fixed?: string;
  has_slot?: boolean;
  accept_as_is?: boolean;
};

type SuggestItem = { hassaniya: string; tier?: string; score?: number };

type DialectHint = { text: string; dialect?: string; flag?: string };

type Draft = {
  text: string;
  source?: string;
  fixed?: string;
  slot?: string;
  has_slot?: boolean;
  pattern?: string;
};

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
  const [chips, setChips] = useState<Chip[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [matchedTemplates, setMatchedTemplates] = useState<Template[]>([]);
  const [suggestions, setSuggestions] = useState<SuggestItem[]>([]);
  const [dialectHints, setDialectHints] = useState<DialectHint[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [draftRejected, setDraftRejected] = useState(false);
  const [suggestBusy, setSuggestBusy] = useState(false);
  const [slotEdit, setSlotEdit] = useState("");
  const voiceRef = useRef<VoiceRecorderHandle | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const canSubmit = hassaniya.trim().length >= 2 || Boolean(audioId);
  const voiceLocked = voiceBusy;

  const loadNext = useCallback(async (view: string) => {
    setLoading(true);
    setHassaniya("");
    setAudioId(null);
    setError("");
    setDraft(null);
    setDraftRejected(false);
    setSuggestions([]);
    setMatchedTemplates([]);
    setDialectHints([]);
    setSlotEdit("");
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

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/contribute/assist");
        const data = await res.json();
        if (!cancelled && res.ok) {
          if (Array.isArray(data.chips)) {
            setChips(
              data.chips
                .map((c: Chip) => ({ phrase: String(c.phrase || "").trim(), tier: c.tier }))
                .filter((c: Chip) => c.phrase.length >= 2)
                .slice(0, 24),
            );
          }
          if (Array.isArray(data.templates)) {
            setTemplates(
              data.templates
                .map((t: Template) => ({
                  id: t.id,
                  pattern: String(t.pattern || "").trim(),
                  accept_as_is: Boolean(t.accept_as_is),
                  has_slot: String(t.pattern || "").includes("[X]"),
                }))
                .filter((t: Template) => t.pattern.length >= 2),
            );
          }
        }
      } catch {
        /* optional assist */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!prompt?.text) {
      setSuggestions([]);
      setDraft(null);
      setMatchedTemplates([]);
      setDialectHints([]);
      return;
    }
    let cancelled = false;
    const handle = window.setTimeout(() => {
      void (async () => {
        setSuggestBusy(true);
        setDraftRejected(false);
        try {
          const res = await fetch(
            `/api/contribute/assist?q=${encodeURIComponent(prompt.text)}&limit=3`,
          );
          const data = await res.json();
          if (cancelled || !res.ok) return;
          setSuggestions(
            Array.isArray(data.items)
              ? data.items
                  .map((it: SuggestItem) => ({
                    hassaniya: String(it.hassaniya || "").trim(),
                    tier: it.tier,
                    score: it.score,
                  }))
                  .filter((it: SuggestItem) => it.hassaniya.length >= 2)
              : [],
          );
          setMatchedTemplates(Array.isArray(data.templates) ? data.templates : []);
          setDialectHints(
            Array.isArray(data.dialectHints)
              ? data.dialectHints
                  .map((d: DialectHint) => ({
                    text: String(d.text || "").trim(),
                    dialect: d.dialect,
                    flag: d.flag,
                  }))
                  .filter((d: DialectHint) => d.text.length >= 2)
              : [],
          );
          const d = data.draft;
          if (d && typeof d.text === "string" && d.text.trim().length >= 2) {
            setDraft({
              text: d.text.trim(),
              source: d.source,
              fixed: d.fixed || "",
              slot: d.slot || "",
              has_slot: Boolean(d.has_slot),
              pattern: d.pattern,
            });
            setSlotEdit(String(d.slot || "").trim());
          } else {
            setDraft(null);
            setSlotEdit("");
          }
        } catch {
          if (!cancelled) {
            setSuggestions([]);
            setDraft(null);
          }
        } finally {
          if (!cancelled) setSuggestBusy(false);
        }
      })();
    }, 200);
    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [prompt?.id, prompt?.text]);

  function insertChip(phrase: string) {
    setHassaniya((prev) => {
      const cur = prev.trim();
      if (!cur) return phrase;
      if (cur.includes(phrase)) return cur;
      return `${cur} ${phrase}`.replace(/\s+/g, " ").trim();
    });
    setDraftRejected(false);
  }

  function applyTemplate(pattern: string, acceptAsIs?: boolean) {
    if (acceptAsIs || !pattern.includes("[X]")) {
      setHassaniya(pattern.replace("[X]", "").trim());
      setSlotEdit("");
      setDraft(null);
      return;
    }
    setDraft({
      text: pattern,
      source: "template",
      fixed: pattern.replace("[X]", "").trim(),
      slot: "",
      has_slot: true,
      pattern,
    });
    setSlotEdit("");
    setHassaniya("");
    setDraftRejected(false);
  }

  function acceptDraft() {
    if (!draft) return;
    let text = draft.text;
    if (draft.has_slot && draft.pattern?.includes("[X]")) {
      const slot = slotEdit.trim();
      text = slot ? draft.pattern.replace("[X]", slot) : draft.pattern.replace(/\s*\[X\]\s*/, " ").trim();
    }
    setHassaniya(text.replace(/\s+/g, " ").trim());
    setDraft(null);
    setDraftRejected(false);
    window.setTimeout(() => textareaRef.current?.focus(), 0);
  }

  function editDraft() {
    if (!draft) return;
    let text = draft.text;
    if (draft.has_slot && draft.pattern?.includes("[X]")) {
      const slot = slotEdit.trim();
      text = slot ? draft.pattern.replace("[X]", slot) : draft.text;
    }
    setHassaniya(text.replace(/\s+/g, " ").trim());
    setDraft(null);
    setDraftRejected(false);
    window.setTimeout(() => {
      const el = textareaRef.current;
      if (!el) return;
      el.focus();
      const fixed = (draft.fixed || "").trim();
      if (fixed && el.value.startsWith(fixed)) {
        el.setSelectionRange(fixed.length, el.value.length);
      } else {
        el.setSelectionRange(el.value.length, el.value.length);
      }
    }, 0);
  }

  function rejectDraft() {
    setDraft(null);
    setDraftRejected(true);
    setSlotEdit("");
    setHassaniya("");
  }

  function applySuggestion(text: string) {
    setHassaniya(text);
    setDraft(null);
    setDraftRejected(false);
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
              Your Hassaniya — draft, templates, chips, type, or speak
            </p>

            {draft && !draftRejected ? (
              <div
                className="border border-[var(--line)] bg-black/20"
                style={{
                  marginBottom: "var(--space-3)",
                  borderRadius: "var(--radius)",
                  padding: "var(--space-3)",
                }}
              >
                <p className="type-label text-[var(--teal)]" style={{ marginBottom: "0.35rem" }}>
                  Draft · {draft.source || "suggest"} — Accept / Edit / Reject
                </p>
                <p className="type-ui" dir="auto" style={{ marginBottom: "0.5rem", lineHeight: 1.5 }}>
                  {draft.has_slot && draft.pattern?.includes("[X]") ? (
                    <>
                      <span className="text-[var(--muted)]">{draft.pattern.split("[X]")[0]}</span>
                      <mark
                        style={{
                          background: "rgba(45, 212, 191, 0.25)",
                          color: "inherit",
                          padding: "0 0.2em",
                          borderRadius: "0.25rem",
                        }}
                      >
                        {slotEdit.trim() || "[X]"}
                      </mark>
                      <span className="text-[var(--muted)]">{draft.pattern.split("[X]")[1] || ""}</span>
                    </>
                  ) : draft.fixed ? (
                    <>
                      <span className="text-[var(--muted)]">{draft.fixed} </span>
                      <mark
                        style={{
                          background: "rgba(45, 212, 191, 0.25)",
                          color: "inherit",
                          padding: "0 0.2em",
                          borderRadius: "0.25rem",
                        }}
                      >
                        {draft.text.startsWith(draft.fixed)
                          ? draft.text.slice(draft.fixed.length).trim() || "…"
                          : draft.text}
                      </mark>
                    </>
                  ) : (
                    draft.text
                  )}
                </p>
                {draft.has_slot ? (
                  <input
                    className="field-input mb-2 w-full"
                    dir="auto"
                    placeholder="Fill [X] only — e.g. تحويله من الصين"
                    value={slotEdit}
                    onChange={(e) => setSlotEdit(e.target.value)}
                  />
                ) : null}
                <div className="flex flex-wrap gap-2">
                  <button type="button" className="btn-primary" onClick={acceptDraft}>
                    Accept
                  </button>
                  <button type="button" className="btn-ghost" onClick={editDraft}>
                    Edit
                  </button>
                  <button type="button" className="btn-ghost" onClick={rejectDraft}>
                    Reject
                  </button>
                </div>
              </div>
            ) : suggestBusy ? (
              <p className="text-sm text-[var(--muted)]" style={{ marginBottom: "var(--space-2)" }}>
                Looking for a draft…
              </p>
            ) : null}

            {(matchedTemplates.length > 0 || templates.length > 0) && (
              <div style={{ marginBottom: "var(--space-2)" }}>
                <p className="type-label text-[var(--muted)]" style={{ marginBottom: "0.35rem" }}>
                  Slot templates
                </p>
                <div className="flex flex-wrap gap-2">
                  {(matchedTemplates.length > 0 ? matchedTemplates : templates.slice(0, 6)).map((t) => (
                    <button
                      key={t.id || t.pattern}
                      type="button"
                      className="rounded-full border border-[var(--line)] bg-black/20 px-3 py-1 text-sm"
                      onClick={() => applyTemplate(t.pattern, t.accept_as_is)}
                    >
                      {t.pattern}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {suggestions.length > 0 ? (
              <div style={{ marginBottom: "var(--space-2)" }}>
                <p className="type-label text-[var(--muted)]" style={{ marginBottom: "0.35rem" }}>
                  Similar (gold / Hassaniya)
                </p>
                <div className="flex flex-wrap gap-2">
                  {suggestions.map((s) => (
                    <button
                      key={s.hassaniya}
                      type="button"
                      className="btn-ghost"
                      style={{ fontSize: "0.95rem", padding: "0.45rem 0.75rem" }}
                      onClick={() => applySuggestion(s.hassaniya)}
                    >
                      {s.hassaniya}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            {dialectHints.length > 0 ? (
              <div style={{ marginBottom: "var(--space-2)" }}>
                <p className="type-label text-[var(--muted)]" style={{ marginBottom: "0.35rem" }}>
                  Dialect hint (Tunisian — edit to Hassaniya)
                </p>
                <div className="flex flex-wrap gap-2">
                  {dialectHints.map((d) => (
                    <button
                      key={d.text}
                      type="button"
                      className="rounded-full border border-dashed border-[var(--line)] px-3 py-1 text-sm text-[var(--muted)]"
                      onClick={() => applySuggestion(d.text)}
                      title="Scaffolding only — rewrite into Mauritanian Hassaniya"
                    >
                      {d.text}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            {chips.length > 0 ? (
              <div style={{ marginBottom: "var(--space-3)" }}>
                <p className="type-label text-[var(--muted)]" style={{ marginBottom: "0.35rem" }}>
                  Phrase chips
                </p>
                <div className="flex flex-wrap gap-2">
                  {chips.map((c) => (
                    <button
                      key={c.phrase}
                      type="button"
                      className="rounded-full border border-[var(--line)] bg-black/20 px-3 py-1 text-sm text-[var(--ink)]"
                      onClick={() => insertChip(c.phrase)}
                    >
                      {c.phrase}
                    </button>
                  ))}
                </div>
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
              Skip does not count as progress. Accept a draft, fill [X], or type/voice → Next.
            </p>
          </section>
        </div>
      )}
    </div>
  );
}
