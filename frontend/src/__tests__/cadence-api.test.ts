import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

const { api } = await import("@/lib/api");

function okJson(body: unknown) {
  return {
    ok: true,
    status: 200,
    json: () => Promise.resolve(body),
  };
}

describe("api.cadence", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    api.setToken("test-token");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("GETs /cadence/today and returns the parsed body", async () => {
    mockFetch.mockResolvedValueOnce(
      okJson({
        date: "2026-05-06",
        buckets: { urgent: [], overdue: [], waiting: [], cold: [] },
        metadata: {
          total_tracked: 3,
          actionable_count: 1,
          urgent_count: 1,
          overdue_count: 0,
          waiting_count: 2,
          cold_count: 0,
          closed_count: 0,
        },
      }),
    );

    const res = (await api.cadence.today()) as any;

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, config] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/cadence/today");
    expect(config.method ?? "GET").toBe("GET");
    expect(res.metadata.total_tracked).toBe(3);
  });
});