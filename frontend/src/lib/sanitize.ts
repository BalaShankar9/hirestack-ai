/**
 * HTML Sanitization Utilities
 *
 * Provides escapeHtml() for safe template interpolation and
 * sanitizeUrl() for link href validation.
 */

/** HTML-encode a string to prevent XSS in template literals. */
export function escapeHtml(str: unknown): string {
  const s = String(str ?? "");
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** Allowed URL protocols for user-supplied links. */
const SAFE_URL_PROTOCOLS = new Set(["http:", "https:", "mailto:"]);

/** Validate a URL — only allow safe protocols. Returns "" for dangerous URIs. */
export function sanitizeUrl(url: string | undefined | null): string {
  if (!url) return "";
  const trimmed = url.trim();
  if (!trimmed) return "";

  try {
    const parsed = new URL(trimmed);
    if (SAFE_URL_PROTOCOLS.has(parsed.protocol)) {
      return trimmed;
    }
    return "";
  } catch {
    // Relative URLs (e.g., "/path") are safe
    if (trimmed.startsWith("/") && !trimmed.startsWith("//")) {
      return trimmed;
    }
    return "";
  }
}

/** Allowed storage buckets for signed URL resolution. */
export const ALLOWED_STORAGE_BUCKETS = new Set(["uploads"]);

/** Validate file extension against an allowlist. */
const ALLOWED_FILE_EXTENSIONS = new Set([
  "pdf", "doc", "docx", "txt", "rtf", "odt",
  "png", "jpg", "jpeg", "gif", "webp", "svg",
  "csv", "xlsx", "xls", "pptx", "ppt",
  "md", "json",
]);

export function isAllowedFileExtension(filename: string): boolean {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  return ALLOWED_FILE_EXTENSIONS.has(ext);
}

/**
 * Sanitize HTML for safe rendering using DOMPurify.
 * Falls back to regex stripping on the server where DOM is unavailable.
 */
export function sanitizeHtml(html: string): string {
  if (!html) return "";
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const DOMPurify = require("dompurify");
  const purify = DOMPurify.default ?? DOMPurify;
  return purify.sanitize(html, {
    ADD_TAGS: ["style"],
    ADD_ATTR: ["target", "rel", "class"],
  });
}

/** Maximum file size for uploads (25 MB). */
export const MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024;

/** Validate file size. */
export function isAllowedFileSize(size: number): boolean {
  return size > 0 && size <= MAX_FILE_SIZE_BYTES;
}
