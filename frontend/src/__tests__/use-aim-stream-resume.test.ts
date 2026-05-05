/**
 * S15 — useAIMStream resume-on-reconnect tests.
 *
 * Covers `resume(sectionId, since?)`:
 *   1. fetches GET /aim/sections/{id}/events?since=<n> first
 *   2. rehydrates persisted `complete` events into terminal state
 *   3. tracks lastSequence for the next reconnect
 *   4. skips re-attaching to live SSE when replay already shows completion
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";

// supabase.auth.getSession is called on stream attach — stub it out before importing the hook.
vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: { getSession: vi.fn(async () => ({ data: { session: null } })) },
  },
}));

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

const { api } = await import("@/lib/api");
const { useAIMStream } = await import("@/hooks/use-aim-stream");

beforeEach(() => {
  mockFetch.mockReset();
  api.setToken("test-token");
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useAIMStream.resume", () => {
  it("rehydrates terminal state from a persisted `complete` event without re-attaching SSE", async () => {
    // GET /aim/sections/sec-1/events?since=0 returns a completed run.
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({
        section_id: "sec-1",
        since: 0,
        count: 2,
        last_sequence: 7,
        events: [
          {
            event_id: "e1", section_id: "sec-1", sequence: 3,
            event_type: "agent_status", agent: "writer", status: "completed",
            message: "Draft ready", progress: 50, latency_ms: 0, data: {},
          },
          {
            event_id: "e2", section_id: "sec-1", sequence: 7,
            event_type: "complete", agent: "aim", status: "completed",
            message: "Section ready", progress: 100, latency_ms: 0,
            data: {
              passed_gate: true,
              stop_reason: "passed",
              final: {
                version: 1, content: "Final body", blocks: [],
                word_count: 2, weighted_score: 92.0, passed_gate: true,
                reviewer: {}, latency_ms: 0,
              },
            },
          },
        ],
      }),
    });

    const { result } = renderHook(() => useAIMStream());

    await act(async () => {
      await result.current.resume("sec-1");
    });

    await waitFor(() => expect(result.current.done).toBe(true));
    expect(result.current.passedGate).toBe(true);
    expect(result.current.stopReason).toBe("passed");
    expect(result.current.attempts).toHaveLength(1);
    expect(result.current.attempts[0].weighted_score).toBe(92.0);
    expect(result.current.lastSequence).toBe(7);
    expect(result.current.isStreaming).toBe(false);

    // Only the GET /events call should have happened — no POST /generate-stream.
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, cfg] = mockFetch.mock.calls[0];
    expect(url).toContain("/aim/sections/sec-1/events?since=0");
    expect((cfg as any)?.method ?? "GET").toBe("GET");
  });

  it("uses tracked lastSequence as `since` on follow-up resume call", async () => {
    // First resume returns one event (no complete) → would normally re-attach,
    // but we make the SSE POST fail fast so the test stays bounded.
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({
        section_id: "sec-1",
        since: 0,
        count: 1,
        last_sequence: 4,
        events: [
          {
            event_id: "e1", section_id: "sec-1", sequence: 4,
            event_type: "agent_status", agent: "writer", status: "completed",
            message: "Draft ready", progress: 50, latency_ms: 0, data: {},
          },
        ],
      }),
    });
    // POST /generate-stream → simulate 503 so consumeStream exits cleanly.
    mockFetch.mockResolvedValueOnce({
      ok: false, status: 503, body: null,
    });

    const { result } = renderHook(() => useAIMStream());
    await act(async () => { await result.current.resume("sec-1"); });

    await waitFor(() => expect(result.current.lastSequence).toBe(4));

    // Now reconnect — should send since=4, not since=0.
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({
        section_id: "sec-1", since: 4, count: 0, last_sequence: 4, events: [],
      }),
    });
    mockFetch.mockResolvedValueOnce({ ok: false, status: 503, body: null });

    await act(async () => { await result.current.resume("sec-1"); });

    const eventsCall = mockFetch.mock.calls.find(
      (c) => typeof c[0] === "string" && c[0].includes("/events?since=4"),
    );
    expect(eventsCall).toBeDefined();
  });
});
