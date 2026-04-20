import { describe, it, expect } from "vitest";
import {
  isTerminalUsableJobStatus,
  TERMINAL_USABLE_JOB_STATUSES,
  type GenerationJobStatus,
} from "@/lib/firestore/models";

describe("GenerationJobStatus contract", () => {
  it("includes succeeded_with_warnings as a valid status literal", () => {
    // Type-level assertion: this line will fail to compile if
    // succeeded_with_warnings is removed from the union.
    const s: GenerationJobStatus = "succeeded_with_warnings";
    expect(s).toBe("succeeded_with_warnings");
  });

  it("treats both succeeded and succeeded_with_warnings as terminal-usable", () => {
    expect(isTerminalUsableJobStatus("succeeded")).toBe(true);
    expect(isTerminalUsableJobStatus("succeeded_with_warnings")).toBe(true);
  });

  it("does not treat in-flight or failure states as terminal-usable", () => {
    expect(isTerminalUsableJobStatus("queued")).toBe(false);
    expect(isTerminalUsableJobStatus("running")).toBe(false);
    expect(isTerminalUsableJobStatus("failed")).toBe(false);
    expect(isTerminalUsableJobStatus("cancelled")).toBe(false);
  });

  it("safely returns false for null/undefined/empty", () => {
    expect(isTerminalUsableJobStatus(null)).toBe(false);
    expect(isTerminalUsableJobStatus(undefined)).toBe(false);
    expect(isTerminalUsableJobStatus("")).toBe(false);
  });

  it("exposes a frozen set of terminal-usable statuses for downstream code", () => {
    expect(TERMINAL_USABLE_JOB_STATUSES.has("succeeded")).toBe(true);
    expect(TERMINAL_USABLE_JOB_STATUSES.has("succeeded_with_warnings")).toBe(true);
    expect(TERMINAL_USABLE_JOB_STATUSES.size).toBe(2);
  });
});
