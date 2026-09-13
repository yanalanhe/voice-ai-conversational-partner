// Wire-format types mirroring server/app/session/events.py + main.py's
// _event_to_json. Kept in one file so a server-side field rename is a single
// obvious diff away from a client-side compile error.

export interface TurnSummary {
  turn_id: string;
  ttfa_ms: number | null;
  stages: Record<string, number>;
  barged_in: boolean;
}

export type ServerEvent =
  | { type: "transcript"; text: string }
  | { type: "assistant_audio"; text: string; seq: number; audio: ArrayBuffer }
  | { type: "turn_complete"; summary: TurnSummary }
  | { type: "turn_interrupted"; summary: TurnSummary };
