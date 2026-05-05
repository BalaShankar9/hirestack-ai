/**
 * AIM section-generation SSE hook.
 *
 * Connects to POST /api/aim/sections/{id}/generate-stream and surfaces
 * each writer→reviewer attempt + the final outcome. The browser EventSource
 * API does not support POST + custom headers, so we use fetch() + ReadableStream.
 *
 * Resume-on-reconnect: `resume(sectionId, sinceSequence?)` rehydrates from
 * GET /api/aim/sections/{id}/events?since=<n> before re-attaching the live
 * stream. The `lastSequence` returned in the state is fed back as `since`
 * on the next reconnect so no events are dropped or duplicated.
 */

import { useCallback, useRef, useState } from "react";

import { api } from "@/lib/api";
import { supabase } from "@/lib/supabase";

export interface AIMAttempt {
  version: number;
  content: string;
  blocks: any[];
  word_count: number;
  weighted_score: number;
  passed_gate: boolean;
  reviewer: any;
  latency_ms: number;
}

export interface AIMStreamState {
  attempts: AIMAttempt[];
  isStreaming: boolean;
  done: boolean;
  passedGate: boolean | null;
  stopReason: string | null;
  error: string | null;
  /** Highest event sequence applied — feed back as `since` on reconnect. */
  lastSequence: number;
  /** True while replaying persisted events (before live stream re-attaches). */
  isResuming: boolean;
}

const initial: AIMStreamState = {
  attempts: [],
  isStreaming: false,
  done: false,
  passedGate: null,
  stopReason: null,
  error: null,
  lastSequence: 0,
  isResuming: false,
};

function applyPersistedEvent(state: AIMStreamState, evt: {
  sequence: number;
  event_type: string;
  data: Record<string, any>;
}): AIMStreamState {
  const next: AIMStreamState = {
    ...state,
    lastSequence: Math.max(state.lastSequence, evt.sequence ?? 0),
  };
  if (evt.event_type === "complete") {
    next.done = true;
    next.passedGate = !!evt.data?.passed_gate;
    next.stopReason = evt.data?.stop_reason ?? null;
    if (evt.data?.final) {
      next.attempts = [...next.attempts, evt.data.final as AIMAttempt];
    }
  } else if (evt.event_type === "error") {
    next.error = (evt as any).message || "stream error";
  }
  return next;
}

export function useAIMStream() {
  const [state, setState] = useState<AIMStreamState>(initial);
  const abortRef = useRef<AbortController | null>(null);
  const lastSeqRef = useRef<number>(0);

  const consumeStream = useCallback(async (sectionId: string) => {
    const ctrl = new AbortController();
    abortRef.current?.abort();
    abortRef.current = ctrl;

    const { data: { session } } = await supabase.auth.getSession();
    const token = session?.access_token;

    let resp: Response;
    try {
      resp = await fetch(api.aim.streamUrl(sectionId), {
        method: "POST",
        signal: ctrl.signal,
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
    } catch (e: any) {
      setState((s) => ({ ...s, isStreaming: false, error: e?.message || "network error" }));
      return;
    }

    if (!resp.ok || !resp.body) {
      setState((s) => ({
        ...s, isStreaming: false,
        error: `HTTP ${resp.status}`,
      }));
      return;
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });

      // SSE messages are separated by blank lines
      const parts = buf.split("\n\n");
      buf = parts.pop() ?? "";

      for (const block of parts) {
        let event = "message";
        let data = "";
        for (const line of block.split("\n")) {
          if (line.startsWith("event: ")) event = line.slice(7).trim();
          else if (line.startsWith("data: ")) data += line.slice(6);
        }
        if (!data) continue;
        let payload: any;
        try { payload = JSON.parse(data); } catch { continue; }

        // Track sequence for resume (server emits sequence on persisted events)
        if (typeof payload?.sequence === "number") {
          lastSeqRef.current = Math.max(lastSeqRef.current, payload.sequence);
        }

        if (event === "attempt") {
          setState((s) => ({
            ...s,
            attempts: [...s.attempts, payload as AIMAttempt],
            lastSequence: lastSeqRef.current,
          }));
        } else if (event === "done" || event === "complete") {
          setState((s) => ({
            ...s,
            isStreaming: false,
            done: true,
            passedGate: !!payload.passed_gate,
            stopReason: payload.stop_reason,
            lastSequence: lastSeqRef.current,
          }));
        } else if (event === "error") {
          setState((s) => ({
            ...s,
            isStreaming: false,
            error: payload.message || "stream error",
            lastSequence: lastSeqRef.current,
          }));
        }
      }
    }
    setState((s) => (s.isStreaming ? { ...s, isStreaming: false } : s));
  }, []);

  const start = useCallback(async (sectionId: string) => {
    lastSeqRef.current = 0;
    setState({ ...initial, isStreaming: true });
    await consumeStream(sectionId);
  }, [consumeStream]);

  /**
   * Resume after a reconnect: rehydrates persisted events from the events
   * endpoint, then re-opens the SSE stream. If `sinceSequence` is omitted,
   * uses the hook's tracked `lastSequence` (typical reconnect path).
   */
  const resume = useCallback(async (
    sectionId: string,
    sinceSequence?: number,
  ) => {
    const since = sinceSequence ?? lastSeqRef.current;
    setState((s) => ({ ...s, isResuming: true, isStreaming: true, error: null }));
    try {
      const replay = await api.aim.listSectionEvents(sectionId, since);
      lastSeqRef.current = replay.last_sequence;
      setState((s) => {
        let next = { ...s, isResuming: false };
        for (const evt of replay.events) {
          next = applyPersistedEvent(next, evt);
        }
        return next;
      });
      // If the replay already shows completion, no need to reconnect.
      if (replay.events.some((e) => e.event_type === "complete")) {
        setState((s) => ({ ...s, isStreaming: false }));
        return;
      }
    } catch (e: any) {
      setState((s) => ({
        ...s, isResuming: false, isStreaming: false,
        error: e?.message || "resume failed",
      }));
      return;
    }
    await consumeStream(sectionId);
  }, [consumeStream]);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    setState((s) => ({ ...s, isStreaming: false }));
  }, []);

  return { ...state, start, resume, cancel };
}
