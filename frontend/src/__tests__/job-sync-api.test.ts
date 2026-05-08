/**
 * Pins the frontend helper contract for job-sync so alerts use the
 * correct backend endpoints and payload field names.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

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

function decodeBody(body: unknown): any {
  let value: any = body;
  for (let i = 0; i < 3 && typeof value === "string"; i++) {
    try {
      value = JSON.parse(value);
    } catch {
      break;
    }
  }
  return value;
}

describe("api.jobSync", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    api.setToken("test-token");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("POSTs alerts to /job-sync/alerts with salary_min", async () => {
    mockFetch.mockResolvedValueOnce(okJson({ id: "alert-1" }));

    await api.jobSync.createAlert({
      keywords: ["react", "typescript"],
      location: "Remote",
      salary_min: 120000,
      experience_level: "senior",
    });

    const [url, config] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/job-sync/alerts");
    expect(config.method).toBe("POST");
    expect(decodeBody(config.body)).toEqual({
      keywords: ["react", "typescript"],
      location: "Remote",
      salary_min: 120000,
      experience_level: "senior",
    });
  });

  it("DELETEs /job-sync/alerts/{id}", async () => {
    mockFetch.mockResolvedValueOnce(okJson({ status: "deleted" }));

    await api.jobSync.deleteAlert("alert-1");

    const [url, config] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/job-sync/alerts/alert-1");
    expect(config.method).toBe("DELETE");
  });

  it("GETs /job-sync/matches with status filter", async () => {
    mockFetch.mockResolvedValueOnce(okJson([]));

    await api.jobSync.getMatches("applied");

    const [url, config] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/job-sync/matches?status=applied");
    expect(config.method ?? "GET").toBe("GET");
  });
});