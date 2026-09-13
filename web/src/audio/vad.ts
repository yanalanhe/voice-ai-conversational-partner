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
}

export class EnergyVad {
  private speaking = false;
  private silenceMs = 0;
  private readonly threshold: number;
  private readonly hangoverMs: number;
  private readonly frameMs: number;

  constructor(
    private readonly callbacks: VadCallbacks,
    opts: VadOptions = {},
  ) {
    this.threshold = opts.threshold ?? 0.02;
    this.hangoverMs = opts.hangoverMs ?? 500;
    this.frameMs = opts.frameMs ?? 20;
  }

  onLevel(rms: number): void {
    const isLoud = rms >= this.threshold;
    if (isLoud) {
      this.silenceMs = 0;
      if (!this.speaking) {
        this.speaking = true;
        this.callbacks.onSpeechStart();
      }
      return;
    }
    if (this.speaking) {
      this.silenceMs += this.frameMs;
      if (this.silenceMs >= this.hangoverMs) {
        this.speaking = false;
        this.silenceMs = 0;
        this.callbacks.onSpeechEnd();
      }
    }
  }

  get isSpeaking(): boolean {
    return this.speaking;
  }
}
