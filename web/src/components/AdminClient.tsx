"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { UserRole } from "@/lib/auth";
import { IdleGuard } from "./IdleGuard";
import { VoiceRecorder } from "./VoiceRecorder";

type UserRow = {
  id: number;
  name: string;
  email: string;
  role: UserRole;
  isAdmin: boolean;
  isReviewer: boolean;
  progress: { done: number; total: number; percent: number };
  submissions: { pending: number; approved: number; rejected: number };
};

type Item = {
  id: string;
  locale: string;
  text: string;
  audioId?: string | null;
  hasAudio?: boolean;
  audioPath?: string | null;
  note: string | null;
  status?: string;
  approvals?: {
    count: number;
    needed: number;
    voters: { id?: number | null; name: string }[];
  };
  user: { id?: number | null; name: string; email: string };
  prompt: {
    sourceText: string;
    sourceLocale: string;
    intent: string;
    importId: string;
  };
};

type ApprovedItem = {
  id: string;
  locale: string;
  text: string;
  answer?: string | null;
  audioId?: string | null;
  hasAudio?: boolean;
  audioPath?: string | null;
  status: string;
  acceptance: {
    mode: string;
    finalAccepter: { id?: number | null; name: string; email?: string; role?: string } | null;
    voters: { id?: number | null; name: string; email?: string }[];
    exportedAt?: string | null;
    reviewedAt?: string | null;
  };
  user: { id?: number | null; name: string; email: string };
  prompt: {
    sourceText: string;
    sourceLocale: string;
    intent: string;
    importId: string;
  };
};

type Daily = { used: number; limit: number | null; remaining: number | null };
type Tab = "inbox" | "people" | "approved";

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

function VoiceClip({
  submissionId,
  caption,
}: {
  submissionId: string;
  caption?: string;
}) {
  const [failed, setFailed] = useState(false);
  const [hint, setHint] = useState("");
  useEffect(() => {
    setFailed(false);
    setHint("");
  }, [submissionId]);

  async function onPlayError() {
    setFailed(true);
    try {
      const res = await fetch(`/api/admin/audio/${encodeURIComponent(submissionId)}`, {
        method: "GET",
        cache: "no-store",
      });
      if (res.status === 404 || res.status === 502) {
        setHint("This clip is missing — re-record and save a new take.");
      } else if (res.ok) {
        setHint(
          "This browser may not play this format — open Admin on Chrome/desktop or re-record on this device.",
        );
      } else if (res.status === 401) {
        setHint("Session expired — log in again.");
      } else {
        setHint("Could not play this clip — try again or re-record.");
      }
    } catch {
      setHint("Could not play this clip — try again or re-record.");
    }
  }

  return (
    <div className="rounded-2xl border border-[var(--teal)]/25 bg-[var(--teal)]/8 px-4 py-3 sm:px-5 sm:py-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--teal)] sm:text-xs">
          Voice
        </span>
        {caption ? (
          <span className="text-sm text-[var(--muted)] sm:text-base">{caption}</span>
        ) : null}
      </div>
      {failed ? (
        <p className="text-sm text-[#e85d4c] sm:text-base">
          {hint || "This clip is missing — re-record and save a new take."}
        </p>
      ) : (
        <audio
          key={submissionId}
          controls
          preload="metadata"
          className="w-full max-w-xl"
          src={`/api/admin/audio/${encodeURIComponent(submissionId)}`}
          onError={() => void onPlayError()}
        />
      )}
    </div>
  );
}

function BigRing({ percent, size = 120 }: { percent: number; size?: number }) {
  const r = size * 0.38;
  const c = 2 * Math.PI * r;
  const offset = c - (Math.min(percent, 100) / 100) * c;
  const mid = size / 2;
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
        <circle
          cx={mid}
          cy={mid}
          r={r}
          fill="none"
          stroke="rgba(242,245,247,0.08)"
          strokeWidth={size * 0.07}
        />
        <circle
          cx={mid}
          cy={mid}
          r={r}
          fill="none"
          stroke="var(--accent)"
          strokeWidth={size * 0.07}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={offset}
          className="transition-all duration-700"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-display text-[clamp(1.5rem,3vw,2.5rem)] leading-none tabular-nums text-[var(--accent)]">
          {percent}%
        </span>
      </div>
    </div>
  );
}

export function AdminClient({
  role,
  isOwner,
  userName,
}: {
  role: UserRole;
  isOwner: boolean;
  userName: string;
}) {
  const [tab, setTab] = useState<Tab>("inbox");
  const [users, setUsers] = useState<UserRow[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [approved, setApproved] = useState<ApprovedItem[]>([]);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [answerEdits, setAnswerEdits] = useState<Record<string, string>>({});
  const [audioEdits, setAudioEdits] = useState<Record<string, string | null>>({});
  const [editingId, setEditingId] = useState<string | null>(null);
  const [index, setIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [roleBusy, setRoleBusy] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [approvedQuery, setApprovedQuery] = useState("");
  const [toast, setToast] = useState("");
  const [daily, setDaily] = useState<Daily>({ used: 0, limit: null, remaining: null });
  const [consensusNeeded, setConsensusNeeded] = useState(3);
  const [booted, setBooted] = useState(false);

  const flash = useCallback((msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(""), 2600);
  }, []);

  const applyApprovedList = useCallback((list: ApprovedItem[]) => {
    setApproved(list);
    const tMap: Record<string, string> = {};
    const aMap: Record<string, string> = {};
    const vMap: Record<string, string | null> = {};
    for (const it of list) {
      tMap[it.id] = it.text;
      aMap[it.id] = it.answer || "";
      vMap[it.id] = it.audioId || null;
    }
    setAnswerEdits(aMap);
    setAudioEdits(vMap);
    setEdits((prev) => ({ ...prev, ...tMap }));
  }, []);

  const loadApproved = useCallback(
    async (q = "") => {
      if (!isOwner) return;
      const qs = q.trim() ? `?q=${encodeURIComponent(q.trim())}` : "";
      const res = await fetch(`/api/admin/approved${qs}`);
      if (!res.ok) return;
      const data = await res.json();
      applyApprovedList(data.items || []);
    },
    [applyApprovedList, isOwner],
  );

  const load = useCallback(async () => {
    setLoading(true);

    // Prefer one-shot bootstrap; fall back if Render is on an older API build.
    const bootRes = await fetch("/api/admin/bootstrap");
    if (bootRes.ok) {
      const data = await bootRes.json().catch(() => ({}));
      setLoading(false);
      const pending = data.pending || {};
      const list: Item[] = pending.items || [];
      setItems(list);
      setDaily(pending.daily || { used: 0, limit: null, remaining: null });
      if (pending.consensusNeeded) setConsensusNeeded(pending.consensusNeeded);
      const map: Record<string, string> = {};
      for (const it of list) map[it.id] = it.text;
      setEdits((prev) => ({ ...prev, ...map }));
      setIndex(0);
      if (!booted) {
        setTab(list.length > 0 || !isOwner ? "inbox" : "people");
        setBooted(true);
      }
      if (data.users?.users) setUsers(data.users.users);
      if (data.approved?.items) applyApprovedList(data.approved.items);
      return;
    }

    const pendingReq = fetch("/api/admin/pending");
    const usersReq = isOwner ? fetch("/api/admin/users") : Promise.resolve(null);
    const approvedReq = isOwner ? loadApproved("") : Promise.resolve();
    const [pRes, uRes] = await Promise.all([pendingReq, usersReq]);
    await approvedReq;
    const pData = await pRes.json().catch(() => ({}));
    setLoading(false);

    if (!pRes.ok) {
      flash(pData.error || "Could not load admin");
      return;
    }
    const list: Item[] = pData.items || [];
    setItems(list);
    setDaily(pData.daily || { used: 0, limit: null, remaining: null });
    if (pData.consensusNeeded) setConsensusNeeded(pData.consensusNeeded);
    const map: Record<string, string> = {};
    for (const it of list) map[it.id] = it.text;
    setEdits((prev) => ({ ...prev, ...map }));
    setIndex(0);
    if (!booted) {
      setTab(list.length > 0 || !isOwner ? "inbox" : "people");
      setBooted(true);
    }
    if (uRes && uRes.ok) {
      const uData = await uRes.json();
      setUsers(uData.users || []);
    }
  }, [applyApprovedList, booted, flash, isOwner, loadApproved]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!isOwner && (tab === "people" || tab === "approved")) setTab("inbox");
  }, [isOwner, tab]);

  useEffect(() => {
    if (tab !== "approved" || !isOwner) return;
    const t = window.setTimeout(() => void loadApproved(approvedQuery), 280);
    return () => window.clearTimeout(t);
  }, [approvedQuery, isOwner, loadApproved, tab]);

  const current = items[index] || null;

  const stats = useMemo(() => {
    const totalDone = users.reduce((s, u) => s + u.progress.done, 0);
    const totalApproved =
      approved.length || users.reduce((s, u) => s + u.submissions.approved, 0);
    return {
      queue: items.length,
      people: users.length,
      totalApproved,
      totalDone,
    };
  }, [users, items, approved.length]);

  const sortedUsers = useMemo(() => {
    const q = query.trim().toLowerCase();
    return [...users]
      .filter(
        (u) =>
          !q ||
          u.name.toLowerCase().includes(q) ||
          u.email.toLowerCase().includes(q),
      )
      .sort((a, b) => b.progress.done - a.progress.done || a.name.localeCompare(b.name));
  }, [users, query]);

  async function setRole(userId: number, next: "reviewer" | "contributor") {
    setRoleBusy(userId);
    const res = await fetch(`/api/admin/users/${userId}/role`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role: next }),
    });
    setRoleBusy(null);
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      flash(data.error || "Role update failed");
      return;
    }
    flash(next === "reviewer" ? "Granted reviewer" : "Revoked reviewer");
    await load();
  }

  async function saveApprovedEdit(id: string) {
    setBusy(true);
    const original = approved.find((a) => a.id === id);
    const nextAudio = audioEdits[id] ?? null;
    const clearAudio = !nextAudio && Boolean(original?.audioId || original?.hasAudio);
    const res = await fetch(`/api/admin/approved/${id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: edits[id] || "",
        answer: answerEdits[id] || "",
        audioId: nextAudio,
        clearAudio,
      }),
    });
    const data = await res.json().catch(() => ({}));
    setBusy(false);
    if (!res.ok) {
      flash(data.error || "Could not save");
      return;
    }
    flash("Approved item updated");
    setEditingId(null);
    await loadApproved(approvedQuery);
  }

  async function review(action: "approve" | "reject") {
    if (!current || busy) return;
    setBusy(true);
    const res = await fetch("/api/admin/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        submissionId: current.id,
        action,
        text: edits[current.id],
      }),
    });
    const data = await res.json().catch(() => ({}));
    setBusy(false);
    if (!res.ok) {
      flash(data.error || data.detail || "Could not save");
      return;
    }
    if (data.daily) setDaily(data.daily);
    if (action === "reject") {
      flash("Declined — progress removed");
    } else if (data.exported) {
      flash(isOwner ? "Approved · exported" : "Consensus reached · exported");
      if (isOwner) void loadApproved(approvedQuery);
    } else {
      const c = data.approvals?.count ?? 0;
      const n = data.approvals?.needed ?? consensusNeeded;
      flash(`Vote saved · ${c} / ${n}`);
    }

    if (action === "reject" || data.exported) {
      const nextItems = items.filter((i) => i.id !== current.id);
      setItems(nextItems);
      setIndex((i) => Math.min(i, Math.max(0, nextItems.length - 1)));
    } else if (data.approvals) {
      setItems((list) =>
        list.map((it) =>
          it.id === current.id
            ? {
                ...it,
                text: edits[current.id] || it.text,
                status: data.status || "awaiting_consensus",
                approvals: data.approvals,
              }
            : it,
        ),
      );
    }
    if (isOwner) {
      const uRes = await fetch("/api/admin/users");
      if (uRes.ok) {
        const uData = await uRes.json();
        setUsers(uData.users || []);
      }
    }
  }

  useEffect(() => {
    if (tab !== "inbox" || !current) return;
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "TEXTAREA" || tag === "INPUT") {
        if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
          e.preventDefault();
          void review("approve");
        }
        return;
      }
      if (e.key === "a" || e.key === "A") void review("approve");
      if (e.key === "d" || e.key === "D") void review("reject");
      if (e.key === "ArrowRight") setIndex((i) => Math.min(items.length - 1, i + 1));
      if (e.key === "ArrowLeft") setIndex((i) => Math.max(0, i - 1));
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, current, edits, busy, items.length]);

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.href = "/";
  }

  const approvals = current?.approvals;
  const approvalCount = approvals?.count ?? 0;
  const approvalNeeded = approvals?.needed ?? consensusNeeded;

  const ownerTabs = (
    [
      ["inbox", "Inbox", stats.queue],
      ["people", "People", stats.people],
      ["approved", "Approved", stats.totalApproved],
    ] as const
  );

  return (
    <div className="page-shell">
      <IdleGuard />
      <nav className="mb-10 flex flex-wrap items-end justify-between gap-5 sm:mb-12 sm:gap-6">
        <div className="min-w-0">
          <a href="/" className="font-brand type-brand tracking-tight">
            Lebne
          </a>
          <p className="mt-3 text-lg text-[var(--muted)] sm:text-xl lg:text-2xl">
            {userName}
            <span className="mx-2 opacity-40">·</span>
            <span className="text-[var(--accent)]">{role}</span>
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3 pb-1 sm:gap-4">
          {!isOwner && daily.limit != null && (
            <div className="rounded-2xl border border-[var(--line)] px-4 py-2.5 text-right sm:px-5 sm:py-3">
              <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--muted)] sm:text-xs">
                Reviews left today
              </p>
              <p className="font-display text-2xl tabular-nums text-[var(--accent)] sm:text-3xl">
                {daily.remaining ?? 0}
                <span className="text-base text-[var(--muted)] sm:text-xl"> / {daily.limit}</span>
              </p>
            </div>
          )}
          <a href="/contribute" className="btn-ghost px-6 py-3.5 text-base sm:px-8 sm:py-4 sm:text-lg">
            Contribute
          </a>
          <button
            type="button"
            className="btn-ghost px-6 py-3.5 text-base sm:px-8 sm:py-4 sm:text-lg"
            onClick={logout}
          >
            Out
          </button>
        </div>
      </nav>

      {!loading && (
        <div
          className={`mb-10 grid gap-3 sm:mb-12 sm:gap-4 ${
            isOwner ? "grid-cols-2 lg:grid-cols-4" : "grid-cols-2"
          }`}
        >
          {(isOwner
            ? [
                { label: "To review", value: stats.queue, on: () => setTab("inbox"), accent: true },
                { label: "People", value: stats.people, on: () => setTab("people") },
                {
                  label: "Approved",
                  value: stats.totalApproved,
                  on: () => setTab("approved"),
                  teal: true,
                },
                { label: "Items done", value: stats.totalDone, on: () => setTab("people") },
              ]
            : [
                { label: "To review", value: stats.queue, on: () => setTab("inbox"), accent: true },
                {
                  label: "Votes left today",
                  value: daily.remaining ?? 0,
                  on: () => setTab("inbox"),
                  accent: true,
                },
              ]
          ).map((s) => (
            <button
              key={s.label}
              type="button"
              onClick={s.on}
              className="rounded-[1.5rem] border border-[var(--line)] bg-[rgba(8,14,20,0.5)] px-5 py-6 text-left transition hover:border-[var(--accent)]/40 sm:rounded-[2rem] sm:px-7 sm:py-8"
            >
              <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--muted)] sm:text-sm sm:tracking-[0.2em]">
                {s.label}
              </p>
              <p
                className={`font-display type-stat mt-2 tabular-nums sm:mt-3 ${
                  s.accent
                    ? "text-[var(--accent)]"
                    : s.teal
                      ? "text-[var(--teal)]"
                      : "text-[var(--ink)]"
                }`}
              >
                {s.value.toLocaleString()}
              </p>
            </button>
          ))}
        </div>
      )}

      <div className="mb-10 flex items-end gap-1 overflow-x-auto border-b border-[var(--line)] sm:mb-12 sm:gap-2">
        {(isOwner
          ? ownerTabs
          : ([["inbox", "Inbox", stats.queue]] as const)
        ).map(([id, label, count]) => {
          const on = tab === id;
          return (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={`relative flex shrink-0 items-center gap-2 px-4 pb-4 pt-2 text-xl font-bold transition sm:gap-3 sm:px-6 sm:pb-5 sm:text-2xl lg:text-3xl ${
                on ? "text-[var(--accent)]" : "text-[var(--muted)] hover:text-[var(--ink)]"
              }`}
            >
              {label}
              <span
                className={`rounded-full px-2.5 py-0.5 text-sm tabular-nums sm:px-3 sm:py-1 sm:text-base lg:text-lg ${
                  on ? "bg-[var(--accent)] text-[var(--accent-ink)]" : "bg-white/8"
                }`}
              >
                {count}
              </span>
              {on && (
                <motion.span
                  layoutId="admin-tab-xl"
                  className="absolute inset-x-2 bottom-0 h-1 rounded-full bg-[var(--accent)] sm:inset-x-3"
                />
              )}
            </button>
          );
        })}
      </div>

      <AnimatePresence>
        {toast && (
          <motion.p
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="mb-6 rounded-2xl border border-[var(--teal)]/30 bg-[var(--teal)]/10 px-4 py-3 text-base text-[var(--teal)] sm:mb-8 sm:rounded-3xl sm:px-6 sm:py-5 sm:text-xl lg:text-2xl"
          >
            {toast}
          </motion.p>
        )}
      </AnimatePresence>

      {loading ? (
        <p className="py-24 text-center text-xl text-[var(--muted)] sm:py-32 sm:text-3xl">
          Loading…
        </p>
      ) : tab === "approved" && isOwner ? (
        <section>
          <div className="mb-8 flex flex-col gap-4 sm:mb-10 sm:flex-row sm:flex-wrap sm:items-end sm:justify-between sm:gap-6">
            <div className="min-w-0">
              <h2 className="font-display text-3xl sm:text-5xl md:text-6xl">Approved</h2>
              <p className="mt-2 max-w-2xl text-base text-[var(--muted)] sm:mt-3 sm:text-xl lg:text-2xl">
                Source · Hassaniya · who accepted. Edit anything that looks wrong or like a joke —
                owner only. Training JSONL has no emails — download is owner-only.
              </p>
            </div>
            <div className="flex w-full max-w-md flex-col gap-3">
              <input
                className="field-input w-full py-3 text-base sm:py-5 sm:text-xl"
                placeholder="Search text, email, accepter…"
                value={approvedQuery}
                onChange={(e) => setApprovedQuery(e.target.value)}
              />
              <a href="/api/admin/exports/hassaniya" className="btn-ghost text-center">
                Download Hassaniya JSONL
              </a>
            </div>
          </div>

          {approved.length === 0 ? (
            <div className="rounded-[1.75rem] border border-dashed border-[var(--line)] px-6 py-16 text-center sm:rounded-[2.5rem] sm:px-10 sm:py-28">
              <p className="font-display text-3xl sm:text-5xl">No approved items yet</p>
              <p className="mt-4 text-lg text-[var(--muted)] sm:text-2xl">
                Exports from you or 3-reviewer consensus show up here.
              </p>
            </div>
          ) : (
            <ul className="space-y-4 sm:space-y-6">
              {approved.map((it, i) => {
                const editing = editingId === it.id;
                const accepter = it.acceptance?.finalAccepter;
                const voters = it.acceptance?.voters || [];
                return (
                  <motion.li
                    key={it.id}
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: Math.min(i * 0.03, 0.2) }}
                    className="rounded-[1.75rem] border border-[var(--line)] bg-[rgba(8,14,20,0.58)] p-5 sm:rounded-[2.5rem] sm:p-8 lg:p-10"
                  >
                    <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
                      <div className="min-w-0">
                        <p className="text-xs font-bold uppercase tracking-[0.18em] text-[var(--muted)] sm:text-sm">
                          {it.prompt.intent}
                          <span className="mx-2 opacity-40">·</span>
                          {it.prompt.sourceLocale}
                          <span className="mx-2 opacity-40">·</span>
                          <span className="text-[var(--teal)]">
                            {it.acceptance?.mode === "owner" ? "owner export" : "consensus"}
                          </span>
                        </p>
                        <p
                          className="font-display mt-3 text-2xl leading-snug sm:text-4xl"
                          dir="auto"
                        >
                          {it.prompt.sourceText}
                        </p>
                        <p className="mt-2 text-sm text-[var(--muted)] sm:text-base">
                          Word / question (source)
                        </p>
                      </div>
                      <button
                        type="button"
                        className={editing ? "btn-ghost px-5 py-3 text-sm sm:text-base" : "btn-primary px-5 py-3 text-sm sm:text-base"}
                        onClick={() => setEditingId(editing ? null : it.id)}
                      >
                        {editing ? "Cancel" : "Edit"}
                      </button>
                    </div>

                    <div className="mb-5 space-y-3">
                      {editing ? (
                        <VoiceRecorder
                          audioId={audioEdits[it.id] ?? null}
                          onAudioId={(id) => setAudioEdits((m) => ({ ...m, [it.id]: id }))}
                          withStt={false}
                          label="Voice (editable)"
                        />
                      ) : it.audioId ? (
                        <VoiceClip
                          submissionId={it.id}
                          caption="Play while checking word / Hassaniya / answer"
                        />
                      ) : (
                        <p className="text-sm text-[var(--muted)]">No playable voice on this item.</p>
                      )}
                    </div>

                    <div className="grid gap-4 lg:grid-cols-2">
                      <div className="rounded-2xl bg-white/[0.04] px-4 py-4 sm:px-6 sm:py-5">
                        <p className="text-xs font-bold uppercase tracking-[0.16em] text-[var(--accent)]">
                          Hassaniya
                        </p>
                        {editing ? (
                          <textarea
                            className="field-input type-panel mt-3 min-h-[120px] resize-none"
                            dir="auto"
                            value={edits[it.id] || ""}
                            onChange={(e) =>
                              setEdits((m) => ({ ...m, [it.id]: e.target.value }))
                            }
                          />
                        ) : (
                          <p className="mt-3 text-xl leading-relaxed sm:text-2xl" dir="auto">
                            {it.text}
                          </p>
                        )}
                      </div>
                      <div className="rounded-2xl bg-white/[0.04] px-4 py-4 sm:px-6 sm:py-5">
                        <p className="text-xs font-bold uppercase tracking-[0.16em] text-[var(--muted)]">
                          Response / answer
                        </p>
                        {editing ? (
                          <textarea
                            className="field-input mt-3 min-h-[120px] resize-none text-lg"
                            dir="auto"
                            placeholder="Optional answer…"
                            value={answerEdits[it.id] || ""}
                            onChange={(e) =>
                              setAnswerEdits((m) => ({ ...m, [it.id]: e.target.value }))
                            }
                          />
                        ) : (
                          <p className="mt-3 text-lg text-[var(--muted)] sm:text-xl" dir="auto">
                            {it.answer?.trim() || "—"}
                          </p>
                        )}
                      </div>
                    </div>

                    <div className="mt-6 flex flex-col gap-4 border-t border-[var(--line)] pt-5 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
                      <div className="min-w-0 space-y-2 text-base sm:text-lg">
                        <p className="text-[var(--muted)]">
                          Contributor{" "}
                          <span className="font-semibold text-[var(--ink)]">{it.user.name}</span>
                          <span className="mx-2 opacity-40">·</span>
                          <span className="truncate">{it.user.email}</span>
                        </p>
                        <p className="text-[var(--muted)]">
                          Accepted by{" "}
                          <span className="font-semibold text-[var(--teal)]">
                            {accepter?.name || "—"}
                          </span>
                          {accepter?.role ? (
                            <span className="ml-2 rounded-full bg-white/8 px-3 py-0.5 text-xs font-bold uppercase tracking-[0.14em] text-[var(--accent)]">
                              {accepter.role}
                            </span>
                          ) : null}
                        </p>
                        {voters.length > 0 && (
                          <p className="text-[var(--muted)]">
                            Voters{" "}
                            <span className="text-[var(--ink)]">
                              {voters.map((v) => v.name).join(" · ")}
                            </span>
                          </p>
                        )}
                      </div>
                      {editing && (
                        <button
                          type="button"
                          className="btn-primary px-8 py-4 text-base sm:text-lg"
                          disabled={busy || !(edits[it.id] || "").trim()}
                          onClick={() => void saveApprovedEdit(it.id)}
                        >
                          {busy ? "…" : "Save fix · re-export"}
                        </button>
                      )}
                    </div>
                  </motion.li>
                );
              })}
            </ul>
          )}
        </section>
      ) : tab === "people" && isOwner ? (
        <section>
          <div className="mb-8 flex flex-col gap-4 sm:mb-10 sm:flex-row sm:flex-wrap sm:items-end sm:justify-between sm:gap-6">
            <div className="min-w-0">
              <h2 className="font-display text-3xl sm:text-5xl md:text-6xl">Contributors</h2>
              <p className="mt-2 max-w-xl text-base text-[var(--muted)] sm:mt-3 sm:text-xl lg:text-2xl">
                Grant or revoke reviewer access. Owners export on approve; reviewers need{" "}
                {consensusNeeded} votes.
              </p>
            </div>
            <input
              className="field-input w-full max-w-md py-3 text-base sm:py-5 sm:text-xl lg:text-2xl"
              placeholder="Search name or email…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>

          {sortedUsers.length === 0 ? (
            <div className="rounded-[1.75rem] border border-dashed border-[var(--line)] px-6 py-16 text-center sm:rounded-[2.5rem] sm:px-10 sm:py-28">
              <p className="font-display text-3xl sm:text-5xl">No matches</p>
            </div>
          ) : (
            <ul className="space-y-4 sm:space-y-6">
              {sortedUsers.map((u, i) => (
                <motion.li
                  key={u.id}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: Math.min(i * 0.04, 0.25) }}
                  className="rounded-[1.75rem] border border-[var(--line)] bg-[rgba(8,14,20,0.58)] p-5 sm:rounded-[2.5rem] sm:p-8 lg:p-10"
                >
                  <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between lg:gap-8">
                    <div className="flex min-w-0 items-center gap-4 sm:gap-6">
                      <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-[var(--accent)]/15 font-brand text-xl text-[var(--accent)] sm:h-24 sm:w-24 sm:text-3xl lg:h-28 lg:w-28 lg:text-4xl">
                        {initials(u.name)}
                      </div>
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
                          <p className="font-display text-2xl leading-tight sm:text-4xl lg:text-5xl">
                            {u.name}
                          </p>
                          <span className="rounded-full bg-white/8 px-3 py-1 text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--accent)] sm:px-4 sm:py-1.5 sm:text-sm">
                            {u.role}
                          </span>
                        </div>
                        <p className="mt-2 truncate text-base text-[var(--muted)] sm:mt-3 sm:text-2xl lg:text-3xl">
                          {u.email}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-5 sm:gap-8">
                      <BigRing percent={u.progress.percent} size={120} />
                      <div className="min-w-0">
                        <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--muted)] sm:text-sm">
                          Progress
                        </p>
                        <p className="mt-1 font-display text-2xl tabular-nums sm:mt-2 sm:text-3xl lg:text-4xl">
                          {u.progress.done.toLocaleString()}
                          <span className="mx-2 text-[var(--muted)]">/</span>
                          {u.progress.total.toLocaleString()}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="mt-6 grid grid-cols-3 gap-2 sm:mt-8 sm:gap-4">
                    <div className="rounded-2xl bg-white/[0.04] px-3 py-4 sm:rounded-3xl sm:px-6 sm:py-6">
                      <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--muted)] sm:text-sm">
                        Approved
                      </p>
                      <p className="font-display mt-1 text-2xl tabular-nums text-[var(--teal)] sm:mt-2 sm:text-5xl">
                        {u.submissions.approved}
                      </p>
                    </div>
                    <div className="rounded-2xl bg-white/[0.04] px-3 py-4 sm:rounded-3xl sm:px-6 sm:py-6">
                      <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--muted)] sm:text-sm">
                        Pending
                      </p>
                      <p className="font-display mt-1 text-2xl tabular-nums sm:mt-2 sm:text-5xl">
                        {u.submissions.pending}
                      </p>
                    </div>
                    <div className="rounded-2xl bg-white/[0.04] px-3 py-4 sm:rounded-3xl sm:px-6 sm:py-6">
                      <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--muted)] sm:text-sm">
                        Declined
                      </p>
                      <p className="font-display mt-1 text-2xl tabular-nums text-[#e85d4c] sm:mt-2 sm:text-5xl">
                        {u.submissions.rejected}
                      </p>
                    </div>
                  </div>

                  {u.role !== "owner" && (
                    <div className="mt-6 flex flex-wrap gap-3 sm:mt-8">
                      {u.role === "reviewer" ? (
                        <button
                          type="button"
                          className="btn-ghost px-6 py-3 text-sm sm:px-8 sm:py-4 sm:text-lg"
                          disabled={roleBusy === u.id}
                          onClick={() => void setRole(u.id, "contributor")}
                        >
                          {roleBusy === u.id ? "…" : "Revoke reviewer"}
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="btn-primary px-6 py-3 text-sm sm:px-8 sm:py-4 sm:text-lg"
                          disabled={roleBusy === u.id}
                          onClick={() => void setRole(u.id, "reviewer")}
                        >
                          {roleBusy === u.id ? "…" : "Grant reviewer"}
                        </button>
                      )}
                    </div>
                  )}
                </motion.li>
              ))}
            </ul>
          )}
        </section>
      ) : !current ? (
        <div className="flex flex-1 flex-col justify-center rounded-[1.75rem] border border-dashed border-[var(--line)] px-6 py-16 sm:rounded-[3rem] sm:px-16 sm:py-28">
          <p className="font-display type-source">Inbox is clear</p>
          <p className="mt-4 max-w-2xl text-base leading-relaxed text-[var(--muted)] sm:mt-6 sm:text-2xl lg:text-3xl">
            {isOwner
              ? "When others submit Hassaniya takes, they show up here."
              : "Nothing waiting for your vote right now."}
          </p>
          {isOwner && (
            <div className="mt-8 flex flex-wrap gap-3 sm:mt-12">
              <button
                type="button"
                className="btn-primary w-fit px-8 py-4 text-base sm:px-10 sm:py-5 sm:text-xl"
                onClick={() => setTab("people")}
              >
                See people
              </button>
              <button
                type="button"
                className="btn-ghost w-fit px-8 py-4 text-base sm:px-10 sm:py-5 sm:text-xl"
                onClick={() => setTab("approved")}
              >
                See approved
              </button>
            </div>
          )}
        </div>
      ) : (
        <div className="flex flex-1 flex-col">
          <div className="mb-6 flex flex-col gap-4 sm:mb-10 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between sm:gap-6">
            <div className="flex min-w-0 items-center gap-3 sm:gap-5">
              <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-white/5 font-brand text-lg text-[var(--muted)] sm:h-20 sm:w-20 sm:text-2xl lg:h-24 lg:w-24 lg:text-3xl">
                {initials(current.user.name)}
              </div>
              <div className="min-w-0">
                <p className="font-display truncate text-2xl sm:text-4xl lg:text-5xl">
                  {current.user.name}
                </p>
                <p className="mt-1 truncate text-base text-[var(--muted)] sm:mt-2 sm:text-2xl lg:text-3xl">
                  {current.user.email}
                </p>
              </div>
            </div>
            <div className="sm:text-right">
              <p className="font-display text-2xl tabular-nums text-[var(--muted)] sm:text-3xl lg:text-4xl">
                {index + 1}
                <span className="mx-2 opacity-40">/</span>
                {items.length}
              </p>
              <p className="mt-1 text-sm text-[var(--accent)] sm:mt-2 sm:text-lg lg:text-xl">
                {isOwner
                  ? "Your approve exports now"
                  : `${approvalCount} / ${approvalNeeded} reviewer votes`}
              </p>
            </div>
          </div>

          {!isOwner && (
            <div className="mb-6 h-2 overflow-hidden rounded-full bg-white/5 sm:mb-8 sm:h-3">
              <motion.div
                className="h-full rounded-full bg-[var(--accent)]"
                animate={{
                  width: `${Math.min(100, (approvalCount / Math.max(approvalNeeded, 1)) * 100)}%`,
                }}
              />
            </div>
          )}

          <AnimatePresence mode="wait">
            <motion.div
              key={current.id}
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.3 }}
              className="mb-8 sm:mb-12"
            >
              <p className="mb-3 text-xs font-bold uppercase tracking-[0.16em] text-[var(--muted)] sm:mb-5 sm:text-base sm:tracking-[0.2em] lg:text-lg">
                {current.prompt.intent}
                <span className="mx-2 opacity-40 sm:mx-3">·</span>
                {current.prompt.sourceLocale}
                {current.audioId && (
                  <>
                    <span className="mx-2 opacity-40 sm:mx-3">·</span>
                    <span className="text-[var(--teal)]">voice</span>
                  </>
                )}
                {current.status === "awaiting_consensus" && (
                  <>
                    <span className="mx-2 opacity-40 sm:mx-3">·</span>
                    <span className="text-[var(--accent)]">awaiting consensus</span>
                  </>
                )}
              </p>
              <p className="mb-2 text-sm text-[var(--muted)] sm:text-base">
                Word / question (source)
              </p>
              <p className="font-display type-source font-medium" dir="auto">
                {current.prompt.sourceText}
              </p>
              {current.audioId ? (
                <div className="mt-6">
                  <VoiceClip
                    submissionId={current.id}
                    caption="Contributor recording — verify against the text below"
                  />
                </div>
              ) : null}
            </motion.div>
          </AnimatePresence>

          <section className="mt-auto rounded-[1.75rem] border border-[var(--line)] bg-[rgba(8,14,20,0.6)] p-5 sm:rounded-[2.75rem] sm:p-10 lg:p-12">
            <div className="mb-4 flex flex-col gap-2 sm:mb-5 sm:flex-row sm:flex-wrap sm:items-end sm:justify-between sm:gap-3">
              <p className="text-xs font-bold uppercase tracking-[0.2em] text-[var(--accent)] sm:text-base lg:text-lg">
                Their Hassaniya
              </p>
              <p className="text-sm text-[var(--muted)] sm:text-lg lg:text-xl">
                {isOwner
                  ? "Edit then approve to export"
                  : "Edit resets other votes · same text needs 3"}
              </p>
            </div>
            <textarea
              className="field-input type-panel min-h-[160px] resize-none rounded-2xl border-0 bg-black/20 px-4 py-4 focus:shadow-none sm:min-h-[220px] sm:rounded-[1.75rem] sm:px-6 sm:py-5 lg:min-h-[260px]"
              dir="auto"
              value={edits[current.id] || ""}
              onChange={(e) => setEdits((m) => ({ ...m, [current.id]: e.target.value }))}
            />
            <div className="mt-6 flex flex-col gap-3 sm:mt-10 sm:gap-5">
              <div className="flex flex-wrap gap-2 sm:gap-3">
                <button
                  type="button"
                  className="btn-ghost flex-1 px-5 py-3 text-sm sm:flex-none sm:px-8 sm:py-4 sm:text-xl"
                  disabled={index <= 0 || busy}
                  onClick={() => setIndex((i) => Math.max(0, i - 1))}
                >
                  ← Prev
                </button>
                <button
                  type="button"
                  className="btn-ghost flex-1 px-5 py-3 text-sm sm:flex-none sm:px-8 sm:py-4 sm:text-xl"
                  disabled={index >= items.length - 1 || busy}
                  onClick={() => setIndex((i) => Math.min(items.length - 1, i + 1))}
                >
                  Skip →
                </button>
              </div>
              <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:justify-end sm:gap-3">
                <button
                  type="button"
                  className="rounded-full border-2 border-[#e85d4c]/50 px-6 py-3 text-base font-bold text-[#e85d4c] transition hover:bg-[#e85d4c]/10 disabled:opacity-40 sm:px-10 sm:py-4 sm:text-xl"
                  disabled={busy}
                  onClick={() => void review("reject")}
                >
                  Decline
                </button>
                <button
                  type="button"
                  className="btn-primary px-6 py-3 text-base sm:px-12 sm:py-4 sm:text-xl"
                  disabled={busy || !(edits[current.id] || "").trim()}
                  onClick={() => void review("approve")}
                >
                  {busy ? "…" : isOwner ? "Approve · export" : "Approve vote"}
                </button>
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
