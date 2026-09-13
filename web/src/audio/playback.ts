// Jitter-buffered playback: each incoming PCM16 clause is scheduled to start
// exactly when the previous one ends (never earlier, never with a gap unless
// the network genuinely underruns), which is what "jitter buffer" means here
// -- there is no separate ring buffer, the AudioContext's own scheduling
// clock (`nextStartTime`) does that job.
//
// `flush()` is the local half of barge-in (LATENCY.md 5.4, PRD VP-6): it
// stops all scheduled/playing sources immediately, without waiting for the
// server to confirm the interruption. The server-side cancellation (via
// speech_start) still happens, but the learner hears silence the instant
// their own VAD fires, not after a round trip.

export class JitterPlayback {
  private readonly ctx: AudioContext;
  private nextStartTime = 0;
  private sources: AudioBufferSourceNode[] = [];

  constructor(sampleRate = 16000) {
    this.ctx = new AudioContext({ sampleRate });
  }

  enqueue(pcm: ArrayBuffer): void {
    const int16 = new Int16Array(pcm);
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) {
      float32[i] = (int16[i] ?? 0) / 32768;
    }

    const buffer = this.ctx.createBuffer(1, float32.length, this.ctx.sampleRate);
    buffer.copyToChannel(float32, 0);

    const source = this.ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(this.ctx.destination);

    const startAt = Math.max(this.ctx.currentTime, this.nextStartTime);
    source.start(startAt);
    this.nextStartTime = startAt + buffer.duration;

    this.sources.push(source);
    source.onended = () => {
      this.sources = this.sources.filter((s) => s !== source);
    };
  }

  flush(): void {
    for (const source of this.sources) {
      try {
        source.stop();
      } catch {
        // already stopped/ended -- fine, this is a best-effort flush
      }
    }
    this.sources = [];
    this.nextStartTime = this.ctx.currentTime;
  }

  get isPlaying(): boolean {
    return this.sources.length > 0;
  }

  async resume(): Promise<void> {
    // Browsers suspend AudioContext until a user gesture; called from the
    // Connect button handler.
    if (this.ctx.state === "suspended") await this.ctx.resume();
  }
}
