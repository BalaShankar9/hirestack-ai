/**
 * Unit tests for the API client — retry logic, error handling, token management
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

// Mock fetch globally
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

// Must import AFTER stubbing fetch
const { api } = await import("@/lib/api");

describe("APIClient", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    api.setToken("test-token-123");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("request()", () => {
    it("makes authenticated requests with the token", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ data: "ok" }),
      });

      await api.request("/test");

      expect(mockFetch).toHaveBeenCalledTimes(1);
      const [url, config] = mockFetch.mock.calls[0];
      expect(url).toContain("/api/test");
      expect(config.headers["Authorization"]).toBe("Bearer test-token-123");
    });

    it("returns parsed JSON on success", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ id: 1, name: "test" }),
      });

      const result = await api.request("/items");
      expect(result).toEqual({ id: 1, name: "test" });
    });

    it("returns empty object for 204 No Content", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 204,
      });

      const result = await api.request("/items/1", { method: "DELETE" });
      expect(result).toEqual({});
    });

    it("throws on 401 without retrying", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: () => Promise.resolve({ detail: "Unauthorized" }),
      });

      await expect(api.request("/protected")).rejects.toThrow();
      expect(mockFetch).toHaveBeenCalledTimes(1); // No retries for 401
    });

    it("throws on 403 without retrying", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 403,
        json: () => Promise.resolve({ detail: "Forbidden" }),
      });

      await expect(api.request("/admin")).rejects.toThrow();
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });

    it("throws on 404 without retrying", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: () => Promise.resolve({ detail: "Not found" }),
      });

      await expect(api.request("/missing")).rejects.toThrow();
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });

    it("retries on 500 server errors", async () => {
      mockFetch
        .mockResolvedValueOnce({
          ok: false,
          status: 500,
          json: () => Promise.resolve({ detail: "Internal Server Error" }),
          headers: new Headers(),
        })
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ recovered: true }),
        });

      const result = await api.request("/flaky");
      expect(result).toEqual({ recovered: true });
      expect(mockFetch).toHaveBeenCalledTimes(2);
    });

    it("retries on network TypeError (offline, DNS failure)", async () => {
      mockFetch
        .mockRejectedValueOnce(new TypeError("Failed to fetch"))
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ recovered: true }),
        });

      const result = await api.request("/network-retry");
      expect(result).toEqual({ recovered: true });
      expect(mockFetch).toHaveBeenCalledTimes(2);
    });

    it("sends JSON body for POST requests", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ id: "new-1" }),
      });

      await api.request("/items", {
        method: "POST",
        body: { title: "New Item", description: "desc" },
      });

      const [, config] = mockFetch.mock.calls[0];
      expect(config.method).toBe("POST");
      expect(config.headers["Content-Type"]).toBe("application/json");
      expect(JSON.parse(config.body)).toEqual({ title: "New Item", description: "desc" });
    });
  });

  describe("setToken()", () => {
    it("updates the auth token for subsequent requests", async () => {
      api.setToken("new-token-456");

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({}),
      });

      await api.request("/check");
      const [, config] = mockFetch.mock.calls[0];
      expect(config.headers["Authorization"]).toBe("Bearer new-token-456");
    });
  });
});
