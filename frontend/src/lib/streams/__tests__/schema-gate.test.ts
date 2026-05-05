import { describe, expect, it } from "vitest";

import {
  MIN_ACCEPTED_SCHEMA,
  SeenEventSet,
  eventDedupKey,
  isSchemaAccepted,
} from "@/lib/streams/schema-gate";

describe("schema-gate / isSchemaAccepted", () => {
  it("accepts payloads with a matching major version", () => {
    expect(isSchemaAccepted({ schema_version: "1.0" })).toBe(true);
    expect(isSchemaAccepted({ schema_version: "1.7" })).toBe(true);
    expect(isSchemaAccepted({ schema_version: "1.99.3" })).toBe(true);
  });

  it("rejects payloads from a future major schema", () => {
    expect(isSchemaAccepted({ schema_version: "2.0" })).toBe(false);
    expect(isSchemaAccepted({ schema_version: "10.0" })).toBe(false);
  });

  it("rejects malformed schema strings", () => {
    expect(isSchemaAccepted({ schema_version: 1 })).toBe(false);
    expect(isSchemaAccepted({ schema_version: "abc" })).toBe(false);
  });

  it("treats unversioned/legacy payloads as accepted", () => {
    expect(isSchemaAccepted({})).toBe(true);
    expect(isSchemaAccepted({ schema_version: undefined })).toBe(true);
    expect(isSchemaAccepted(null)).toBe(true);
    expect(isSchemaAccepted("not-an-object")).toBe(true);
  });

  it("exposes the current contract major", () => {
    expect(MIN_ACCEPTED_SCHEMA.split(".")[0]).toBe("1");
  });
});

describe("schema-gate / eventDedupKey", () => {
  it("prefers event_id when present", () => {
    expect(eventDedupKey("agent_status", { event_id: "abc-123" })).toBe("id:abc-123");
  });

  it("falls back to event:stage:sequence when event_id missing", () => {
    expect(eventDedupKey("agent_status", { stage: "writer", sequence: 7 }))
      .toBe("s:agent_status:writer:7");
  });

  it("falls back to agent when stage missing", () => {
    expect(eventDedupKey("agent_status", { agent: "reviewer", sequence: 3 }))
      .toBe("s:agent_status:reviewer:3");
  });
});

describe("schema-gate / SeenEventSet", () => {
  it("returns true the first time and false on replays", () => {
    const seen = new SeenEventSet();
    expect(seen.add("id:1")).toBe(true);
    expect(seen.add("id:1")).toBe(false);
    expect(seen.add("id:2")).toBe(true);
    expect(seen.size).toBe(2);
  });

  it("evicts oldest keys past capacity (bounded memory)", () => {
    const seen = new SeenEventSet(3);
    seen.add("a"); seen.add("b"); seen.add("c"); seen.add("d");
    expect(seen.has("a")).toBe(false); // evicted
    expect(seen.has("d")).toBe(true);
    expect(seen.size).toBe(3);
  });

  it("reset() clears state", () => {
    const seen = new SeenEventSet();
    seen.add("x");
    seen.reset();
    expect(seen.size).toBe(0);
    expect(seen.add("x")).toBe(true);
  });
});
