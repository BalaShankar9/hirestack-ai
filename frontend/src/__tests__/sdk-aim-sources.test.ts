import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

const { HirestackSdk, SdkError } = await import("@/lib/sdk");

function okJson(body: unknown, status = 200) {
  return {
    ok: true,
    status,
    json: () => Promise.resolve(body),
  };
}

describe("HirestackSdk — AIM sources", () => {
  let client: InstanceType<typeof HirestackSdk>;

  beforeEach(() => {
    mockFetch.mockReset();
    client = new HirestackSdk("http://localhost:8000");
    client.setToken("test-token");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("targets the /api/v1 mount, not legacy /api", async () => {
    mockFetch.mockResolvedValueOnce(okJson([]));

    await client.aim.listSources("assignment-1");

    const [url, config] = mockFetch.mock.calls[0];
    expect(url).toBe(
      "http://localhost:8000/api/v1/aim/assignments/assignment-1/sources",
    );
    expect(config.headers.Authorization).toBe("Bearer test-token");
  });

  it("POSTs source create with JSON content-type", async () => {
    mockFetch.mockResolvedValueOnce(okJson({ id: "s1", title: "Methods" }, 201));

    const out = await client.aim.createSource("assignment-1", {
      source_type: "book",
      title: "Methods",
      authors: ["Ada Lovelace"],
      year: 2024,
    });

    expect(out.id).toBe("s1");
    const [url, config] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/v1/aim/assignments/assignment-1/sources");
    expect(config.method).toBe("POST");
    expect(config.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(config.body)).toEqual({
      source_type: "book",
      title: "Methods",
      authors: ["Ada Lovelace"],
      year: 2024,
    });
  });

  it("DELETE returns void on 204", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, status: 204, json: vi.fn() });

    const result = await client.aim.deleteSource("source-1");

    expect(result).toBeUndefined();
    const [url, config] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/v1/aim/sources/source-1");
    expect(config.method).toBe("DELETE");
  });

  it("URL-encodes path params", async () => {
    mockFetch.mockResolvedValueOnce(okJson([]));

    await client.aim.listSources("a/b c");

    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain("/aim/assignments/a%2Fb%20c/sources");
  });

  it("throws SdkError with status + body on non-OK", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 422,
      json: () => Promise.resolve({ detail: "bad" }),
    });

    await expect(client.aim.createSource("a", {} as never)).rejects.toMatchObject({
      name: "Error",
      status: 422,
      body: { detail: "bad" },
    });
  });

  it("does not send Authorization when no token set", async () => {
    const anon = new HirestackSdk("http://localhost:8000");
    mockFetch.mockResolvedValueOnce(okJson([]));

    await anon.aim.listSources("a1");

    const [, config] = mockFetch.mock.calls[0];
    expect(config.headers.Authorization).toBeUndefined();
  });
});
