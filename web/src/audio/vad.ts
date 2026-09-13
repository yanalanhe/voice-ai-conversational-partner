// Energy-based endpointing, run client-side so the barge-in signal (and the
// local playback flush that rides on it) does not wait on a server
// round-trip -- see PRD VP-3/VP-6 and LATENCY.md 5.4. This is intentionally
// the simplest thing that could work: a level threshold with hangover. Level
// crossing is checked once per capture frame (20ms).

export interface VadCallbacks {
  onSpeechStart: () => void;
  onSpeechEnd: () => void;
}

export interface VadOptions {
  /** RMS (0..1) above which a frame counts as speech. */
  threshold?: number;
  /** Sustained silence, in ms, before declaring speech has ended. Matches the
   * PRD's default silence threshold (VP-3); level policies can override this
   * later for adaptive endpointing by proficiency level. */
  hangoverMs?: number;
  /** Duration represented by one onLevel() call. Must match the capture
   * worklet's frame size (320 samples @ 16kHz = 20ms). */
  frameMs?: number;
  /** Hard ceiling on one utterance's length, in ms. Intermittent background
   * noise can keep re-triggering "loud" frames indefinitely, resetting the
   * silence hangover before it ever completes -- without this, a noisy room
   * produces an unbounded recording (observed: 41s, 75s buffers in
   * production) that real STT then fails to recognize at all, since a
   * single-utterance recognizer expects one utterance, not a minute of
   * audio. Forces speech_end regardless of instantaneous level once hit. */
  maxSpeechMs?: number;
}

export class EnergyVad {
  private speaking = false;
  private silenceMs = 0;
  private speechMs = 0;
  private readonly threshold: number;
  private readonly hangoverMs: number;
  private readonly frameMs: number;
  private readonly maxSpeechMs: number;

  constructor(
    private readonly callbacks: VadCallbacks,
    opts: VadOptions = {},
  ) {
    this.threshold = opts.threshold ?? 0.02;
    // 500ms (the PRD VP-3 default) reads natural mid-sentence thinking-pauses
    // as end-of-utterance for real spontaneous speech, fragmenting turns and
    // triggering spurious barge-in on the agent's own in-flight reply
    // (observed in production once real STT/LLM replaced the mocks, which
    // never paused). 900ms trades a bit of endpointing latency for fewer
    // false completions.
    this.hangoverMs = opts.hangoverMs ?? 900;
    this.frameMs = opts.frameMs ?? 20;
    this.maxSpeechMs = opts.maxSpeechMs ?? 8000;
  }

  onLevel(rms: number): void {
    const isLoud = rms >= this.threshold;
    if (isLoud) {
      this.silenceMs = 0;
      if (!this.speaking) {
        this.speaking = true;
        this.speechMs = 0;
        this.callbacks.onSpeechStart();
        return;
      }
    }
    if (this.speaking) {
      this.speechMs += this.frameMs;
      if (this.speechMs >= this.maxSpeechMs) {
        this.speaking = false;
        this.silenceMs = 0;
        this.callbacks.onSpeechEnd();
        return;
      }
      if (!isLoud) {
        this.silenceMs += this.frameMs;
        if (this.silenceMs >= this.hangoverMs) {
          this.speaking = false;
          this.silenceMs = 0;
          this.callbacks.onSpeechEnd();
        }
      }
    }
  }

  get isSpeaking(): boolean {
    return this.speaking;
  }
}
