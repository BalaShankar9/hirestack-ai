import { describe, expect, it, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";

import {
  publishTokenDelta,
  resetTokenStream,
  getTokenStreamBuffer,
  subscribeTokenStream,
} from "@/lib/streams/token-stream-bus";
import { useTokenStream } from "@/hooks/use-token-stream";

describe("token-stream-bus", () => {
  beforeEach(() => {
    resetTokenStream();
  });

  it("appends contiguous deltas in sequence order", () => {
    publishTokenDelta({ stage: "quill", document_kind: "cv", delta: "Hello ", sequence: 0 });
    publishTokenDelta({ stage: "quill", document_kind: "cv", delta: "world", sequence: 1 });
    expect(getTokenStreamBuffer("quill", "cv")).toBe("Hello world");
  });

  it("buffers out-of-order deltas until predecessors arrive", () => {
    publishTokenDelta({ stage: "quill", document_kind: "cv", delta: "C", sequence: 2 });
    publishTokenDelta({ stage: "quill", document_kind: "cv", delta: "A", sequence: 0 });
    expect(getTokenStreamBuffer("quill", "cv")).toBe("A");
    publishTokenDelta({ stage: "quill", document_kind: "cv", delta: "B", sequence: 1 });
    expect(getTokenStreamBuffer("quill", "cv")).toBe("ABC");
  });

  it("drops duplicate replays of older sequences", () => {
    publishTokenDelta({ stage: "quill", document_kind: "cv", delta: "X", sequence: 0 });
    publishTokenDelta({ stage: "quill", document_kind: "cv", delta: "Y", sequence: 1 });
    publishTokenDelta({ stage: "quill", document_kind: "cv", delta: "X-dup", sequence: 0 });
    expect(getTokenStreamBuffer("quill", "cv")).toBe("XY");
  });

  it("isolates streams across (stage, document_kind) keys", () => {
    publishTokenDelta({ stage: "quill", document_kind: "cv", delta: "CV", sequence: 0 });
    publishTokenDelta({ stage: "quill", document_kind: "cover_letter", delta: "CL", sequence: 0 });
    expect(getTokenStreamBuffer("quill", "cv")).toBe("CV");
    expect(getTokenStreamBuffer("quill", "cover_letter")).toBe("CL");
  });

  it("notifies subscribers with accumulated buffer", () => {
    const seen: string[] = [];
    const off = subscribeTokenStream("forge", "personal_statement", (buf) => {
      seen.push(buf);
    });
    publishTokenDelta({ stage: "forge", document_kind: "personal_statement", delta: "a", sequence: 0 });
    publishTokenDelta({ stage: "forge", document_kind: "personal_statement", delta: "b", sequence: 1 });
    off();
    publishTokenDelta({ stage: "forge", document_kind: "personal_statement", delta: "c", sequence: 2 });
    expect(seen).toEqual(["a", "ab"]);
    expect(getTokenStreamBuffer("forge", "personal_statement")).toBe("abc");
  });

  it("resets a single stream to empty", () => {
    publishTokenDelta({ stage: "quill", document_kind: "cv", delta: "X", sequence: 0 });
    resetTokenStream("quill", "cv");
    expect(getTokenStreamBuffer("quill", "cv")).toBe("");
    publishTokenDelta({ stage: "quill", document_kind: "cv", delta: "fresh", sequence: 0 });
    expect(getTokenStreamBuffer("quill", "cv")).toBe("fresh");
  });
});

describe("useTokenStream", () => {
  beforeEach(() => {
    resetTokenStream();
  });

  it("returns the current buffer and updates as deltas arrive", () => {
    const { result } = renderHook(() => useTokenStream("quill", "cv"));
    expect(result.current.buffer).toBe("");
    expect(result.current.isStreaming).toBe(false);

    act(() => {
      publishTokenDelta({ stage: "quill", document_kind: "cv", delta: "Hi", sequence: 0 });
    });
    expect(result.current.buffer).toBe("Hi");
    expect(result.current.isStreaming).toBe(true);

    act(() => {
      publishTokenDelta({ stage: "quill", document_kind: "cv", delta: "!", sequence: 1 });
    });
    expect(result.current.buffer).toBe("Hi!");
  });

  it("clears isStreaming on reset sentinel", () => {
    const { result } = renderHook(() => useTokenStream("quill", "cv"));
    act(() => {
      publishTokenDelta({ stage: "quill", document_kind: "cv", delta: "x", sequence: 0 });
    });
    expect(result.current.isStreaming).toBe(true);
    act(() => {
      resetTokenStream("quill", "cv");
    });
    expect(result.current.buffer).toBe("");
    expect(result.current.isStreaming).toBe(false);
  });

  it("ignores deltas for other (stage, document_kind) pairs", () => {
    const { result } = renderHook(() => useTokenStream("quill", "cv"));
    act(() => {
      publishTokenDelta({ stage: "forge", document_kind: "portfolio", delta: "nope", sequence: 0 });
    });
    expect(result.current.buffer).toBe("");
  });
});
