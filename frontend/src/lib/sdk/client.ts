/**
 * Typed SDK client (PR m4-pr13).
 *
 * Thin wrapper over `fetch` typed against the generated `schema.d.ts`.
 * Once `openapi-fetch` is added to the dependency graph, `request()` can
 * be swapped for it without touching call sites.
 *
 * All routes target the new `/api/v1` mount point. The legacy `/api`
 * mount stays live for one release for rollback safety.
 */
import type {
  AIMSourceCard,
  AIMSourceCreatePayload,
} from "./schema";

const DEFAULT_BASE_URL =
  (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_URL) || "";

export class SdkError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

export class HirestackSdk {
  baseUrl: string;
  private token: string | null = null;

  constructor(baseUrl: string = DEFAULT_BASE_URL) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
  }

  setToken(token: string | null): void {
    this.token = token;
  }

  private async request<T>(
    path: string,
    init: RequestInit = {},
  ): Promise<T> {
    const headers: Record<string, string> = {
      Accept: "application/json",
      ...((init.headers as Record<string, string>) || {}),
    };
    if (init.body && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }
    if (this.token) headers.Authorization = `Bearer ${this.token}`;

    const url = `${this.baseUrl}${path}`;
    const res = await fetch(url, { ...init, headers });
    if (!res.ok) {
      let body: unknown = null;
      try {
        body = await res.json();
      } catch {
        /* ignore */
      }
      throw new SdkError(res.status, `SDK ${init.method ?? "GET"} ${path} → ${res.status}`, body);
    }
    if (res.status === 204) return undefined as unknown as T;
    return (await res.json()) as T;
  }

  aim = {
    /** GET /api/v1/aim/assignments/{id}/sources */
    listSources: (assignmentId: string): Promise<AIMSourceCard[]> =>
      this.request<AIMSourceCard[]>(
        `/api/v1/aim/assignments/${encodeURIComponent(assignmentId)}/sources`,
      ),

    /** POST /api/v1/aim/assignments/{id}/sources */
    createSource: (
      assignmentId: string,
      payload: AIMSourceCreatePayload,
    ): Promise<AIMSourceCard> =>
      this.request<AIMSourceCard>(
        `/api/v1/aim/assignments/${encodeURIComponent(assignmentId)}/sources`,
        { method: "POST", body: JSON.stringify(payload) },
      ),

    /** DELETE /api/v1/aim/sources/{id} */
    deleteSource: (sourceId: string): Promise<void> =>
      this.request<void>(
        `/api/v1/aim/sources/${encodeURIComponent(sourceId)}`,
        { method: "DELETE" },
      ),
  };
}

export const sdk = new HirestackSdk();
