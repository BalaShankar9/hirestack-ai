/**
 * W5 UX unit tests: useIntelPrefetch hook + api.prefetchIntel.
 *
 * Validates debounce, dedupe, failure silent-swallow, and status transitions.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

const { api } = await import("@/lib/api");
const { useIntelPrefetch } = await import("@/hooks/use-intel-prefetch");

const VALID_JD = "x".repeat(80);

beforeEach(() => {
  mockFetch.mockReset();
  api.setToken("test-token");
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("api.prefetchIntel", () => {
  it("POSTs to /api/intel/prefetch and returns the parsed body on success", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ status: "queued", jd_hash: "intel_abc" }),
    });

    const result = await api.prefetchIntel({
      jd_text: VALID_JD,
      job_title: "Senior Engineer",
      company: "Acme",
    });

    expect(result).toEqual({ status: "queued", jd_hash: "intel_abc" });
    const [url, cfg] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/intel/prefetch");
    expect(cfg.method).toBe("POST");
  });

  it("swallows errors and returns null so UX never breaks", async () => {
    // Non-retryable 400 — request() throws, prefetchIntel catches and returns null.
    mockFetch.mockResolvedValue({
      ok: false,
      status: 400,
      json: () => Promise.resolve({ detail: "bad" }),
    });
    const result = await api.prefetchIntel({
      jd_text: VALID_JD,
      job_title: "Senior Engineer",
      company: "Acme",
    });
    expect(result).toBeNull();
  });
});

describe("useIntelPrefetch", () => {
  it("skips prefetch when jd_text is too short", async () => {
    const { result } = renderHook(() =>
      useIntelPrefetch({
        jd_text: "short",
        job_title: "Senior Engineer",
        company: "Acme",
        debounceMs: 10,
      })
    );
    // Wait past debounce window
    await new Promise((r) => setTimeout(r, 40));
    expect(mockFetch).not.toHaveBeenCalled();
    expect(result.current.status).toBe("idle");
  });

  it("skips when any required field is missing", async () => {
    renderHook(() =>
      useIntelPrefetch({ jd_text: VALID_JD, job_title: "", company: "Acme", debounceMs: 10 })
    );
    await new Promise((r) => setTimeout(r, 40));
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("debounces before firing and sets status to cached on cache hit", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ status: "cached", jd_hash: "intel_xyz" }),
    });

    const { result } = renderHook(() =>
      useIntelPrefetch({
        jd_text: VALID_JD,
        job_title: "Senior Engineer",
        company: "Acme",
        debounceMs: 10,
      })
    );

    // Before debounce fires — no call yet
    expect(mockFetch).not.toHaveBeenCalled();

    await waitFor(
      () => expect(result.current.status).toBe("cached"),
      { timeout: 500 }
    );
    expect(result.current.jdHash).toBe("intel_xyz");
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("dedupes re-renders with identical params — fires only once", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ status: "queued", jd_hash: "intel_1" }),
    });

    const { rerender } = renderHook(
      (props) => useIntelPrefetch(props),
      {
        initialProps: {
          jd_text: VALID_JD,
          job_title: "Eng",
          company: "Acme",
          debounceMs: 10,
        } as Parameters<typeof useIntelPrefetch>[0],
      }
    );

    await new Promise((r) => setTimeout(r, 60));
    rerender({ jd_text: VALID_JD, job_title: "Eng", company: "Acme", debounceMs: 10 });
    await new Promise((r) => setTimeout(r, 60));

    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("reports 'failed' when the backend call ultimately errors", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 400,
      json: () => Promise.resolve({ detail: "bad" }),
    });

    const { result } = renderHook(() =>
      useIntelPrefetch({
        jd_text: VALID_JD,
        job_title: "Senior Engineer",
        company: "Acme",
        debounceMs: 10,
      })
    );

    await waitFor(
      () => expect(result.current.status).toBe("failed"),
      { timeout: 1000 }
    );
  });

  it("respects `disabled` flag and never fires", async () => {
    renderHook(() =>
      useIntelPrefetch({
        jd_text: VALID_JD,
        job_title: "Eng",
        company: "Acme",
        disabled: true,
        debounceMs: 10,
      })
    );
    await new Promise((r) => setTimeout(r, 40));
    expect(mockFetch).not.toHaveBeenCalled();
  });
});
