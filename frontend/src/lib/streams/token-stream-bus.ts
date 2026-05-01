/**
 * S14-F3c: Token-delta event bus.
 *
 * The SSE pipeline (`generateApplicationModules` in `lib/firestore/ops.ts`)
 * publishes raw `token_delta` frames from the backend via `publishTokenDelta`.
 * UI components subscribe through `useTokenStream(stage, documentKind)` and
 * paint live tokens into the workspace document preview.
 *
 * Design notes:
 *  - In-memory only — the bus is recreated on every page load. Sequence
 *    numbers therefore must reset whenever a new generation starts; we
 *    expose `resetTokenStream(stage, documentKind)` for that.
 *  - We accumulate the buffer per (stage, document_kind) so a subscriber
 *    that mounts mid-stream still sees everything generated so far.
 *  - Out-of-order deltas (caused by SSE coalescing under backpressure) are
 *    inserted by sequence number; gaps are tolerated and rendered as soon
 *    as the missing chunks arrive.
 */

export interface TokenDeltaPayload {
  stage: string;
  document_kind: string;
  delta: string;
  sequence: number;
}

type Listener = (buffer: string, payload: TokenDeltaPayload) => void;

interface StreamState {
  /** Accumulated text in sequence order. */
  buffer: string;
  /** Highest contiguous sequence we have rendered. */
  nextSequence: number;
  /** Out-of-order deltas waiting for missing predecessors. */
  pending: Map<number, string>;
  listeners: Set<Listener>;
}

const streams = new Map<string, StreamState>();

function keyFor(stage: string, documentKind: string): string {
  return `${stage}::${documentKind}`;
}

function getState(stage: string, documentKind: string): StreamState {
  const key = keyFor(stage, documentKind);
  let state = streams.get(key);
  if (!state) {
    state = { buffer: "", nextSequence: 0, pending: new Map(), listeners: new Set() };
    streams.set(key, state);
  }
  return state;
}

export function getTokenStreamBuffer(stage: string, documentKind: string): string {
  return streams.get(keyFor(stage, documentKind))?.buffer ?? "";
}

export function subscribeTokenStream(
  stage: string,
  documentKind: string,
  listener: Listener,
): () => void {
  const state = getState(stage, documentKind);
  state.listeners.add(listener);
  return () => {
    state.listeners.delete(listener);
  };
}

export function resetTokenStream(stage?: string, documentKind?: string): void {
  if (stage && documentKind) {
    const key = keyFor(stage, documentKind);
    const state = streams.get(key);
    if (state) {
      state.buffer = "";
      state.nextSequence = 0;
      state.pending.clear();
      // Notify subscribers so they clear their UI immediately.
      const empty: TokenDeltaPayload = { stage, document_kind: documentKind, delta: "", sequence: -1 };
      for (const listener of state.listeners) {
        try {
          listener("", empty);
        } catch {
          /* ignore listener errors */
        }
      }
    }
    return;
  }
  // Reset everything (new generation run).
  for (const [, state] of streams) {
    state.buffer = "";
    state.nextSequence = 0;
    state.pending.clear();
    const empty: TokenDeltaPayload = { stage: "", document_kind: "", delta: "", sequence: -1 };
    for (const listener of state.listeners) {
      try {
        listener("", empty);
      } catch {
        /* ignore listener errors */
      }
    }
  }
}

export function publishTokenDelta(payload: TokenDeltaPayload): void {
  if (!payload || typeof payload.delta !== "string") return;
  const state = getState(payload.stage, payload.document_kind);

  // Backend sequence numbers begin at 0. Anything less than nextSequence
  // is a duplicate (from a coalescing replay) and is dropped.
  if (payload.sequence < state.nextSequence) return;

  if (payload.sequence === state.nextSequence) {
    state.buffer += payload.delta;
    state.nextSequence += 1;
    // Drain any pending out-of-order deltas that are now contiguous.
    while (state.pending.has(state.nextSequence)) {
      state.buffer += state.pending.get(state.nextSequence)!;
      state.pending.delete(state.nextSequence);
      state.nextSequence += 1;
    }
  } else {
    state.pending.set(payload.sequence, payload.delta);
  }

  for (const listener of state.listeners) {
    try {
      listener(state.buffer, payload);
    } catch {
      /* ignore listener errors */
    }
  }
}
