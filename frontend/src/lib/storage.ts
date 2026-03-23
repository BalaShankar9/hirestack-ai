import { supabase } from "@/lib/supabase";
import { ALLOWED_STORAGE_BUCKETS } from "@/lib/sanitize";

export type StorageRef = {
  bucket: string;
  path: string;
};

export function isHttpUrl(value: string): boolean {
  return /^https?:\/\//i.test(value);
}

/**
 * Storage reference format used across the app:
 *   storage://<bucket>/<path>
 *
 * Example:
 *   storage://uploads/<uid>/evidence/file_abc.pdf
 */
export function parseStorageRef(value: string): StorageRef | null {
  if (!value) return null;
  if (!value.startsWith("storage://")) return null;

  const rest = value.slice("storage://".length);
  const firstSlash = rest.indexOf("/");
  if (firstSlash <= 0) return null;

  const bucket = rest.slice(0, firstSlash).trim();
  const path = rest.slice(firstSlash + 1).trim();
  if (!bucket || !path) return null;

  return { bucket, path };
}

export async function resolveFileUrl(
  urlOrRef: string | undefined,
  expiresInSeconds = 60 * 10
): Promise<string | null> {
  if (!urlOrRef) return null;
  if (isHttpUrl(urlOrRef)) return urlOrRef;

  const parsed = parseStorageRef(urlOrRef);
  if (!parsed) return null;

  // Validate bucket against allowlist (M9-F9)
  if (!ALLOWED_STORAGE_BUCKETS.has(parsed.bucket)) {
    console.warn(`[Storage] Blocked access to disallowed bucket: ${parsed.bucket}`);
    return null;
  }

  const { data, error } = await supabase.storage
    .from(parsed.bucket)
    .createSignedUrl(parsed.path, expiresInSeconds);
  if (error) throw error;
  return data.signedUrl;
}

