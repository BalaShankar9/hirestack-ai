/**
 * Unit tests for `api.jdCheck` (E3.frontend) — the helper added
 * alongside the public POST /api/jd-check route (commit 678194b).
 * Pins method/path/body shape so the frontend stays aligned with
 * the backend's JDCheckRequest.
 *
 * Decoder note: APIClient.request stringifies `body` again on top of
 * the helper's JSON.stringify, so we decode up to twice to recover
 * the payload (same pattern as batch-generate-api.test.ts and
 * tracked-companies-api.test.ts).
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

function errJson(status: number, detail: string) {
  return {
    ok: false,
    status,
    json: () => Promise.resolve({ detail }),
    headers: { get: () => null },
  };
}

function decodeBody(body: unknown): any {
  let v: any = body;
  for (let i = 0; i < 3 && typeof v === "string"; i++) {
    try {
      v = JSON.parse(v);
    } catch {
      break;
    }
  }
  return v;
}

describe("api.jdCheck", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    api.setToken(null);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("POSTs to /jd-check with text payload", async () => {
    mockFetch.mockResolvedValueOnce(
      okJson({
        findings: [],
        by_category: {
          ageist: 0,
          gendered: 0,
          vague_compensation: 0,
          unrealistic_experience: 0,
          culture_red_flag: 0,
          urgency: 0,
        },
        severity_counts: { critical: 0, warn: 0, info: 0 },
        total_count: 0,
      }),
    );

    const res = (await api.jdCheck.scan("Senior engineer wanted.")) as any;

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, config] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/jd-check");
    expect(config.method).toBe("POST");
    expect(decodeBody(config.body)).toEqual({ text: "Senior engineer wanted." });
    expect(res.total_count).toBe(0);
  });

  it("returns the parsed report with findings", async () => {
    mockFetch.mockResolvedValueOnce(
      okJson({
        findings: [
          {
            category: "gendered",
            severity: "critical",
            snippet: "Hire a rockstar engineer.",
            term: "rockstar",
            char_start: 7,
            char_end: 15,
          },
        ],
        by_category: {
          ageist: 0,
          gendered: 1,
          vague_compensation: 0,
          unrealistic_experience: 0,
          culture_red_flag: 0,
          urgency: 0,
        },
        severity_counts: { critical: 1, warn: 0, info: 0 },
        total_count: 1,
      }),
    );

    const res = (await api.jdCheck.scan("Hire a rockstar engineer.")) as any;
    expect(res.total_count).toBe(1);
    expect(res.findings[0].term).toBe("rockstar");
    expect(res.severity_counts.critical).toBe(1);
  });

  it("does not require an auth token (anonymous route)", async () => {
    mockFetch.mockResolvedValueOnce(
      okJson({
        findings: [],
        by_category: {},
        severity_counts: { critical: 0, warn: 0, info: 0 },
        total_count: 0,
      }),
    );

    await api.jdCheck.scan("any text");

    const [, config] = mockFetch.mock.calls[0];
    const headers = (config.headers ?? {}) as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
  });

  it("propagates 422 oversize errors as Error", async () => {
    mockFetch.mockResolvedValueOnce(errJson(422, "Text too long"));

    await expect(api.jdCheck.scan("x".repeat(300_000))).rejects.toThrow(/too long/i);
  });

  it("propagates 422 empty-text errors as Error", async () => {
    mockFetch.mockResolvedValueOnce(errJson(422, "text must not be blank"));

    await expect(api.jdCheck.scan("")).rejects.toThrow(/blank/i);
  });

  it("preserves unicode payloads", async () => {
    mockFetch.mockResolvedValueOnce(
      okJson({
        findings: [],
        by_category: {},
        severity_counts: { critical: 0, warn: 0, info: 0 },
        total_count: 0,
      }),
    );

    await api.jdCheck.scan("Looking for rockstar — résumé required.");

    const [, config] = mockFetch.mock.calls[0];
    const decoded = decodeBody(config.body);
    expect(decoded.text).toBe("Looking for rockstar — résumé required.");
  });
});
