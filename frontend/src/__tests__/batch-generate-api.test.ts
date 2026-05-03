/**
 * Unit tests for the `api.batchGenerate.commit` helper added in
 * B0.persist.frontend.  Verifies the POST payload shape so the
 * frontend stays aligned with the backend's BatchCommitRequest
 * (urls + optional min_fit_score + optional concurrency).
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

/**
 * Body decoder: existing batchGenerate.plan/score helpers pass an
 * already-JSON.stringified body to APIClient.request, which then
 * JSON.stringifies it again (RequestOptions.body is `any`). To stay
 * aligned with that established pattern we accept either single- or
 * double-stringified payloads and decode until we hit an object.
 */
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

describe("api.batchGenerate.commit", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    api.setToken("test-token");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("posts urls only when no opts are provided", async () => {
    mockFetch.mockResolvedValueOnce(okJson({ persisted: { batch_id: "b1", inserted: [], inserted_count: 0, skipped: [], skipped_count: 0 } }));

    await api.batchGenerate.commit(["https://a", "https://b"]);

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, config] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/generate/batch/commit");
    expect(config.method).toBe("POST");
    const body = decodeBody(config.body);
    expect(body).toEqual({ urls: ["https://a", "https://b"] });
  });

  it("includes min_fit_score and concurrency only when defined", async () => {
    mockFetch.mockResolvedValueOnce(okJson({ persisted: { batch_id: "b1", inserted: [], inserted_count: 0, skipped: [], skipped_count: 0 } }));

    await api.batchGenerate.commit(["https://a"], { min_fit_score: 3.5, concurrency: 4 });

    const body = decodeBody(mockFetch.mock.calls[0][1].body);
    expect(body).toEqual({ urls: ["https://a"], min_fit_score: 3.5, concurrency: 4 });
  });

  it("omits undefined opts (no nullish min_fit_score key)", async () => {
    mockFetch.mockResolvedValueOnce(okJson({ persisted: { batch_id: "b1", inserted: [], inserted_count: 0, skipped: [], skipped_count: 0 } }));

    await api.batchGenerate.commit(["https://a"], { concurrency: 2 });

    const body = decodeBody(mockFetch.mock.calls[0][1].body);
    expect(body).toEqual({ urls: ["https://a"], concurrency: 2 });
    expect("min_fit_score" in body).toBe(false);
  });

  it("returns the parsed JSON response (persisted block passthrough)", async () => {
    const persisted = {
      batch_id: "batch-xyz",
      inserted: [{ canonical_url: "https://a", application_id: "app-1" }],
      inserted_count: 1,
      skipped: [{ canonical_url: "https://b", application_id: "app-2" }],
      skipped_count: 1,
    };
    mockFetch.mockResolvedValueOnce(okJson({ persisted, plan: {}, scored: {}, min_fit_score: 3.0 }));

    const res = (await api.batchGenerate.commit(["https://a", "https://b"])) as any;

    expect(res.persisted).toEqual(persisted);
  });
});
