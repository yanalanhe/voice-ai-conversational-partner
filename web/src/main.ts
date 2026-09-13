import { startCapture, type CaptureHandle } from "./audio/capture";
import { EnergyVad } from "./audio/vad";
import { JitterPlayback } from "./audio/playback";
import { SessionTransport } from "./net/transport";
import { Hud } from "./ui/hud";
import type { ServerEvent } from "./types";

const hudRootEl = document.querySelector<HTMLElement>("#hud");
const connectBtnEl = document.querySelector<HTMLButtonElement>("#connect");
if (!hudRootEl || !connectBtnEl) throw new Error("index.html is missing #hud or #connect");
// Rebind to a definitely-non-null const: TS does not carry the guard above's
// narrowing into the nested closures below.
const hudRoot: HTMLElement = hudRootEl;
const connectBtn: HTMLButtonElement = connectBtnEl;

const hud = new Hud(hudRoot);

let capture: CaptureHandle | null = null;
let transport: SessionTransport | null = null;
const playback = new JitterPlayback();

function wsUrl(): string {
  // VITE_WS_URL is baked in at build time (Vite inlines import.meta.env.*
  // statically). It's needed whenever the client isn't served through Vite's
  // dev-server proxy (vite.config.ts's /ws rewrite) -- a `vite preview` or
  // any static production build has no such proxy, so same-origin would try
  // to reach a WebSocket server on the frontend's own port instead of the
  // backend's. Falls back to same-origin for local `npm run dev`.
  const configured = import.meta.env.VITE_WS_URL;
  const base = configured ?? `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/ws/session`;

  // AccessCodeGuard on the backend (server/app/main.py) reads this from the
  // `code` query param and closes the connection before accept() if it's
  // missing or wrong -- required whenever DEMO_ACCESS_CODE is set server-side,
  // i.e. any public deployment. Unset locally, where the guard is disabled.
  const code = import.meta.env.VITE_DEMO_ACCESS_CODE;
  if (!code) return base;
  const url = new URL(base);
  url.searchParams.set("code", code);
  return url.toString();
}

async function connect(): Promise<void> {
  connectBtn.disabled = true;
  hud.setStatus("connecting...");
  await playback.resume();

  const vad = new EnergyVad({
    onSpeechStart: () => {
      // Local barge-in: stop audio the instant WE detect speech, before the
      // server even knows -- see playback.ts docstring.
      if (playback.isPlaying) playback.flush();
      transport?.sendSpeechStart();
    },
    onSpeechEnd: () => transport?.sendSpeechEnd(),
  });

  transport = new SessionTransport(
    wsUrl(),
    (event: ServerEvent) => {
      switch (event.type) {
        case "transcript":
          hud.addLine("You", event.text);
          break;
        case "assistant_audio":
          hud.addLine("Agent", event.text);
          playback.enqueue(event.audio);
          break;
        case "turn_complete":
          hud.setLatency(event.summary);
          break;
        case "turn_interrupted":
          hud.setLatency(event.summary);
          hud.markInterrupted();
          break;
        case "no_speech":
          hud.markNoSpeech();
          break;
      }
    },
    () => hud.setStatus("connected -- speak whenever you're ready"),
    () => {
      hud.setStatus("disconnected");
      connectBtn.disabled = false;
      connectBtn.textContent = "Connect";
    },
  );

  capture = await startCapture(
    // Gated on the VAD's current classification of *this* frame (capture.ts
    // calls onLevel before onFrame), not sent unconditionally -- otherwise
    // every silent moment between utterances gets queued server-side too,
    // since the server has no independent way to tell speech from silence.
    // See orchestrator.py's audio queue: it only resets between turns, so
    // anything sent while not actually speaking pollutes the next utterance.
    (pcm) => {
      if (vad.isSpeaking) transport?.sendAudioFrame(pcm);
    },
    (rms) => vad.onLevel(rms),
  );

  connectBtn.disabled = false;
  connectBtn.textContent = "Disconnect";
}

function disconnect(): void {
  capture?.stop();
  capture = null;
  transport?.close();
  transport = null;
  playback.flush();
  hud.setStatus("disconnected");
  connectBtn.textContent = "Connect";
}

connectBtn.addEventListener("click", () => {
  if (transport) {
    disconnect();
  } else {
    connect().catch((err: unknown) => {
      console.error(err);
      hud.setStatus(`error: ${err instanceof Error ? err.message : String(err)}`);
      connectBtn.disabled = false;
    });
  }
});
