export { HirestackSdk, SdkError, sdk } from "./client";
export type {
  AIMSourceCard,
  AIMSourceCreatePayload,
  paths,
} from "./schema";

// PR m9-pr35 (M10 exit gate): consume the generated event-envelope types so
// the codegen drift workflow has a real downstream consumer in TypeScript.
export type { EventEnvelope } from "../../types/events";
