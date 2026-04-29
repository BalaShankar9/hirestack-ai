/**
 * S8-F5: Behavioural pinning for src/lib/error-reporting.ts (R4).
 *
 * Module holds private queue+timer state, so each test does
 * vi.resetModules() + dynamic import to get a fresh instance.
 */
import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";

const REPORT_URL = "/api/backend/frontend-errors";

async function loadFresh() {
  vi.resetModules();
  return await import("@/lib/error-reporting");
}

let mockFetch: ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockFetch = vi.fn().mockResolvedValue({ ok: true });
  vi.stubGlobal("fetch", mockFetch);
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// reportError envelope shape
// ---------------------------------------------------------------------------

describe("reportError envelope", () => {
  it("captures error message", async () => {
    const { reportError } = await loadFresh();
    reportError(new Error("kaboom"));
    await vi.advanceTimersByTimeAsync(5_000);

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.errors[0].message).toBe("kaboom");
  });

  it("includes stack (truncated to 2000 chars)", async () => {
    const { reportError } = await loadFresh();
    const e = new Error("x");
    e.stack = "y".repeat(3000);
    reportError(e);
    await vi.advanceTimersByTimeAsync(5_000);

    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.errors[0].stack.length).toBe(2000);
  });

  it("includes componentStack (truncated to 1000 chars)", async () => {
    const { reportError } = await loadFresh();
    reportError(new Error("x"), "z".repeat(1500));
    await vi.advanceTimersByTimeAsync(5_000);

    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.errors[0].componentStack.length).toBe(1000);
  });

  it("omits stack/componentStack cleanly when not provided", async () => {
    const { reportError } = await loadFresh();
    const e = new Error("nostack");
    delete (e as any).stack;
    reportError(e);
    await vi.advanceTimersByTimeAsync(5_000);

    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.errors[0].stack).toBeUndefined();
    expect(body.errors[0].componentStack).toBeUndefined();
  });

  it("includes url from window.location.href", async () => {
    const { reportError } = await loadFresh();
    reportError(new Error("x"));
    await vi.advanceTimersByTimeAsync(5_000);

    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.errors[0].url).toBe(window.location.href);
  });

  it("includes userAgent from navigator.userAgent", async () => {
    const { reportError } = await loadFresh();
    reportError(new Error("x"));
    await vi.advanceTimersByTimeAsync(5_000);

    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.errors[0].userAgent).toBe(navigator.userAgent);
  });

  it("includes ISO-8601 timestamp", async () => {
    const { reportError } = await loadFresh();
    reportError(new Error("x"));
    await vi.advanceTimersByTimeAsync(5_000);

    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.errors[0].timestamp).toMatch(
      /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/,
    );
  });
});

// ---------------------------------------------------------------------------
// flush + queue behaviour
// ---------------------------------------------------------------------------

describe("flush behaviour", () => {
  it("POSTs to /api/backend/frontend-errors with keepalive=true and JSON body", async () => {
    const { reportError } = await loadFresh();
    reportError(new Error("a"));
    await vi.advanceTimersByTimeAsync(5_000);

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, opts] = mockFetch.mock.calls[0];
    expect(url).toBe(REPORT_URL);
    expect(opts.method).toBe("POST");
    expect(opts.keepalive).toBe(true);
    expect(opts.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(opts.body)).toMatchObject({
      errors: [{ message: "a" }],
    });
  });

  it("buffers up to 20 errors then drops further enqueues silently", async () => {
    const { reportError } = await loadFresh();
    for (let i = 0; i < 25; i++) reportError(new Error(`e${i}`));
    await vi.advanceTimersByTimeAsync(5_000);

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.errors.length).toBe(20);
    // First 20 were the ones kept, in arrival order.
    expect(body.errors[0].message).toBe("e0");
    expect(body.errors[19].message).toBe("e19");
  });

  it("does NOT flush before 5 seconds elapsed", async () => {
    const { reportError } = await loadFresh();
    reportError(new Error("a"));
    await vi.advanceTimersByTimeAsync(4_999);
    expect(mockFetch).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("does not reset the timer when a second error is enqueued during the window", async () => {
    const { reportError } = await loadFresh();
    reportError(new Error("a"));
    await vi.advanceTimersByTimeAsync(3_000);
    reportError(new Error("b"));
    await vi.advanceTimersByTimeAsync(2_000); // total = 5s from FIRST enqueue
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.errors.map((e: any) => e.message)).toEqual(["a", "b"]);
  });

  it("starts a new timer for the next batch after a flush", async () => {
    const { reportError } = await loadFresh();
    reportError(new Error("a"));
    await vi.advanceTimersByTimeAsync(5_000);
    expect(mockFetch).toHaveBeenCalledTimes(1);

    reportError(new Error("b"));
    await vi.advanceTimersByTimeAsync(5_000);
    expect(mockFetch).toHaveBeenCalledTimes(2);
    expect(JSON.parse(mockFetch.mock.calls[1][1].body).errors[0].message).toBe("b");
  });

  it("swallows fetch failures (never throws to caller)", async () => {
    mockFetch.mockRejectedValueOnce(new Error("network down"));
    const { reportError } = await loadFresh();
    reportError(new Error("a"));
    // Must not raise an unhandled rejection.
    await vi.advanceTimersByTimeAsync(5_000);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// installGlobalErrorHandler
// ---------------------------------------------------------------------------

describe("installGlobalErrorHandler", () => {
  it("is a no-op when window is undefined (SSR path)", async () => {
    const original = globalThis.window;
    // @ts-expect-error — intentionally deleting for the SSR-path test.
    delete globalThis.window;
    try {
      const { installGlobalErrorHandler } = await loadFresh();
      // Must not throw and must not register anything.
      expect(() => installGlobalErrorHandler()).not.toThrow();
    } finally {
      // @ts-expect-error — restoring.
      globalThis.window = original;
    }
  });

  it("dispatches a window 'error' event into reportError", async () => {
    const { installGlobalErrorHandler } = await loadFresh();
    installGlobalErrorHandler();

    const ev = new ErrorEvent("error", { error: new Error("uncaught"), message: "uncaught" });
    window.dispatchEvent(ev);

    await vi.advanceTimersByTimeAsync(5_000);
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.errors[0].message).toBe("uncaught");
  });

  it("falls back to event.message when event.error is not an Error", async () => {
    const { installGlobalErrorHandler } = await loadFresh();
    installGlobalErrorHandler();

    window.dispatchEvent(new ErrorEvent("error", { message: "string-only" }));
    await vi.advanceTimersByTimeAsync(5_000);
    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.errors[0].message).toBe("string-only");
  });

  it("dispatches 'unhandledrejection' with an Error reason", async () => {
    const { installGlobalErrorHandler } = await loadFresh();
    installGlobalErrorHandler();

    const ev = new Event("unhandledrejection") as PromiseRejectionEvent;
    (ev as any).reason = new Error("rejected");
    window.dispatchEvent(ev);

    await vi.advanceTimersByTimeAsync(5_000);
    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.errors[0].message).toBe("rejected");
  });

  it("dispatches 'unhandledrejection' with a non-Error reason (coerced via String)", async () => {
    const { installGlobalErrorHandler } = await loadFresh();
    installGlobalErrorHandler();

    const ev = new Event("unhandledrejection") as PromiseRejectionEvent;
    (ev as any).reason = "stringly-typed";
    window.dispatchEvent(ev);

    await vi.advanceTimersByTimeAsync(5_000);
    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.errors[0].message).toBe("stringly-typed");
  });

  it("uses the documented fallback when reason is null/undefined", async () => {
    const { installGlobalErrorHandler } = await loadFresh();
    installGlobalErrorHandler();

    const ev = new Event("unhandledrejection") as PromiseRejectionEvent;
    (ev as any).reason = null;
    window.dispatchEvent(ev);

    await vi.advanceTimersByTimeAsync(5_000);
    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.errors[0].message).toBe("Unhandled promise rejection");
  });

  it("flushes immediately when document.visibilityState becomes 'hidden'", async () => {
    const { reportError, installGlobalErrorHandler } = await loadFresh();
    installGlobalErrorHandler();
    reportError(new Error("a"));
    expect(mockFetch).not.toHaveBeenCalled();

    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => "hidden",
    });
    document.dispatchEvent(new Event("visibilitychange"));
    // flush() is async — let microtasks drain.
    await Promise.resolve();
    await Promise.resolve();
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });
});
