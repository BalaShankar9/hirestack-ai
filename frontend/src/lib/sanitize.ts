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
 * Sanitize HTML for safe rendering.
 * Uses a tag-strip approach on the server (no DOM available).
 * On the client, uses the browser DOMParser for proper sanitization.
 */
export function sanitizeHtml(html: string): string {
  if (!html) return "";

  // Server-side: no DOM available — strip dangerous tags and attributes
  if (typeof window === "undefined") {
    return html
      .replace(/<script[\s\S]*?<\/script>/gi, "")
      .replace(/<iframe[\s\S]*?<\/iframe>/gi, "")
      .replace(/<object[\s\S]*?<\/object>/gi, "")
      .replace(/<embed[^>]*>/gi, "")
      .replace(/<form[\s\S]*?<\/form>/gi, "")
      .replace(/on\w+\s*=\s*["'][^"']*["']/gi, "")
      .replace(/javascript\s*:/gi, "");
  }

  // Client-side: use browser DOMParser for proper sanitization
  const SAFE_TAGS = new Set([
    "h1", "h2", "h3", "h4", "h5", "h6",
    "p", "br", "hr",
    "b", "strong", "i", "em", "u", "s", "mark", "small", "sub", "sup",
    "ul", "ol", "li",
    "a",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption",
    "div", "span", "section", "article", "header", "footer",
    "blockquote", "pre", "code",
    "img",
    "figure", "figcaption",
    "details", "summary",
    "dl", "dt", "dd",
    "style",
  ]);

  const SAFE_ATTRS = new Set([
    "class", "style", "id", "href", "target", "rel", "title",
    "src", "alt", "width", "height", "loading",
    "colspan", "rowspan", "scope", "start", "type",
    "data-section", "data-module", "role", "aria-label",
  ]);

  const parser = new DOMParser();
  const doc = parser.parseFromString(html, "text/html");

  function sanitizeNode(node: Node): void {
    const children = Array.from(node.childNodes);
    for (const child of children) {
      if (child.nodeType === Node.ELEMENT_NODE) {
        const el = child as Element;
        const tag = el.tagName.toLowerCase();

        if (!SAFE_TAGS.has(tag)) {
          // Dangerous tags: remove entirely (script, iframe, object, etc.)
          if (["script", "iframe", "object", "embed", "form", "link", "meta", "base"].includes(tag)) {
            el.remove();
            continue;
          }
          // Unknown but non-dangerous tags: unwrap (keep children)
          while (el.firstChild) {
            node.insertBefore(el.firstChild, el);
          }
          el.remove();
          continue;
        }

        // Remove unsafe attributes
        const attrs = Array.from(el.attributes);
        for (const attr of attrs) {
          if (!SAFE_ATTRS.has(attr.name)) {
            el.removeAttribute(attr.name);
          }
          // Block javascript: URLs in href/src
          if ((attr.name === "href" || attr.name === "src") &&
              attr.value.replace(/\s/g, "").toLowerCase().startsWith("javascript:")) {
            el.removeAttribute(attr.name);
          }
        }

        sanitizeNode(el);
      }
    }
  }

  sanitizeNode(doc.body);
  return doc.body.innerHTML;
}

/** Maximum file size for uploads (25 MB). */
export const MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024;

/** Validate file size. */
export function isAllowedFileSize(size: number): boolean {
  return size > 0 && size <= MAX_FILE_SIZE_BYTES;
}
