/**
 * GENERATED — do not edit by hand.
 *
 * PR m4-pr13: hand-curated subset of the OpenAPI schema scoped to the
 * endpoints migrated in this PR (AIM sources). Run
 * `tools/codegen/openapi.sh` against a live backend to regenerate the
 * full surface. This file is committed so CI can `git diff --exit-code`
 * to detect drift between backend routes and the typed SDK.
 *
 * All paths are mounted under both `/api/...` (legacy) and
 * `/api/v1/...` (new). The SDK targets the v1 mount point.
 */

export interface AIMSourceCard {
  id: string;
  assignment_id: string;
  source_type: string;
  title: string | null;
  authors: string[];
  year: number | null;
  publisher?: string | null;
  journal?: string | null;
  doi?: string | null;
  url?: string | null;
  reliability_tier: string;
  verification_status: string;
  created_at: string;
  updated_at: string;
}

export interface AIMSourceCreatePayload {
  source_type?: string;
  title?: string | null;
  authors?: string[];
  year?: number | null;
  publisher?: string | null;
  journal?: string | null;
  doi?: string | null;
  url?: string | null;
}

export interface paths {
  "/api/v1/aim/assignments/{assignment_id}/sources": {
    get: {
      parameters: { path: { assignment_id: string } };
      responses: { 200: { content: { "application/json": AIMSourceCard[] } } };
    };
    post: {
      parameters: { path: { assignment_id: string } };
      requestBody: { content: { "application/json": AIMSourceCreatePayload } };
      responses: { 201: { content: { "application/json": AIMSourceCard } } };
    };
  };
  "/api/v1/aim/sources/{source_id}": {
    get: {
      parameters: { path: { source_id: string } };
      responses: { 200: { content: { "application/json": AIMSourceCard } } };
    };
    delete: {
      parameters: { path: { source_id: string } };
      responses: { 204: { content: never } };
    };
  };
}
