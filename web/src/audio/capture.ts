// Main-thread side of audio capture. The AudioContext is created at 16kHz
// directly -- getUserMedia's track is resampled by the browser to match, so
// no manual resampling code is needed here (see capture-worklet.js for why
// framing happens on the worklet side instead).

export interface CaptureHandle {
  stop: () => void;
}

export async function startCapture(
  onFrame: (pcm: ArrayBuffer) => void,
  onLevel: (rms: number) => void,
): Promise<CaptureHandle> {
  const audioContext = new AudioContext({ sampleRate: 16000 });
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });

  const workletUrl = new URL("./capture-worklet.js", import.meta.url);
  await audioContext.audioWorklet.addModule(workletUrl);

  const source = audioContext.createMediaStreamSource(stream);
  const node = new AudioWorkletNode(audioContext, "capture-processor");

  node.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
    const pcm = event.data;
    // onLevel first: it may flip the VAD into "speaking" on this very frame
    // (firing onSpeechStart), and onFrame's caller gates sending on that
    // same-frame result -- reversing the order would silently drop the
    // frame that triggered speech detection.
    onLevel(rmsOf(new Int16Array(pcm)));
    onFrame(pcm);
  };

  // Deliberately not connected to `audioContext.destination` -- capturing the
  // mic must never loop it back out of the speakers.
  source.connect(node);

  return {
    stop: () => {
      source.disconnect();
      node.disconnect();
      for (const track of stream.getTracks()) track.stop();
      void audioContext.close();
    },
  };
}

function rmsOf(samples: Int16Array): number {
  let sumSquares = 0;
  for (let i = 0; i < samples.length; i++) {
    const s = samples[i]! / 32768;
    sumSquares += s * s;
  }
  return Math.sqrt(sumSquares / samples.length);
}
