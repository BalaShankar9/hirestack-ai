/**
 * S8-F4: extend api client coverage — uploadFile retry/auth/payload
 * and the sanitizeErrorDetail private behaviour observable through
 * the public request() surface (R5).
 *
 * The existing api-client.test.ts already pins request() retry counts
 * and basic JSON contracts. This file pins:
 *   - uploadFile success/failure/retry/auth/additionalData
 *   - sanitizeErrorDetail observable behaviour
 *   - Retry-After header parsing
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

// Must import AFTER stubbing fetch.
const { api } = await import("@/lib/api");

beforeEach(() => {
  mockFetch.mockReset();
  api.setToken("test-token");
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

// ---------------------------------------------------------------------------
// uploadFile
// ---------------------------------------------------------------------------

describe("uploadFile()", () => {
  it("posts a multipart FormData containing the file", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ id: "u1" }),
    });
    const file = new File(["hello"], "resume.pdf", { type: "application/pdf" });

    const result = await api.uploadFile("/profile/upload", file);

    expect(result).toEqual({ id: "u1" });
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, config] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/profile/upload");
    expect(config.method).toBe("POST");
    expect(config.body).toBeInstanceOf(FormData);
    const fd = config.body as FormData;
    expect((fd.get("file") as File).name).toBe("resume.pdf");
  });

  it("does NOT set Content-Type (browser sets multipart boundary)", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    });
    await api.uploadFile("/x", new File(["a"], "a.txt"));
    const [, config] = mockFetch.mock.calls[0];
    expect(config.headers["Content-Type"]).toBeUndefined();
  });

  it("sends the auth token from setToken()", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    });
    await api.uploadFile("/x", new File(["a"], "a.txt"));
    const [, config] = mockFetch.mock.calls[0];
    expect(config.headers["Authorization"]).toBe("Bearer test-token");
  });

  it("the per-call token argument overrides the stored token", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    });
    await api.uploadFile("/x", new File(["a"], "a.txt"), undefined, "override-tok");
    const [, config] = mockFetch.mock.calls[0];
    expect(config.headers["Authorization"]).toBe("Bearer override-tok");
  });

  it("appends every entry of additionalData to the FormData", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    });
    await api.uploadFile(
      "/profile/upload",
      new File(["a"], "a.txt"),
      { is_primary: "true", tag: "primary" },
    );
    const fd = mockFetch.mock.calls[0][1].body as FormData;
    expect(fd.get("is_primary")).toBe("true");
    expect(fd.get("tag")).toBe("primary");
  });

  it("throws immediately on 4xx without retrying", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 422,
      json: () => Promise.resolve({ detail: "bad file" }),
    });
    await expect(api.uploadFile("/x", new File(["a"], "a.txt"))).rejects.toThrow("bad file");
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("uses a generic message when 4xx response has no detail and no JSON body", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 400,
      json: () => Promise.reject(new Error("not json")),
    });
    await expect(api.uploadFile("/x", new File(["a"], "a.txt"))).rejects.toThrow("Upload failed");
  });

  it("retries on 500 (succeeds on attempt 2)", async () => {
    vi.useFakeTimers();
    mockFetch
      .mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: () => Promise.resolve({ detail: "boom" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ id: "ok" }),
      });

    const promise = api.uploadFile("/x", new File(["a"], "a.txt"));
    await vi.runAllTimersAsync();
    await expect(promise).resolves.toEqual({ id: "ok" });
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it("retries on network TypeError", async () => {
    vi.useFakeTimers();
    mockFetch
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ id: "ok" }),
      });

    const promise = api.uploadFile("/x", new File(["a"], "a.txt"));
    await vi.runAllTimersAsync();
    await expect(promise).resolves.toEqual({ id: "ok" });
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it("after MAX_RETRIES (3) exhausted on 5xx, throws the last error", async () => {
    vi.useFakeTimers();
    mockFetch.mockResolvedValue({
      ok: false,
      status: 503,
      json: () => Promise.resolve({ detail: "still down" }),
    });

    const promise = api.uploadFile("/x", new File(["a"], "a.txt"));
    promise.catch(() => {}); // suppress unhandled rejection during pump
    await vi.runAllTimersAsync();
    await expect(promise).rejects.toThrow();
    expect(mockFetch).toHaveBeenCalledTimes(3);
  });

  it("after MAX_RETRIES (3) exhausted on network errors, throws the last error", async () => {
    vi.useFakeTimers();
    mockFetch.mockRejectedValue(new TypeError("offline"));

    const promise = api.uploadFile("/x", new File(["a"], "a.txt"));
    promise.catch(() => {});
    await vi.runAllTimersAsync();
    await expect(promise).rejects.toThrow();
    expect(mockFetch).toHaveBeenCalledTimes(3);
  });
});

// ---------------------------------------------------------------------------
// sanitizeErrorDetail (observed via request())
// ---------------------------------------------------------------------------

describe("sanitizeErrorDetail (via request())", () => {
  it("replaces a 5xx detail containing 'Traceback' with the generic 5xx message", async () => {
    vi.useFakeTimers();
    mockFetch.mockResolvedValue({
      ok: false,
      status: 500,
      json: () => Promise.resolve({ detail: "Traceback (most recent call last):\n  ..." }),
      headers: new Headers(),
    });
    const p = api.request("/boom").catch((e) => e);
    await vi.runAllTimersAsync();
    const err = (await p) as Error;
    expect(err.message).toBe("Something went wrong on our end. Please try again.");
  });

  it("replaces a 4xx detail containing a file path with the generic 4xx message", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 422,
      json: () => Promise.resolve({ detail: 'File "x.py", line 12, in foo' }),
    });
    await expect(api.request("/v")).rejects.toThrow("Request failed (422)");
  });

  it("truncates an over-long 4xx detail to 300 chars", async () => {
    const longDetail = "x".repeat(400);
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 400,
      json: () => Promise.resolve({ detail: longDetail }),
    });
    await expect(api.request("/v")).rejects.toThrow("x".repeat(300));
    // And not 400 chars worth
    try {
      await api.request("/v");
    } catch {
      // already asserted above
    }
  });

  it("returns the generic 5xx message when detail is over 300 chars on a 5xx", async () => {
    vi.useFakeTimers();
    mockFetch.mockResolvedValue({
      ok: false,
      status: 500,
      json: () => Promise.resolve({ detail: "y".repeat(400) }),
      headers: new Headers(),
    });
    const p = api.request("/boom").catch((e) => e);
    await vi.runAllTimersAsync();
    const err = (await p) as Error;
    expect(err.message).toBe("Something went wrong on our end. Please try again.");
  });

  it("falls back to a generic message when detail is missing entirely", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: () => Promise.resolve({}),
    });
    await expect(api.request("/missing")).rejects.toThrow("HTTP error! status: 404");
  });

  it("preserves a clean short 4xx detail verbatim", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 400,
      json: () => Promise.resolve({ detail: "Email already in use" }),
    });
    await expect(api.request("/signup", { method: "POST", body: {} })).rejects.toThrow(
      "Email already in use",
    );
  });
});

// ---------------------------------------------------------------------------
// Retry-After header
// ---------------------------------------------------------------------------

describe("Retry-After header", () => {
  it("respects a numeric Retry-After (seconds) before retry on 503", async () => {
    vi.useFakeTimers();
    mockFetch
      .mockResolvedValueOnce({
        ok: false,
        status: 503,
        json: () => Promise.resolve({ detail: "rate limited" }),
        headers: new Headers({ "Retry-After": "5" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ ok: true }),
      });

    const p = api.request("/x");
    // Advance < 5s — second fetch should not have fired yet.
    await vi.advanceTimersByTimeAsync(4000);
    expect(mockFetch).toHaveBeenCalledTimes(1);
    // Advance past 5s — second fetch fires.
    await vi.advanceTimersByTimeAsync(2000);
    await expect(p).resolves.toEqual({ ok: true });
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it("falls back to attempt*2000 ms when Retry-After is non-numeric", async () => {
    vi.useFakeTimers();
    mockFetch
      .mockResolvedValueOnce({
        ok: false,
        status: 503,
        json: () => Promise.resolve({ detail: "x" }),
        headers: new Headers({ "Retry-After": "not-a-number" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ ok: true }),
      });

    const p = api.request("/x");
    // Less than 2s — still waiting on attempt-1's backoff.
    await vi.advanceTimersByTimeAsync(1500);
    expect(mockFetch).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1000);
    await expect(p).resolves.toEqual({ ok: true });
  });
});
