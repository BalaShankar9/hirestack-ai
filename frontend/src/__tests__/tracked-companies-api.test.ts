/**
 * Unit tests for `api.trackedCompanies` (B2.frontend) — the helper
 * added alongside the /api/tracked-companies CRUD route (commit
 * 68ab4b4). Pins method/path/body shape so the frontend stays
 * aligned with the backend's CreateTrackedCompanyRequest /
 * PatchTrackedCompanyRequest.
 *
 * Decoder note: APIClient.request stringifies `body` again on top of
 * the helpers' JSON.stringify, so we decode up to twice to recover
 * the payload (same pattern as batch-generate-api.test.ts).
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

describe("api.trackedCompanies", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    api.setToken("test-token");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe(".list()", () => {
    it("GETs /tracked-companies and returns the parsed body", async () => {
      mockFetch.mockResolvedValueOnce(
        okJson({
          items: [{ id: "row-1", provider: "greenhouse", company_slug: "stripe" }],
          count: 1,
        }),
      );

      const res = (await api.trackedCompanies.list()) as any;

      expect(mockFetch).toHaveBeenCalledTimes(1);
      const [url, config] = mockFetch.mock.calls[0];
      expect(url).toContain("/api/tracked-companies");
      // GET requests in APIClient.request omit explicit method.
      expect(config.method ?? "GET").toBe("GET");
      expect(res.count).toBe(1);
      expect(res.items[0].company_slug).toBe("stripe");
    });
  });

  describe(".listDiscoveries()", () => {
    it("GETs /tracked-companies/discoveries with the limit query", async () => {
      mockFetch.mockResolvedValueOnce(
        okJson({
          items: [{ id: "history-1", company_slug: "stripe", role_title: "Designer" }],
          count: 1,
        }),
      );

      const res = (await api.trackedCompanies.listDiscoveries(10)) as any;

      expect(mockFetch).toHaveBeenCalledTimes(1);
      const [url, config] = mockFetch.mock.calls[0];
      expect(url).toContain("/api/tracked-companies/discoveries?limit=10");
      expect(config.method ?? "GET").toBe("GET");
      expect(res.items[0].role_title).toBe("Designer");
    });
  });

  describe(".create()", () => {
    it("POSTs the full payload (greenhouse, no workday tenant)", async () => {
      mockFetch.mockResolvedValueOnce(
        okJson({ id: "row-1", provider: "greenhouse", company_slug: "stripe" }),
      );

      await api.trackedCompanies.create({
        provider: "greenhouse",
        company_slug: "stripe",
        display_name: "Stripe",
      });

      const [url, config] = mockFetch.mock.calls[0];
      expect(url).toContain("/api/tracked-companies");
      expect(config.method).toBe("POST");
      expect(decodeBody(config.body)).toEqual({
        provider: "greenhouse",
        company_slug: "stripe",
        display_name: "Stripe",
      });
    });

    it("includes workday_tenant + careers_url when provided", async () => {
      mockFetch.mockResolvedValueOnce(okJson({ id: "row-1" }));

      await api.trackedCompanies.create({
        provider: "workday",
        company_slug: "acme",
        display_name: "Acme",
        workday_tenant: "acme.wd5",
        careers_url: "https://acme.com/careers",
      });

      const body = decodeBody(mockFetch.mock.calls[0][1].body);
      expect(body.workday_tenant).toBe("acme.wd5");
      expect(body.careers_url).toBe("https://acme.com/careers");
    });
  });

  describe(".update()", () => {
    it("PATCHes /tracked-companies/{id} with the editable subset", async () => {
      mockFetch.mockResolvedValueOnce(
        okJson({ id: "row-1", display_name: "Stripe Inc.", enabled: false }),
      );

      await api.trackedCompanies.update("row-1", {
        display_name: "Stripe Inc.",
        enabled: false,
      });

      const [url, config] = mockFetch.mock.calls[0];
      expect(url).toContain("/api/tracked-companies/row-1");
      expect(String(config.method).toUpperCase()).toBe("PATCH");
      expect(decodeBody(config.body)).toEqual({
        display_name: "Stripe Inc.",
        enabled: false,
      });
    });

    it("forwards null careers_url (clear via blank)", async () => {
      mockFetch.mockResolvedValueOnce(okJson({ id: "row-1" }));

      await api.trackedCompanies.update("row-1", { careers_url: null });

      const body = decodeBody(mockFetch.mock.calls[0][1].body);
      expect(body).toEqual({ careers_url: null });
    });
  });

  describe(".delete()", () => {
    it("DELETEs /tracked-companies/{id}", async () => {
      mockFetch.mockResolvedValueOnce(
        okJson({ status: "deleted", id: "row-1" }),
      );

      await api.trackedCompanies.delete("row-1");

      const [url, config] = mockFetch.mock.calls[0];
      expect(url).toContain("/api/tracked-companies/row-1");
      expect(config.method).toBe("DELETE");
    });
  });
});
