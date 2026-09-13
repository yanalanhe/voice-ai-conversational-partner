// WebSocket client for the wire protocol in server/app/main.py: binary PCM
// frames upstream, JSON control upstream, and a JSON-then-binary pair
// downstream for each assistant audio clause (an `assistant_text` message
// immediately followed by the raw audio bytes it describes).

import type { ServerEvent } from "../types";

export class SessionTransport {
  private readonly ws: WebSocket;
  private pendingAudioMeta: { text: string; seq: number } | null = null;

  constructor(
    url: string,
    private readonly onEvent: (event: ServerEvent) => void,
    private readonly onOpen?: () => void,
    private readonly onClose?: () => void,
  ) {
    this.ws = new WebSocket(url);
    this.ws.binaryType = "arraybuffer";
    this.ws.onopen = () => this.onOpen?.();
    this.ws.onclose = () => this.onClose?.();
    this.ws.onmessage = (event) => this.handleMessage(event);
  }

  private handleMessage(event: MessageEvent<string | ArrayBuffer>): void {
    if (typeof event.data === "string") {
      const msg = JSON.parse(event.data) as Record<string, unknown>;
      if (msg["type"] === "assistant_text") {
        this.pendingAudioMeta = { text: msg["text"] as string, seq: msg["seq"] as number };
        return;
      }
      this.onEvent(msg as unknown as ServerEvent);
      return;
    }
    if (this.pendingAudioMeta) {
      this.onEvent({
        type: "assistant_audio",
        text: this.pendingAudioMeta.text,
        seq: this.pendingAudioMeta.seq,
        audio: event.data,
      });
      this.pendingAudioMeta = null;
    }
  }

  sendAudioFrame(pcm: ArrayBuffer): void {
    if (this.ws.readyState === WebSocket.OPEN) this.ws.send(pcm);
  }

  sendSpeechStart(): void {
    this.sendControl({ type: "speech_start" });
  }

  sendSpeechEnd(): void {
    this.sendControl({ type: "speech_end" });
  }

  private sendControl(obj: unknown): void {
    if (this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(obj));
  }

  close(): void {
    this.ws.close();
  }
}
