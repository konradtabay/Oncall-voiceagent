"""Scripted demo: a fake terminal, then the real call, then a spoken success."""

from __future__ import annotations

import threading

# Spoken opener is compact; full text is what the voice agent uses for Q&A.
DEMO_PROJECT = (
    "Organization: Northern Lattice AI, a sovereign Canadian AI company (HQ Toronto, "
    "GPU regions in Montréal and BC). Mission: train and operate domestic foundation "
    "and specialty models on Canadian infrastructure so sensitive data and weights never "
    "leave the country. Platform: LatticeTrain, the in-house distributed training "
    "orchestrator for pretraining, fine-tunes, and eval — not a wrapper on US APIs. "
    "Current flagship line includes NorthStar-Encode, brain encoding models that map "
    "neural recordings (iEEG, ECoG, EEG) to latent state for health and BCI research. "
    "Flow: datasets land in sovereign object storage, preprocessing and tokenization "
    "workers write shards, GPU trainers run contrastive and temporal VAE encoding "
    "objectives, checkpoints go to the Canadian model registry with residency tags. "
    "Redis stream training:encode queues encode-model jobs (AX-14 fine-tune, sweeps, "
    "exports). train-runner is the worker fleet on that stream (group "
    "training:encode:workers). Deploy 7a updated 512-d latent schema checks. Health "
    ":8080 is train-runner liveness. Impact if down: sovereign AX-14 retrain stalls, "
    "internal eval cannot refresh, and partner pilots wait on Canadian-hosted weights."
)
DEMO_SUMMARY = (
    "train-runner crash after Redis WRONGTYPE on training:encode:cursor"
)
DEMO_LOGS = (
    "2026-09-26T23:48:11Z train-runner-3 pid=48921 stderr: "
    "redis.exceptions.ResponseError: WRONGTYPE Operation against a key holding "
    "the wrong kind of value — key training:encode:cursor is type string, expected "
    "stream | consumer group training:encode:workers stalled 4m12s queue_depth=847 | "
    "GET /health :8080 connection refused exit=1"
)
DEMO_BRIEF = (
    "Production worker train-runner-3 (PID 48921) crashed right after deploy 7a on "
    "LatticeTrain (NorthStar-Encode track). The sidecar passed health checks but the "
    "main process died when it tried to read Redis stream training:encode for the "
    "sovereign AX-14 encoding fine-tune on Canadian GPUs. "
    "Stderr shows redis.exceptions.ResponseError: WRONGTYPE on key "
    "training:encode:cursor — that key is a STRING but the worker expects a STREAM "
    "(XREADGROUP). Likely cause: someone ran redis-cli SET training:encode:cursor "
    "during the 18:32 hotfix. Queue depth is 847 encode jobs, consumers stalled for "
    "over four minutes, and https://example.com/health on port 8080 is connection "
    "refused because train-runner is down."
)
DEMO_FIX = (
    "On the Redis primary: DEL training:encode:cursor (or TYPE + DEL if unsure), "
    "recreate the stream cursor with XGROUP CREATE training:encode workers $ MKSTREAM "
    "if the group is missing, then systemctl restart train-runner. Confirm with "
    "XINFO STREAM training:encode, XINFO GROUPS training:encode, and GET /health "
    "returning 200. If the cursor seed is gone, roll back deploy to 6f before restart."
)
DEMO_OPENING_ISSUE = (
    "train-runner-3 died on a Redis WRONGTYPE — key training:encode:cursor is a string, "
    "not a stream, so NorthStar-Encode jobs for AX-14 are stuck."
)
DEMO_OPENING_FIX = (
    "Delete that key, recreate the stream consumer group, and restart train-runner."
)
DEMO_SUCCESS = "Fix complete, health is back. Chat soon."

DEMO_ERROR_LINES = (
    "train-runner-3 exit 1 (signal SIGTERM after crash loop)",
    "stderr: WRONGTYPE key training:encode:cursor (got string, want stream)",
    "redis: XREADGROUP training:encode:workers blocked",
    "queue_depth=847 AX-14 encode jobs stalled 4m12s",
    "GET /health :8080 connection refused",
    "last deploy: 7a (18:29 UTC) manual SET on cursor @ 18:32",
    "on call",
    "ringing maintainer",
)
DEMO_WORK_LINES = (
    "maintainer confirmed execute",
    "kubectl logs train-runner-3 --previous | grep WRONGTYPE",
    "redis-cli TYPE training:encode:cursor -> string",
    "redis-cli DEL training:encode:cursor",
    "XGROUP CREATE training:encode workers $ MKSTREAM",
    "systemctl restart train-runner",
)
DEMO_RECOVER_LINES = (
    "train-runner-3 pid=49102 listening :8080",
    "XINFO STREAM training:encode entries=1",
    "GET /health 200 4ms",
    "encode queue_depth=12 draining",
    "AX-14 checkpoint job resumed",
)

_STAGES = frozenset({"healthy", "error", "fixing", "success"})


class DemoBoard:
    def __init__(self) -> None:
        self._stage = "healthy"
        self._seq = 0
        self._sms_seq = 0
        self._epoch = 0
        self._lines: list[dict[str, str | int]] = []
        self._messages: list[dict[str, str | int]] = []
        self._lock = threading.Lock()

    def stage(self) -> str:
        with self._lock:
            return self._stage

    def set_stage(self, stage: str) -> None:
        if stage not in _STAGES:
            return
        with self._lock:
            self._stage = stage

    def push(self, text: str, tone: str, *, alert: bool = False) -> None:
        with self._lock:
            self._seq += 1
            self._lines.append(
                {"id": self._seq, "text": text, "tone": tone, "alert": alert}
            )
            self._lines = self._lines[-48:]

    def lines(self) -> list[dict[str, str | int]]:
        with self._lock:
            return list(self._lines)

    def push_sms(self, body: str, kind: str) -> None:
        with self._lock:
            self._sms_seq += 1
            self._messages.append(
                {"id": self._sms_seq, "body": body, "kind": kind}
            )
            self._messages = self._messages[-8:]

    def messages(self) -> list[dict[str, str | int]]:
        with self._lock:
            return list(self._messages)

    def epoch(self) -> int:
        with self._lock:
            return self._epoch

    def clear(self) -> None:
        with self._lock:
            self._lines.clear()
            self._messages.clear()
            self._epoch += 1


PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>worker</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  html, body { margin: 0; height: 100%; background: #0c0d10; color: #d7dbe2; font-family: ui-sans-serif, system-ui, sans-serif; }
  main { min-height: 100%; display: flex; align-items: center; justify-content: center; padding: 24px; }
  .frame { position: relative; width: min(1104px, calc(100vw - 48px)); }
  .chrome { position: relative; display: flex; align-items: center; gap: 10px; padding: 12px 17px; background: #1a1c22; border: 1px solid #2a2e38; border-bottom: 0; border-radius: 14px 14px 0 0; }
  .dot { width: 12px; height: 12px; border-radius: 50%; background: #3a3f4b; }
  .title { margin-left: 10px; background: none; border: 0; padding: 0; font: inherit; font-size: 16px; letter-spacing: 0.04em; color: #9aa3b2; text-align: left; }
  .title.armed { cursor: pointer; }
  .title.armed:hover { color: #c5ccd8; }
  .log { margin: 0; width: 100%; aspect-ratio: 2 / 1; height: auto; overflow-x: hidden; overflow-y: auto; padding: 22px 24px 34px; background: #07080b; border: 1px solid #2a2e38; border-radius: 0 0 14px 14px; font: 18px/1.55 ui-monospace, SFMono-Regular, Menlo, monospace; color: #d7dbe2; }
  .log .line { display: block; min-height: 1.55em; white-space: pre-wrap; word-break: break-word; color: #d7dbe2; }
  .log .line.ok { color: #3dff86 !important; }
  .log .line.bad { color: #ff5a5a !important; }
  .confirm { position: absolute; left: 14px; top: 46px; z-index: 20; width: 264px; padding: 14px; background: #16181e; border: 1px solid #343846; border-radius: 10px; box-shadow: 0 12px 40px rgba(0,0,0,0.45); }
  .confirm p { margin: 0 0 12px; font-size: 16px; color: #d7dbe2; }
  .confirm button { background: #222632; color: #e8edf5; border: 1px solid #343846; border-radius: 7px; padding: 7px 12px; font-size: 16px; cursor: pointer; }
  .confirm button.run { background: #12351f; border-color: #2f8f52; color: #3dff86; font-weight: 600; }
  .confirm button + button { margin-left: 8px; }
  .text-drop { position: fixed; top: 16px; right: 16px; width: min(340px, calc(100vw - 32px)); z-index: 50; transform: translate3d(28px, -130%, 0); opacity: 0; pointer-events: none; filter: blur(2px); transition: transform 0.55s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.35s ease, filter 0.35s ease; }
  .text-drop.show { transform: translate3d(0, 0, 0); opacity: 1; pointer-events: auto; filter: none; }
  .text-card { display: flex; gap: 12px; align-items: flex-start; background: rgba(36, 36, 38, 0.94); border-radius: 22px; padding: 12px 14px 14px; box-shadow: 0 16px 40px rgba(0,0,0,0.45); font-family: ui-sans-serif, system-ui, sans-serif; backdrop-filter: blur(16px); }
  .im-icon { flex: 0 0 auto; width: 38px; height: 38px; border-radius: 9px; background: linear-gradient(180deg, #62e56a, #2ebd4f); position: relative; }
  .im-icon::after { content: ""; position: absolute; left: 8px; top: 10px; width: 22px; height: 16px; border-radius: 8px; background: #fff; }
  .im-icon::before { content: ""; position: absolute; left: 12px; top: 22px; width: 8px; height: 8px; background: #fff; transform: rotate(45deg); z-index: 1; }
  .im-copy { min-width: 0; flex: 1; }
  .im-top { display: flex; justify-content: space-between; gap: 8px; font-size: 12px; letter-spacing: 0.02em; color: #a1a1a6; text-transform: uppercase; }
  .im-from { margin-top: 1px; font-size: 15px; font-weight: 650; color: #f5f5f7; }
  .text-card p { margin: 2px 0 0; font-size: 15px; line-height: 1.35; color: #f5f5f7; white-space: pre-line; }
</style>
</head>
<body>
<main>
  <div class="frame">
    <div id="textDrop" class="text-drop" hidden>
      <div class="text-card">
        <div class="im-icon" aria-hidden="true"></div>
        <div class="im-copy">
          <div class="im-top"><span>Messages</span><span>now</span></div>
          <div class="im-from">On-call</div>
          <p id="textBody"></p>
        </div>
      </div>
    </div>
    <div id="term" class="healthy">
      <div class="chrome">
        <span class="dot"></span><span class="dot"></span><span class="dot"></span>
        <button id="launcher" class="title armed" type="button">train-runner · lattice-train</button>
        <div id="confirm" class="confirm" hidden>
          <p>Run the incident?</p>
          <button id="yes" class="run" type="button">Run</button>
          <button id="no" type="button">Cancel</button>
        </div>
      </div>
      <div id="log" class="log" aria-live="polite"></div>
    </div>
  </div>
</main>
<script>
const healthyLines = [
  "train-runner-3 listening on :8080",
  "GET /health 200 4ms",
  "XREADGROUP training:encode ok lag=0",
  "AX-14 northstar-encode job idle (ca-central)",
  "deploy 7a checked out main",
  "heartbeat ok",
  "encode queue_depth 0",
];
const term = document.getElementById("term");
const log = document.getElementById("log");
const launcher = document.getElementById("launcher");
const confirmBox = document.getElementById("confirm");
const params = new URLSearchParams(location.search);
const painted = params.get("stage");
let stage = "healthy";
let logEpoch = 0;
let cursor = 0;
let running = false;
const drawn = new Set();
const seenSms = new Set();
const textDrop = document.getElementById("textDrop");
const textBody = document.getElementById("textBody");
let textTimer = 0;
let audioCtx = null;
let nextBeep = 0;

function armAudio() {
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (!Ctx) return;
  if (!audioCtx) audioCtx = new Ctx();
  if (audioCtx.state === "suspended") audioCtx.resume();
}

function playChime() {
  if (!audioCtx || audioCtx.state !== "running") return;
  [784, 988, 1318].forEach((freq, index) => {
    const start = audioCtx.currentTime + index * 0.07;
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(freq, start);
    gain.gain.setValueAtTime(0.0001, start);
    gain.gain.exponentialRampToValueAtTime(0.08, start + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.32);
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    osc.start(start);
    osc.stop(start + 0.34);
  });
}

function playError() {
  if (!audioCtx || audioCtx.state !== "running") return;
  const start = Math.max(audioCtx.currentTime, nextBeep);
  nextBeep = start + 0.22;
  const osc = audioCtx.createOscillator();
  const gain = audioCtx.createGain();
  osc.type = "square";
  osc.frequency.setValueAtTime(640, start);
  osc.frequency.exponentialRampToValueAtTime(160, start + 0.16);
  gain.gain.setValueAtTime(0.0001, start);
  gain.gain.exponentialRampToValueAtTime(0.07, start + 0.015);
  gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.18);
  osc.connect(gain);
  gain.connect(audioCtx.destination);
  osc.start(start);
  osc.stop(start + 0.2);
}

function formatTs(ts) {
  return new Date(ts).toISOString().slice(11, 19);
}

function addLocal(text, tone, ts) {
  const row = document.createElement("div");
  row.className = "line " + (tone === "ok" ? "ok" : "bad");
  row.textContent = formatTs(ts || Date.now()) + "  " + text;
  log.appendChild(row);
  while (log.childElementCount > 48) log.removeChild(log.firstElementChild);
  log.scrollTop = log.scrollHeight;
}

function ingestLines(lines, epoch) {
  const stamp = epoch === undefined || epoch === null ? logEpoch : epoch;
  for (const line of lines || []) {
    const key = String(stamp) + ":" + String(line.id);
    if (drawn.has(key)) continue;
    drawn.add(key);
    addLocal(line.text, line.tone === "ok" ? "ok" : "bad", Date.now());
    if (line.alert) playError();
  }
}

function seedHealthyIfEmpty() {
  if (log.childElementCount) return;
  const base = Date.now();
  for (let i = 14; i >= 1; i -= 1) {
    addLocal(healthyLines[cursor % healthyLines.length], "ok", base - i * 800);
    cursor += 1;
  }
}

function setChrome(next) {
  stage = next;
  term.className = next;
  const quiet = next === "healthy" || next === "success";
  if (quiet && !running) launcher.classList.add("armed");
  else launcher.classList.remove("armed");
  if (!quiet) confirmBox.hidden = true;
}

function showText(body) {
  armAudio();
  playChime();
  textBody.textContent = body;
  textDrop.hidden = false;
  requestAnimationFrame(() => textDrop.classList.add("show"));
  clearTimeout(textTimer);
  textTimer = setTimeout(() => {
    textDrop.classList.remove("show");
    setTimeout(() => { if (!textDrop.classList.contains("show")) textDrop.hidden = true; }, 400);
  }, 9000);
}

function ingestMessages(messages, epoch) {
  const stamp = epoch === undefined || epoch === null ? logEpoch : epoch;
  for (const message of messages || []) {
    const key = String(stamp) + ":" + String(message.id);
    if (seenSms.has(key)) continue;
    seenSms.add(key);
    showText(message.body);
  }
}

function paint(next) {
  if (next === stage) return;
  setChrome(next);
}

async function refresh() {
  if (painted) return;
  try {
    const res = await fetch("/demo/state");
    const body = await res.json();
    if (body.epoch !== undefined && body.epoch !== null) logEpoch = body.epoch;
    const next = body.stage || "healthy";
    if (next === "healthy" || next === "success") running = false;
    paint(next);
    ingestLines(body.lines, body.epoch);
    ingestMessages(body.messages, body.epoch);
  } catch (err) {
    /* keep the last frame */
  }
}

async function trigger() {
  if (running || painted) return;
  armAudio();
  running = true;
  confirmBox.hidden = true;
  launcher.classList.remove("armed");
  try {
    const res = await fetch("/demo/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    if (!res.ok) {
      running = false;
      launcher.classList.add("armed");
    } else {
      await refresh();
    }
  } catch (err) {
    running = false;
    launcher.classList.add("armed");
  }
}

function openConfirm() {
  if (stage !== "healthy" && stage !== "success") return;
  if (running) return;
  confirmBox.hidden = false;
}

launcher.addEventListener("click", openConfirm);
document.getElementById("yes").addEventListener("click", (event) => {
  event.stopPropagation();
  trigger();
});
document.getElementById("no").addEventListener("click", (event) => {
  event.stopPropagation();
  confirmBox.hidden = true;
});
confirmBox.addEventListener("click", (event) => event.stopPropagation());

const Speech = window.SpeechRecognition || window.webkitSpeechRecognition;
if (Speech && !painted) {
  const rec = new Speech();
  rec.continuous = true;
  rec.interimResults = false;
  rec.onresult = (event) => {
    const said = event.results[event.results.length - 1][0].transcript.toLowerCase();
    if (said.includes("run it") && (stage === "healthy" || stage === "success") && !running) {
      trigger();
    }
  };
  rec.onend = () => rec.start();
  rec.start();
}

seedHealthyIfEmpty();
if (painted === "error" || painted === "fixing" || painted === "success") setChrome(painted);
refresh();
setInterval(() => {
  if (stage !== "healthy" && stage !== "success") return;
  addLocal(healthyLines[cursor % healthyLines.length], "ok", Date.now());
  cursor += 1;
}, 900);
setInterval(refresh, 400);
</script>
</body>
</html>
"""
