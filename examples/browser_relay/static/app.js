// Browser frontend for the Scribe SDK relay demo.
// Mode 1: MediaRecorder -> POST blob -> server does single upload.
// Mode 2: WebAudio PCM16 @16kHz -> WS -> server relays into an SDK stream.

const statusEl = document.getElementById("status");
const resultEl = document.getElementById("result");

const setStatus = (s) => (statusEl.textContent = s);
const showResult = (obj) => (resultEl.textContent = JSON.stringify(obj, null, 2));

// Poll the relay until the session reaches a terminal status.
async function pollResults(sessionId) {
  const terminal = new Set(["completed", "partial", "failed", "expired"]);
  for (let i = 0; i < 120; i++) {
    const res = await fetch(`/api/results/${sessionId}`);
    const body = await res.json();
    setStatus(`processing… (${body.status})`);
    if (terminal.has(body.status)) {
      setStatus(`done: ${body.status}`);
      showResult(body);
      return;
    }
    await new Promise((r) => setTimeout(r, 3000));
  }
  setStatus("timed out waiting for results");
}

// ----------------------------------------------------------------------------
// Mode 1 — record & upload
// ----------------------------------------------------------------------------
let mediaRecorder, recChunks = [];

document.getElementById("recStart").onclick = async () => {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  recChunks = [];
  mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
  mediaRecorder.ondataavailable = (e) => e.data.size && recChunks.push(e.data);
  mediaRecorder.onstop = async () => {
    stream.getTracks().forEach((t) => t.stop());
    const blob = new Blob(recChunks, { type: "audio/webm" });
    setStatus("uploading…");
    const form = new FormData();
    form.append("file", blob, "recording.webm");
    const res = await fetch("/api/upload", { method: "POST", body: form });
    const { session_id } = await res.json();
    await pollResults(session_id);
  };
  mediaRecorder.start();
  setStatus("recording…");
  toggle("rec", true);
};

document.getElementById("recStop").onclick = () => {
  mediaRecorder && mediaRecorder.stop();
  toggle("rec", false);
};

// ----------------------------------------------------------------------------
// Mode 2 — live stream over WebSocket
// ----------------------------------------------------------------------------
let audioCtx, sourceNode, processorNode, ws, mediaStream, streamSessionId;

document.getElementById("streamStart").onclick = async () => {
  mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });

  // Request a 16 kHz context so no manual resampling is needed.
  audioCtx = new AudioContext({ sampleRate: 16000 });
  await audioCtx.resume();
  sourceNode = audioCtx.createMediaStreamSource(mediaStream);
  processorNode = audioCtx.createScriptProcessor(4096, 1, 1);

  ws = new WebSocket(`ws://${location.host}/api/stream`);
  ws.binaryType = "arraybuffer";
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.event === "ready") {
      streamSessionId = msg.session_id;
      setStatus(`streaming… (session ${streamSessionId})`);
    }
  };

  processorNode.onaudioprocess = (e) => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const float = e.inputBuffer.getChannelData(0);
    const pcm16 = new Int16Array(float.length);
    for (let i = 0; i < float.length; i++) {
      const s = Math.max(-1, Math.min(1, float[i]));
      pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    ws.send(pcm16.buffer);
  };

  sourceNode.connect(processorNode);
  processorNode.connect(audioCtx.destination);
  toggle("stream", true);
};

document.getElementById("streamStop").onclick = async () => {
  toggle("stream", false);
  try { processorNode && processorNode.disconnect(); } catch {}
  try { sourceNode && sourceNode.disconnect(); } catch {}
  mediaStream && mediaStream.getTracks().forEach((t) => t.stop());
  if (audioCtx) await audioCtx.close();
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send("stop");
    ws.close();
  }
  if (streamSessionId) {
    setStatus("stream stopped; processing…");
    await pollResults(streamSessionId);
  }
};

function toggle(prefix, running) {
  document.getElementById(`${prefix}Start`).disabled = running;
  document.getElementById(`${prefix}Stop`).disabled = !running;
}
