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

function decodeBody(body: unknown): unknown {
  return typeof body === "string" ? JSON.parse(body) : body;
}

describe("api.aim source helpers", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    api.setToken("test-token");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("GETs assignment sources", async () => {
    mockFetch.mockResolvedValueOnce(okJson([{ id: "source-1", title: "Methods" }]));

    const result = await api.aim.listSources("assignment-1");

    const [url, config] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/aim/assignments/assignment-1/sources");
    expect(config.method ?? "GET").toBe("GET");
    expect(result[0].title).toBe("Methods");
  });

  it("POSTs a source card payload", async () => {
    mockFetch.mockResolvedValueOnce(okJson({ id: "source-1", title: "Methods" }));

    await api.aim.createSource("assignment-1", {
      source_type: "book",
      title: "Methods",
      authors: ["Ada Lovelace"],
      year: 2024,
    });

    const [url, config] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/aim/assignments/assignment-1/sources");
    expect(config.method).toBe("POST");
    expect(decodeBody(config.body)).toEqual({
      source_type: "book",
      title: "Methods",
      authors: ["Ada Lovelace"],
      year: 2024,
    });
  });

  it("DELETEs a source card", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, status: 204, json: vi.fn() });

    await api.aim.deleteSource("source-1");

    const [url, config] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/aim/sources/source-1");
    expect(config.method).toBe("DELETE");
  });
});