/**
 * Pipeline event schema gate (S15-A1).
 *
 * Centralises *two* invariants every SSE consumer must enforce so the UI
 * never lies to the user:
 *
 *   1. **Schema major-version gate** — drop any payload whose
 *      `schema_version` major differs from `MIN_ACCEPTED_SCHEMA`. A backend
 *      that ships a breaking event shape MUST bump its major; until the
 *      frontend learns the new shape we ignore those events instead of
 *      mis-rendering them.
 *
 *   2. **Idempotent dedup** — the SSE transport may replay an event when
 *      reconnecting, and a future at-least-once persistence layer (DB sink
 *      hydration on resume) can also re-fire seen events. We dedup on
 *      `event_id` (uuid) when present, and fall back to a structural key
 *      (`event_type:stage:sequence`) when the producer hasn't tagged one
 *      yet.
 */

export const MIN_ACCEPTED_SCHEMA = "1.0";

const MIN_ACCEPTED_MAJOR = Number.parseInt(MIN_ACCEPTED_SCHEMA.split(".")[0] ?? "1", 10);

/** Returns true when the payload's schema_version matches our major. */
export function isSchemaAccepted(payload: unknown): boolean {
  if (!payload || typeof payload !== "object") return true; // legacy payloads pass
  const raw = (payload as { schema_version?: unknown }).schema_version;
  if (raw === undefined || raw === null || raw === "") return true; // unversioned = legacy
  if (typeof raw !== "string") return false;
  const major = Number.parseInt(raw.split(".")[0] ?? "", 10);
  if (!Number.isFinite(major)) return false;
  return major === MIN_ACCEPTED_MAJOR;
}

/** Stable key used by the deduper. */
export function eventDedupKey(eventName: string, payload: unknown): string {
  const obj = (payload && typeof payload === "object") ? payload as Record<string, unknown> : {};
  const eid = typeof obj.event_id === "string" ? obj.event_id : null;
  if (eid) return `id:${eid}`;
  // Fallback structural key — covers backends that haven't adopted event_id yet.
  const stage = typeof obj.stage === "string" ? obj.stage
    : typeof obj.agent === "string" ? obj.agent : "";
  const seq = typeof obj.sequence === "number" ? obj.sequence : "";
  return `s:${eventName}:${stage}:${seq}`;
}

/**
 * Bounded-memory dedup set. The agentic stream emits at most a few hundred
 * events per pipeline run; we cap at 4096 to absorb worst-case
 * token-delta storms without leaking memory across long-lived sessions.
 */
export class SeenEventSet {
  private readonly seen = new Set<string>();
  private readonly order: string[] = [];
  constructor(private readonly capacity: number = 4096) {}

  /** Returns true if this is the first time we have seen `key`. */
  add(key: string): boolean {
    if (this.seen.has(key)) return false;
    this.seen.add(key);
    this.order.push(key);
    if (this.order.length > this.capacity) {
      const evict = this.order.shift();
      if (evict !== undefined) this.seen.delete(evict);
    }
    return true;
  }

  has(key: string): boolean {
    return this.seen.has(key);
  }

  reset(): void {
    this.seen.clear();
    this.order.length = 0;
  }

  get size(): number {
    return this.seen.size;
  }
}
