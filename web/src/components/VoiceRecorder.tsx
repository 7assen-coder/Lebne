"use client";

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type ChangeEvent,
} from "react";
import { loadAudioObjectUrl } from "@/lib/audio-playback";
import { pickRecorderMime, uploadVoiceBlob } from "@/lib/voice-upload";

export type VoiceRecorderHandle = {
  recording: boolean;
  busy: boolean;
  stopAndFlush: () => Promise<string | null>;
};

type Props = {
  audioId: string | null;
  onAudioId: (id: string | null) => void;
  onTranscript?: (text: string) => void;
  withStt?: boolean;
  label?: string;
  onStateChange?: (state: { recording: boolean; busy: boolean }) => void;
};

export const VoiceRecorder = forwardRef<VoiceRecorderHandle, Props>(function VoiceRecorder(
  {
    audioId,
    onAudioId,
    onTranscript,
    withStt = true,
    label = "Voice",
    onStateChange,
  },
  ref,
) {
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [hint, setHint] = useState("");
  const [failed, setFailed] = useState(false);
  const [previewSrc, setPreviewSrc] = useState<string | null>(null);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const mimeRef = useRef("audio/webm");
  const audioIdRef = useRef(audioId);
  const uploadPromiseRef = useRef<Promise<string | null> | null>(null);
  const stopWaitersRef = useRef<Array<(id: string | null) => void>>([]);

  useEffect(() => {
    audioIdRef.current = audioId;
  }, [audioId]);

  useEffect(() => {
    onStateChange?.({ recording, busy });
  }, [recording, busy, onStateChange]);

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    setPreviewSrc(null);
    if (!audioId) return;
    void (async () => {
      try {
        const loaded = await loadAudioObjectUrl(`/api/audio/${encodeURIComponent(audioId)}`);
        if (cancelled) {
          URL.revokeObjectURL(loaded.url);
          return;
        }
        objectUrl = loaded.url;
        setPreviewSrc(loaded.url);
      } catch {
        if (!cancelled) setPreviewSrc(null);
      }
    })();
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [audioId]);

  function settleStopWaiters(id: string | null) {
    const waiters = stopWaitersRef.current;
    stopWaitersRef.current = [];
    for (const resolve of waiters) resolve(id);
  }

  async function handleBlob(blob: Blob): Promise<string | null> {
    setBusy(true);
    setHint("Uploading…");
    setFailed(false);
    const work = (async () => {
      try {
        const result = await uploadVoiceBlob(blob, { withStt });
        onAudioId(result.audioId);
        audioIdRef.current = result.audioId;
        if (result.transcript && onTranscript) onTranscript(result.transcript);
        setHint("Voice saved");
        return result.audioId;
      } catch {
        setHint("Voice failed — try again or pick a file");
        setFailed(true);
        return null;
      } finally {
        setBusy(false);
        uploadPromiseRef.current = null;
      }
    })();
    uploadPromiseRef.current = work;
    const id = await work;
    settleStopWaiters(id);
    return id;
  }

  async function stopAndFlush(): Promise<string | null> {
    if (uploadPromiseRef.current) {
      return uploadPromiseRef.current;
    }
    if (recording && mediaRef.current) {
      return new Promise((resolve) => {
        stopWaitersRef.current.push(resolve);
        mediaRef.current?.stop();
        setRecording(false);
      });
    }
    return audioIdRef.current;
  }

  useImperativeHandle(
    ref,
    () => ({
      get recording() {
        return recording;
      },
      get busy() {
        return busy;
      },
      stopAndFlush,
    }),
    [recording, busy],
  );

  async function toggleRecord() {
    if (busy) return;
    if (recording && mediaRef.current) {
      mediaRef.current.stop();
      setRecording(false);
      return;
    }
    const mime = pickRecorderMime();
    if (!mime) {
      setHint("Recording unsupported — pick an audio file");
      fileRef.current?.click();
      return;
    }
    mimeRef.current = mime.split(";")[0];
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream, { mimeType: mime });
      chunksRef.current = [];
      rec.ondataavailable = (e) => {
        if (e.data.size) chunksRef.current.push(e.data);
      };
      rec.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        void handleBlob(new Blob(chunksRef.current, { type: mimeRef.current }));
      };
      mediaRef.current = rec;
      rec.start();
      setRecording(true);
      setHint("Listening… tap again to stop");
    } catch {
      setHint("Mic blocked — pick an audio file instead");
      fileRef.current?.click();
    }
  }

  function onFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    void handleBlob(file);
  }

  return (
    <div className="rounded-2xl border border-[var(--teal)]/25 bg-[var(--teal)]/8 px-4 py-4 sm:px-5">
      <p className="text-xs font-bold uppercase tracking-[0.16em] text-[var(--teal)]">{label}</p>
      <p className="mt-2 text-sm text-[var(--muted)] sm:text-base">
        {audioId
          ? "Clip ready — play below, or re-record / pick a file."
          : "Record on phone or laptop, or choose an audio file."}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          className={recording ? "btn-primary px-5 py-2.5 text-sm" : "btn-ghost px-5 py-2.5 text-sm"}
          disabled={busy}
          onClick={() => void toggleRecord()}
        >
          {recording ? "Stop" : audioId ? "Re-record" : "Record"}
        </button>
        <button
          type="button"
          className="btn-ghost px-5 py-2.5 text-sm"
          disabled={busy || recording}
          onClick={() => fileRef.current?.click()}
        >
          Pick file
        </button>
        {audioId ? (
          <button
            type="button"
            className="btn-ghost px-5 py-2.5 text-sm"
            disabled={busy}
            onClick={() => {
              onAudioId(null);
              audioIdRef.current = null;
              setHint("");
              setFailed(false);
            }}
          >
            Clear
          </button>
        ) : null}
      </div>
      <input
        ref={fileRef}
        type="file"
        accept="audio/*,.m4a,.mp3,.wav,.webm,.ogg,.aac"
        capture="user"
        className="hidden"
        onChange={onFile}
      />
      {hint ? (
        <p className={`mt-2 text-sm ${failed ? "text-[#e85d4c]" : "text-[var(--muted)]"}`}>{hint}</p>
      ) : null}
      {audioId && previewSrc ? (
        <audio key={audioId} controls preload="auto" className="mt-3 w-full max-w-xl" src={previewSrc} />
      ) : null}
    </div>
  );
});
