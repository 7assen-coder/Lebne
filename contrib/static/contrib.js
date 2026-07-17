(() => {
  const status = document.getElementById("voice-status");
  const textArea = document.getElementById("rewrite_text");
  const audioPath = document.getElementById("audio_path");
  const recordBtn = document.getElementById("btn-record");
  const fileInput = document.getElementById("audio_file");
  if (!textArea) return;

  const localeInput = () =>
    document.querySelector('input[name="target_locale"]:checked')?.value || "fr";

  async function sendAudio(blob, filename) {
    if (status) status.textContent = "Transcribing…";
    const fd = new FormData();
    fd.append("target_locale", localeInput());
    fd.append("audio", blob, filename);
    const res = await fetch("/contrib/stt", { method: "POST", body: fd });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      if (status) status.textContent = data.detail || "STT failed";
      return;
    }
    if (data.text) textArea.value = data.text;
    if (data.audio_path && audioPath) audioPath.value = data.audio_path;
    if (status) status.textContent = "Draft filled — edit before submit";
  }

  if (fileInput) {
    fileInput.addEventListener("change", async () => {
      const file = fileInput.files?.[0];
      if (!file) return;
      await sendAudio(file, file.name);
      fileInput.value = "";
    });
  }

  if (!recordBtn || recordBtn.disabled) return;

  let mediaRecorder = null;
  let chunks = [];

  recordBtn.addEventListener("mousedown", async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      chunks = [];
      mediaRecorder = new MediaRecorder(stream);
      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size) chunks.push(e.data);
      };
      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunks, { type: "audio/webm" });
        await sendAudio(blob, "recording.webm");
      };
      mediaRecorder.start();
      if (status) status.textContent = "Recording… release to stop";
      recordBtn.classList.add("is-recording");
    } catch (err) {
      if (status) status.textContent = "Microphone blocked";
    }
  });

  const stop = () => {
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
      recordBtn.classList.remove("is-recording");
    }
  };
  recordBtn.addEventListener("mouseup", stop);
  recordBtn.addEventListener("mouseleave", stop);
  recordBtn.addEventListener("touchend", stop);
})();
