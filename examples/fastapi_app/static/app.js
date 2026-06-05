// Browser frontend for the Scribe SDK demo.
//
// Chunked flow (steps kept separate):
//   1. POST /api/sessions                  -> session_id
//   2. POST /api/sessions/{id}/audio       -> SDK VADs the file, uploads chunks
//   3. POST /api/sessions/{id}/end         -> end the session
//   4. GET  /api/sessions/{id}/results     -> poll every 1s until terminal
//
// Live stream flow: WS /api/stream with raw PCM16 @16kHz frames, then poll.

const statusEl = document.getElementById("status");
const resultEl = document.getElementById("result");
const sessionIdEl = document.getElementById("sessionId");

const setStatus = (s) => (statusEl.textContent = s);
const showResult = (obj) => (resultEl.textContent = JSON.stringify(obj, null, 2));
const $ = (id) => document.getElementById(id);

let sessionId = null;

// Poll the relay every 1s until the session reaches a terminal status.
async function pollResults(sid) {
  const terminal = new Set(["completed", "partial", "failed", "expired"]);
  for (let i = 0; i < 600; i++) {
    const res = await fetch(`/api/sessions/${sid}/results`);
    const body = await res.json();
    setStatus(`processing… (${body.status})`);
    if (terminal.has(body.status)) {
      setStatus(`done: ${body.status}`);
      showResult(body);
      return;
    }
    await new Promise((r) => setTimeout(r, 1000)); // wait 1s (client-side)
  }
  setStatus("timed out waiting for results");
}

// ----------------------------------------------------------------------------
// Chunked flow
// ----------------------------------------------------------------------------
function setChunkedEnabled(haveSession) {
  $("fileInput").disabled = !haveSession;
  $("uploadFile").disabled = !haveSession;
  $("recStart").disabled = !haveSession;
  $("endSession").disabled = !haveSession;
}

$("startSession").onclick = async () => {
  setStatus("starting session…");
  const res = await fetch("/api/sessions", { method: "POST" });
  const body = await res.json();
  sessionId = body.session_id;
  sessionIdEl.textContent = sessionId;
  setChunkedEnabled(true);
  showResult("—");
  setStatus("session started — upload a file or record from the mic");
};

$("uploadFile").onclick = async () => {
  const file = $("fileInput").files[0];
  if (!file || !sessionId) return;
  setStatus(`uploading & VADing ${file.name}…`);
  const form = new FormData();
  form.append("file", file, file.name);
  const res = await fetch(`/api/sessions/${sessionId}/audio`, { method: "POST", body: form });
  const body = await res.json();
  setStatus(`uploaded ${body.chunks_uploaded} chunk(s) — ${body.total_chunks} total. Add more or end.`);
};

$("endSession").onclick = async () => {
  if (!sessionId) return;
  setStatus("ending session…");
  await fetch(`/api/sessions/${sessionId}/end`, { method: "POST" });
  setChunkedEnabled(false);
  const sid = sessionId;
  sessionId = null;
  await pollResults(sid);
};

// Mic recording -> blob -> same /audio endpoint (the SDK VADs it server-side).
let mediaRecorder, recChunks = [];

$("recStart").onclick = async () => {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  recChunks = [];
  mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
  mediaRecorder.ondataavailable = (e) => e.data.size && recChunks.push(e.data);
  mediaRecorder.onstop = async () => {
    stream.getTracks().forEach((t) => t.stop());
    const blob = new Blob(recChunks, { type: "audio/webm" });
    setStatus("uploading & VADing recording…");
    const form = new FormData();
    form.append("file", blob, "recording.webm");
    const res = await fetch(`/api/sessions/${sessionId}/audio`, { method: "POST", body: form });
    const body = await res.json();
    setStatus(`uploaded ${body.chunks_uploaded} chunk(s) — ${body.total_chunks} total. Add more or end.`);
  };
  mediaRecorder.start();
  setStatus("recording…");
  $("recStart").disabled = true;
  $("recStop").disabled = false;
};

$("recStop").onclick = () => {
  mediaRecorder && mediaRecorder.stop();
  $("recStart").disabled = false;
  $("recStop").disabled = true;
};

// ----------------------------------------------------------------------------
// Live stream flow
// ----------------------------------------------------------------------------
let audioCtx, sourceNode, processorNode, ws, mediaStream, streamSessionId;

$("streamStart").onclick = async () => {
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
  $("streamStart").disabled = true;
  $("streamStop").disabled = false;
};

$("streamStop").onclick = async () => {
  $("streamStart").disabled = false;
  $("streamStop").disabled = true;
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
