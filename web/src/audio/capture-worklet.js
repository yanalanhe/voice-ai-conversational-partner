// AudioWorkletProcessor runs on the audio rendering thread, not the main
// thread -- it cannot import TS or touch the DOM, so this file is plain JS,
// loaded directly as a URL (see capture.ts). Its only job: buffer the
// browser's native render-quantum callbacks (128 samples) into 20ms frames
// of 16-bit PCM and hand them to the main thread.
class CaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = [];
    this._frameSize = 320; // 20ms @ 16kHz -- must match server AudioChunk framing
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel) {
      for (let i = 0; i < channel.length; i++) {
        this._buffer.push(channel[i]);
        if (this._buffer.length >= this._frameSize) {
          this._emit();
        }
      }
    }
    return true; // keep the processor alive
  }

  _emit() {
    const frame = this._buffer.splice(0, this._frameSize);
    const pcm16 = new Int16Array(frame.length);
    for (let i = 0; i < frame.length; i++) {
      const s = Math.max(-1, Math.min(1, frame[i]));
      pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    this.port.postMessage(pcm16.buffer, [pcm16.buffer]);
  }
}

registerProcessor("capture-processor", CaptureProcessor);
