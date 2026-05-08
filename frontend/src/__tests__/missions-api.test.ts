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

function decodeBody(body: unknown): any {
  return typeof body === "string" ? JSON.parse(body) : body;
}

describe("api.missions", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    api.setToken("test-token");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("GETs /missions with an optional status filter", async () => {
    mockFetch.mockResolvedValueOnce(okJson({ items: [], count: 0 }));

    await api.missions.list("active");

    const [url, config] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/missions?status=active");
    expect(config.method ?? "GET").toBe("GET");
  });

  it("POSTs the mission create payload", async () => {
    mockFetch.mockResolvedValueOnce(okJson({ id: "mission-1" }));

    await api.missions.create({
      name: "Design leadership",
      role_titles: ["Staff Product Designer"],
      min_fit_score: 4.3,
      voice_preset: "warm_eager",
    });

    const [url, config] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/missions");
    expect(config.method).toBe("POST");
    expect(decodeBody(config.body)).toEqual({
      name: "Design leadership",
      role_titles: ["Staff Product Designer"],
      min_fit_score: 4.3,
      voice_preset: "warm_eager",
    });
  });

  it("GETs mission drafts with query params", async () => {
    mockFetch.mockResolvedValueOnce(okJson({ items: [], count: 0 }));

    await api.missions.listDrafts("mission-1", 25, "ready_for_user");

    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/missions/mission-1/drafts?limit=25&status=ready_for_user");
  });

  it("POSTs mission sync requests", async () => {
    mockFetch.mockResolvedValueOnce(okJson({ status: "ok", created: 1 }));

    await api.missions.sync("mission-1");

    const [url, config] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/missions/mission-1/sync");
    expect(config.method).toBe("POST");
  });

  it("PATCHes mission drafts status changes", async () => {
    mockFetch.mockResolvedValueOnce(okJson({ id: "draft-1", status: "sent" }));

    await api.missions.updateDraft("mission-1", "draft-1", { status: "sent" });

    const [url, config] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/missions/mission-1/drafts/draft-1");
    expect(config.method).toBe("PATCH");
    expect(decodeBody(config.body)).toEqual({ status: "sent" });
  });
});