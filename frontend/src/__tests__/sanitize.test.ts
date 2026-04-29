/**
 * S8-F1: Behavioural pinning for src/lib/sanitize.ts.
 *
 * XSS-critical primitives — escapeHtml, sanitizeUrl, sanitizeHtml
 * (server + client paths), file-type allowlist, file-size allowlist,
 * storage bucket allowlist.
 */
import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import {
  escapeHtml,
  sanitizeUrl,
  sanitizeHtml,
  isAllowedFileExtension,
  isAllowedFileSize,
  ALLOWED_STORAGE_BUCKETS,
  MAX_FILE_SIZE_BYTES,
} from "@/lib/sanitize";

// ---------------------------------------------------------------------------
// escapeHtml
// ---------------------------------------------------------------------------

describe("escapeHtml", () => {
  it("encodes the five core HTML metacharacters", () => {
    expect(escapeHtml(`<script>alert("x")</script>`)).toBe(
      "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;",
    );
  });

  it("encodes single quotes as &#39; (numeric entity)", () => {
    expect(escapeHtml("it's")).toBe("it&#39;s");
  });

  it("encodes & first so existing entities are double-escaped", () => {
    // This is the documented invariant: & always becomes &amp; first,
    // even if the input already contains an entity.
    expect(escapeHtml("&amp;")).toBe("&amp;amp;");
  });

  it("returns empty string for null and undefined", () => {
    expect(escapeHtml(null)).toBe("");
    expect(escapeHtml(undefined)).toBe("");
  });

  it("coerces numbers and booleans to strings before escaping", () => {
    expect(escapeHtml(42)).toBe("42");
    expect(escapeHtml(true)).toBe("true");
  });

  it("returns empty string when given empty string", () => {
    expect(escapeHtml("")).toBe("");
  });

  it("leaves a plain ASCII string untouched", () => {
    expect(escapeHtml("hello world")).toBe("hello world");
  });
});

// ---------------------------------------------------------------------------
// sanitizeUrl
// ---------------------------------------------------------------------------

describe("sanitizeUrl", () => {
  it("allows http URLs", () => {
    expect(sanitizeUrl("http://example.com")).toBe("http://example.com");
  });

  it("allows https URLs", () => {
    expect(sanitizeUrl("https://example.com/path")).toBe(
      "https://example.com/path",
    );
  });

  it("allows mailto URLs", () => {
    expect(sanitizeUrl("mailto:a@b.com")).toBe("mailto:a@b.com");
  });

  it("blocks javascript: URLs", () => {
    expect(sanitizeUrl("javascript:alert(1)")).toBe("");
  });

  it("blocks data: URLs", () => {
    expect(sanitizeUrl("data:text/html,<script>alert(1)</script>")).toBe("");
  });

  it("blocks file: URLs", () => {
    expect(sanitizeUrl("file:///etc/passwd")).toBe("");
  });

  it("blocks vbscript: URLs", () => {
    expect(sanitizeUrl("vbscript:msgbox(1)")).toBe("");
  });

  it("returns empty string for null/undefined/empty", () => {
    expect(sanitizeUrl(null)).toBe("");
    expect(sanitizeUrl(undefined)).toBe("");
    expect(sanitizeUrl("")).toBe("");
  });

  it("returns empty string when input is only whitespace", () => {
    expect(sanitizeUrl("   ")).toBe("");
  });

  it("trims whitespace before parsing", () => {
    expect(sanitizeUrl("  https://x.com  ")).toBe("https://x.com");
  });

  it("allows root-relative paths", () => {
    expect(sanitizeUrl("/dashboard")).toBe("/dashboard");
  });

  it("blocks protocol-relative URLs (//evil.com)", () => {
    // Protocol-relative URLs are dangerous — they inherit the page's protocol
    // and can be used to bypass http→https checks. The contract explicitly
    // requires NOT starting with `//`.
    expect(sanitizeUrl("//evil.com")).toBe("");
  });

  it("blocks bare strings that fail URL parsing and aren't root-relative", () => {
    expect(sanitizeUrl("not a url")).toBe("");
  });
});

// ---------------------------------------------------------------------------
// sanitizeHtml — client path (jsdom provides DOMParser)
// ---------------------------------------------------------------------------

describe("sanitizeHtml — client path (DOMParser available)", () => {
  it("returns empty string for empty input", () => {
    expect(sanitizeHtml("")).toBe("");
  });

  it("strips <script> tags entirely (content removed)", () => {
    const out = sanitizeHtml("<p>hi</p><script>alert(1)</script>");
    expect(out).toContain("<p>hi</p>");
    expect(out).not.toContain("<script");
    expect(out).not.toContain("alert(1)");
  });

  it("strips <iframe> tags entirely", () => {
    const out = sanitizeHtml(`<iframe src="evil"></iframe><p>ok</p>`);
    expect(out).not.toContain("<iframe");
    expect(out).toContain("<p>ok</p>");
  });

  it("strips <object>, <embed>, <form>, <link>, <meta>, <base>", () => {
    for (const tag of ["object", "embed", "form", "link", "meta", "base"]) {
      const out = sanitizeHtml(`<${tag}></${tag}><p>x</p>`);
      expect(out).not.toContain(`<${tag}`);
      expect(out).toContain("<p>x</p>");
    }
  });

  it("unwraps unknown but non-dangerous tags, keeping children", () => {
    const out = sanitizeHtml("<custom-thing><span>kept</span></custom-thing>");
    expect(out).toContain("kept");
    expect(out).not.toContain("custom-thing");
  });

  it("removes inline event handler attributes (onclick, onerror)", () => {
    const out = sanitizeHtml(`<p onclick="alert(1)">hi</p>`);
    expect(out).not.toContain("onclick");
    expect(out).toContain(">hi</p>");
  });

  it("strips javascript: URLs from href attributes", () => {
    const out = sanitizeHtml(`<a href="javascript:alert(1)">click</a>`);
    expect(out).not.toMatch(/href="javascript:/i);
  });

  it("strips javascript: URLs from src attributes", () => {
    const out = sanitizeHtml(`<img src="javascript:alert(1)" alt="x">`);
    expect(out).not.toMatch(/src="javascript:/i);
  });

  it("strips javascript: URLs even with whitespace obfuscation", () => {
    // The contract uses .replace(/\s/g, "") before checking startsWith.
    const out = sanitizeHtml(`<a href="java\nscript:alert(1)">x</a>`);
    expect(out).not.toMatch(/href="java/i);
  });

  it("removes attributes not in the safe allowlist (e.g. ping, formaction)", () => {
    const out = sanitizeHtml(`<a href="/x" ping="https://evil" formaction="/x">y</a>`);
    expect(out).not.toContain("ping=");
    expect(out).not.toContain("formaction=");
    expect(out).toContain('href="/x"');
  });

  it("preserves safe formatting tags (p, h1-h6, ul, ol, li, strong, em)", () => {
    const out = sanitizeHtml(
      "<h1>t</h1><p><strong>b</strong> <em>i</em></p><ul><li>x</li></ul>",
    );
    expect(out).toContain("<h1>t</h1>");
    expect(out).toContain("<strong>b</strong>");
    expect(out).toContain("<em>i</em>");
    expect(out).toContain("<li>x</li>");
  });

  it("preserves safe table tags", () => {
    const out = sanitizeHtml(
      "<table><thead><tr><th>h</th></tr></thead><tbody><tr><td>d</td></tr></tbody></table>",
    );
    expect(out).toContain("<table>");
    expect(out).toContain("<thead>");
    expect(out).toContain("<th>h</th>");
    expect(out).toContain("<td>d</td>");
  });

  it("preserves <a> with href, target, rel and class attributes", () => {
    const out = sanitizeHtml(
      `<a href="https://x.com" target="_blank" rel="noopener" class="link">x</a>`,
    );
    expect(out).toContain('href="https://x.com"');
    expect(out).toContain('target="_blank"');
    expect(out).toContain('rel="noopener"');
    expect(out).toContain('class="link"');
  });

  it("preserves data-section / data-module / role / aria-label attributes", () => {
    const out = sanitizeHtml(
      `<div data-section="s" data-module="m" role="region" aria-label="x">y</div>`,
    );
    expect(out).toContain('data-section="s"');
    expect(out).toContain('data-module="m"');
    expect(out).toContain('role="region"');
    expect(out).toContain('aria-label="x"');
  });

  it("recursively sanitizes nested dangerous content", () => {
    const out = sanitizeHtml(
      "<div><section><p>ok</p><script>x</script></section></div>",
    );
    expect(out).toContain("<p>ok</p>");
    expect(out).not.toContain("<script");
  });
});

// ---------------------------------------------------------------------------
// sanitizeHtml — server path (no DOMParser, regex strip)
// ---------------------------------------------------------------------------

describe("sanitizeHtml — server path (no window)", () => {
  let originalWindow: typeof globalThis.window | undefined;

  beforeEach(() => {
    originalWindow = globalThis.window;
    // Force the server-side branch by removing window.
    // @ts-expect-error — intentionally removing for the server-path test.
    delete globalThis.window;
  });

  afterEach(() => {
    if (originalWindow !== undefined) {
      // @ts-expect-error — restoring after test.
      globalThis.window = originalWindow;
    }
  });

  it("strips <script>...</script> blocks via regex", () => {
    expect(sanitizeHtml("<p>a</p><script>evil()</script><p>b</p>")).toBe(
      "<p>a</p><p>b</p>",
    );
  });

  it("strips <iframe>...</iframe> blocks", () => {
    expect(sanitizeHtml(`<iframe src="x"></iframe><p>y</p>`)).toBe("<p>y</p>");
  });

  it("strips <object>, <embed>, <form>", () => {
    expect(sanitizeHtml("<object></object><embed><form></form><p>z</p>")).toBe(
      "<p>z</p>",
    );
  });

  it("strips inline on* event handler attributes", () => {
    const out = sanitizeHtml(`<p onclick="alert(1)" onerror="x">hi</p>`);
    expect(out).not.toContain("onclick");
    expect(out).not.toContain("onerror");
    expect(out).toContain("<p");
    expect(out).toContain(">hi</p>");
  });

  it("strips literal javascript: URI prefix", () => {
    const out = sanitizeHtml(`<a href="javascript:alert(1)">x</a>`);
    expect(out).not.toContain("javascript:");
  });
});

// ---------------------------------------------------------------------------
// File extension allowlist
// ---------------------------------------------------------------------------

describe("isAllowedFileExtension", () => {
  it("accepts pdf/doc/docx/txt/rtf/odt", () => {
    for (const ext of ["pdf", "doc", "docx", "txt", "rtf", "odt"]) {
      expect(isAllowedFileExtension(`file.${ext}`)).toBe(true);
    }
  });

  it("accepts common image formats", () => {
    for (const ext of ["png", "jpg", "jpeg", "gif", "webp", "svg"]) {
      expect(isAllowedFileExtension(`x.${ext}`)).toBe(true);
    }
  });

  it("accepts spreadsheet formats", () => {
    for (const ext of ["csv", "xlsx", "xls", "pptx", "ppt"]) {
      expect(isAllowedFileExtension(`x.${ext}`)).toBe(true);
    }
  });

  it("accepts md and json", () => {
    expect(isAllowedFileExtension("x.md")).toBe(true);
    expect(isAllowedFileExtension("x.json")).toBe(true);
  });

  it("rejects executable extensions (exe, sh, js, html)", () => {
    expect(isAllowedFileExtension("a.exe")).toBe(false);
    expect(isAllowedFileExtension("a.sh")).toBe(false);
    expect(isAllowedFileExtension("a.js")).toBe(false);
    expect(isAllowedFileExtension("a.html")).toBe(false);
  });

  it("is case-insensitive", () => {
    expect(isAllowedFileExtension("FILE.PDF")).toBe(true);
    expect(isAllowedFileExtension("Photo.JPG")).toBe(true);
  });

  it("uses the LAST dot as the extension separator", () => {
    expect(isAllowedFileExtension("archive.tar.pdf")).toBe(true);
    expect(isAllowedFileExtension("archive.tar.exe")).toBe(false);
  });

  it("rejects files with no extension", () => {
    expect(isAllowedFileExtension("README")).toBe(false);
  });

  it("rejects empty string", () => {
    expect(isAllowedFileExtension("")).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// File size allowlist
// ---------------------------------------------------------------------------

describe("isAllowedFileSize", () => {
  it("MAX_FILE_SIZE_BYTES is exactly 25 MiB", () => {
    expect(MAX_FILE_SIZE_BYTES).toBe(25 * 1024 * 1024);
  });

  it("accepts 1 byte", () => {
    expect(isAllowedFileSize(1)).toBe(true);
  });

  it("accepts the boundary (exactly 25 MiB)", () => {
    expect(isAllowedFileSize(MAX_FILE_SIZE_BYTES)).toBe(true);
  });

  it("rejects one byte above the boundary", () => {
    expect(isAllowedFileSize(MAX_FILE_SIZE_BYTES + 1)).toBe(false);
  });

  it("rejects zero bytes", () => {
    expect(isAllowedFileSize(0)).toBe(false);
  });

  it("rejects negative byte counts", () => {
    expect(isAllowedFileSize(-1)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Storage bucket allowlist
// ---------------------------------------------------------------------------

describe("ALLOWED_STORAGE_BUCKETS", () => {
  it("contains exactly the 'uploads' bucket", () => {
    expect(ALLOWED_STORAGE_BUCKETS.has("uploads")).toBe(true);
    expect(ALLOWED_STORAGE_BUCKETS.size).toBe(1);
  });

  it("does not contain commonly attempted bucket names", () => {
    expect(ALLOWED_STORAGE_BUCKETS.has("public")).toBe(false);
    expect(ALLOWED_STORAGE_BUCKETS.has("private")).toBe(false);
    expect(ALLOWED_STORAGE_BUCKETS.has("admin")).toBe(false);
  });
});
