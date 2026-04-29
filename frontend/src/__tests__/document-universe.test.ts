/**
 * S8-F3: Behavioural pinning for src/lib/document-universe.ts.
 *
 * Locks the document type registry contract: cardinality, key uniqueness,
 * RECOMMENDED_KEYS coherence, group set, GROUP_META completeness, and the
 * findUniverseDoc / mergeWithUniverse helpers.
 */
import { describe, expect, it } from "vitest";
import {
  DOCUMENT_UNIVERSE,
  RECOMMENDED_KEYS,
  GROUP_META,
  TAILORED_UNIVERSE,
  BENCHMARK_UNIVERSE,
  findUniverseDoc,
  mergeWithUniverse,
} from "@/lib/document-universe";

const ALLOWED_GROUPS = new Set([
  "recommended",
  "professional",
  "executive",
  "academic",
  "compliance",
  "technical",
  "creative",
] as const);

describe("DOCUMENT_UNIVERSE — registry shape", () => {
  it("contains at least 50 entries (large catalogue)", () => {
    expect(DOCUMENT_UNIVERSE.length).toBeGreaterThanOrEqual(50);
  });

  it("every entry has key, label, description, recommended, group", () => {
    for (const d of DOCUMENT_UNIVERSE) {
      expect(typeof d.key).toBe("string");
      expect(d.key.length).toBeGreaterThan(0);
      expect(typeof d.label).toBe("string");
      expect(d.label.length).toBeGreaterThan(0);
      expect(typeof d.description).toBe("string");
      expect(d.description.length).toBeGreaterThan(0);
      expect(typeof d.recommended).toBe("boolean");
      expect(ALLOWED_GROUPS.has(d.group)).toBe(true);
    }
  });

  it("keys are globally unique", () => {
    const seen = new Set<string>();
    for (const d of DOCUMENT_UNIVERSE) {
      expect(seen.has(d.key)).toBe(false);
      seen.add(d.key);
    }
  });

  it("keys use snake_case (lowercase letters, digits, underscores only)", () => {
    for (const d of DOCUMENT_UNIVERSE) {
      expect(d.key).toMatch(/^[a-z0-9_]+$/);
    }
  });
});

describe("RECOMMENDED_KEYS coherence", () => {
  it("every key listed in RECOMMENDED_KEYS exists in DOCUMENT_UNIVERSE", () => {
    const keys = new Set(DOCUMENT_UNIVERSE.map((d) => d.key));
    for (const k of RECOMMENDED_KEYS) {
      expect(keys.has(k)).toBe(true);
    }
  });

  it("every entry with recommended=true is in group 'recommended'", () => {
    for (const d of DOCUMENT_UNIVERSE) {
      if (d.recommended) expect(d.group).toBe("recommended");
    }
  });

  it("every entry in group 'recommended' has recommended=true", () => {
    for (const d of DOCUMENT_UNIVERSE) {
      if (d.group === "recommended") expect(d.recommended).toBe(true);
    }
  });

  it("RECOMMENDED_KEYS includes the canonical 11-doc set (cv, resume, cover_letter, ...)", () => {
    expect(RECOMMENDED_KEYS).toContain("cv");
    expect(RECOMMENDED_KEYS).toContain("resume");
    expect(RECOMMENDED_KEYS).toContain("cover_letter");
    expect(RECOMMENDED_KEYS).toContain("personal_statement");
    expect(RECOMMENDED_KEYS).toContain("portfolio");
    expect(RECOMMENDED_KEYS).toContain("executive_summary");
    expect(RECOMMENDED_KEYS).toContain("elevator_pitch");
    expect(RECOMMENDED_KEYS).toContain("linkedin_summary");
    expect(RECOMMENDED_KEYS).toContain("skills_matrix");
    expect(RECOMMENDED_KEYS).toContain("interview_preparation");
    expect(RECOMMENDED_KEYS).toContain("competency_framework");
  });
});

describe("GROUP_META", () => {
  it("contains an entry for every group used by DOCUMENT_UNIVERSE", () => {
    const usedGroups = new Set(DOCUMENT_UNIVERSE.map((d) => d.group));
    for (const g of usedGroups) {
      expect(GROUP_META[g]).toBeDefined();
      expect(typeof GROUP_META[g].label).toBe("string");
      expect(GROUP_META[g].label.length).toBeGreaterThan(0);
      expect(typeof GROUP_META[g].order).toBe("number");
    }
  });

  it("recommended group has order 0 (sorts first)", () => {
    expect(GROUP_META.recommended.order).toBe(0);
  });

  it("group orders are unique (deterministic UI sort)", () => {
    const orders = Object.values(GROUP_META).map((m) => m.order);
    expect(new Set(orders).size).toBe(orders.length);
  });

  it("group orders are contiguous starting from 0", () => {
    const orders = Object.values(GROUP_META)
      .map((m) => m.order)
      .sort((a, b) => a - b);
    for (let i = 0; i < orders.length; i++) {
      expect(orders[i]).toBe(i);
    }
  });
});

describe("Deprecated aliases", () => {
  it("TAILORED_UNIVERSE is identity-equal to DOCUMENT_UNIVERSE", () => {
    expect(TAILORED_UNIVERSE).toBe(DOCUMENT_UNIVERSE);
  });

  it("BENCHMARK_UNIVERSE is identity-equal to DOCUMENT_UNIVERSE", () => {
    expect(BENCHMARK_UNIVERSE).toBe(DOCUMENT_UNIVERSE);
  });
});

describe("findUniverseDoc", () => {
  it("returns the entry for a known key", () => {
    const d = findUniverseDoc("cv");
    expect(d).toBeDefined();
    expect(d!.key).toBe("cv");
    expect(d!.recommended).toBe(true);
  });

  it("returns undefined for an unknown key", () => {
    expect(findUniverseDoc("nonexistent_key_xyz")).toBeUndefined();
  });

  it("ignores the deprecated _tier argument", () => {
    expect(findUniverseDoc("cv", "tailored")).toBe(findUniverseDoc("cv"));
    expect(findUniverseDoc("cv", "benchmark")).toBe(findUniverseDoc("cv"));
  });

  it("is case-sensitive", () => {
    expect(findUniverseDoc("CV")).toBeUndefined();
    expect(findUniverseDoc("Cover_Letter")).toBeUndefined();
  });
});

describe("mergeWithUniverse", () => {
  type Doc = { docType: string; status: string };

  it("returns one entry per universe def, in universe order", () => {
    const subset = DOCUMENT_UNIVERSE.slice(0, 3);
    const result = mergeWithUniverse(subset, []);
    expect(result).toHaveLength(3);
    expect(result.map((r) => r.def.key)).toEqual(subset.map((d) => d.key));
  });

  it("attaches the matching actual doc and leaves the rest as null", () => {
    const subset = DOCUMENT_UNIVERSE.slice(0, 2);
    const actual: Doc[] = [{ docType: subset[0].key, status: "completed" }];
    const result = mergeWithUniverse(subset, actual);
    expect(result[0].doc).toEqual(actual[0]);
    expect(result[1].doc).toBeNull();
  });

  it("returns null for every def when actual is empty", () => {
    const subset = DOCUMENT_UNIVERSE.slice(0, 4);
    const result = mergeWithUniverse(subset, []);
    expect(result.every((r) => r.doc === null)).toBe(true);
  });

  it("keeps the FIRST occurrence when the same docType appears multiple times (newest-first input)", () => {
    const subset = [DOCUMENT_UNIVERSE[0]];
    const actual: Doc[] = [
      { docType: subset[0].key, status: "first" },
      { docType: subset[0].key, status: "second" },
    ];
    const result = mergeWithUniverse(subset, actual);
    expect(result[0].doc!.status).toBe("first");
  });

  it("ignores actual docs whose docType is not in the universe slice", () => {
    const subset = [DOCUMENT_UNIVERSE[0]];
    const actual: Doc[] = [{ docType: "key_not_in_subset", status: "completed" }];
    const result = mergeWithUniverse(subset, actual);
    expect(result[0].doc).toBeNull();
  });

  it("returns empty array when universe is empty", () => {
    const result = mergeWithUniverse([], [{ docType: "cv", status: "completed" }]);
    expect(result).toEqual([]);
  });
});
