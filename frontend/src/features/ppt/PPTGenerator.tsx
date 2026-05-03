"use client";

/**
 * PPTGenerator — Interactive presentation builder component.
 *
 * Allows users to:
 *   • Describe a topic (required, 2-2000 chars)
 *   • Pick audience, slide count (3-30), tone, theme
 *   • Preview an outline (POST /api/ppt/outline)
 *   • Generate and download the .pptx (POST /api/ppt/generate)
 */
import React, { useState } from "react";

type Theme = "modern" | "minimal" | "corporate" | "investor";

interface PPTRequest {
  topic: string;
  audience: string;
  slide_count: number;
  tone: string;
  theme: Theme;
  extra_context: string;
}

interface OutlineSection {
  title: string;
  bullets?: string[];
  kind?: string;
}

const DEFAULT_REQ: PPTRequest = {
  topic: "",
  audience: "",
  slide_count: 10,
  tone: "",
  theme: "modern",
  extra_context: "",
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "/api";

export default function PPTGenerator() {
  const [form, setForm] = useState<PPTRequest>(DEFAULT_REQ);
  const [outline, setOutline] = useState<OutlineSection[] | null>(null);
  const [status, setStatus] = useState<"idle" | "outlining" | "generating" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);

  const update = <K extends keyof PPTRequest>(key: K, value: PPTRequest[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const buildPayload = () => {
    const payload: Record<string, unknown> = {
      topic: form.topic.trim(),
      slide_count: form.slide_count,
      theme: form.theme,
    };
    if (form.audience.trim()) payload.audience = form.audience.trim();
    if (form.tone.trim()) payload.tone = form.tone.trim();
    if (form.extra_context.trim()) payload.extra_context = form.extra_context.trim();
    return payload;
  };

  const fetchOutline = async () => {
    if (!form.topic.trim()) {
      setError("Topic is required.");
      return;
    }
    setStatus("outlining");
    setError(null);
    try {
      const resp = await fetch(`${API_BASE}/ppt/outline`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(buildPayload()),
      });
      if (!resp.ok) {
        const detail = await resp.text();
        throw new Error(`Outline failed (${resp.status}): ${detail}`);
      }
      const data = await resp.json();
      const sections: OutlineSection[] = Array.isArray(data?.slides)
        ? data.slides.map((s: any) => ({
            title: s.title || "Untitled",
            bullets: s.bullets ?? [],
            kind: s.kind ?? "content",
          }))
        : [];
      setOutline(sections);
      setStatus("idle");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus("error");
    }
  };

  const generateAndDownload = async () => {
    if (!form.topic.trim()) {
      setError("Topic is required.");
      return;
    }
    setStatus("generating");
    setError(null);
    setDownloadUrl(null);
    try {
      const resp = await fetch(`${API_BASE}/ppt/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(buildPayload()),
      });
      if (!resp.ok) {
        const detail = await resp.text();
        throw new Error(`Generation failed (${resp.status}): ${detail}`);
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      setDownloadUrl(url);
      // Auto-download
      const a = document.createElement("a");
      a.href = url;
      a.download = `${form.topic.replace(/[^a-z0-9]+/gi, "_").slice(0, 80) || "presentation"}.pptx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setStatus("idle");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus("error");
    }
  };

  const isBusy = status === "outlining" || status === "generating";

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6">
      <header className="space-y-2">
        <h1 className="text-3xl font-bold tracking-tight">PPT Generator</h1>
        <p className="text-sm text-neutral-500">
          Generate investor-grade presentations from a topic. Preview the outline before downloading the .pptx.
        </p>
      </header>

      <section className="grid gap-4 rounded-xl border p-6 bg-white dark:bg-neutral-900 shadow-sm">
        <label className="space-y-1">
          <span className="text-sm font-medium">Topic *</span>
          <textarea
            className="w-full rounded border p-2 min-h-[80px] bg-transparent"
            value={form.topic}
            maxLength={2000}
            placeholder="e.g. Q2 2026 go-to-market plan for our Series B launch"
            onChange={(e) => update("topic", e.target.value)}
            disabled={isBusy}
          />
        </label>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <label className="space-y-1">
            <span className="text-sm font-medium">Audience</span>
            <input
              className="w-full rounded border p-2 bg-transparent"
              value={form.audience}
              maxLength={500}
              placeholder="e.g. Series B investors, board members"
              onChange={(e) => update("audience", e.target.value)}
              disabled={isBusy}
            />
          </label>
          <label className="space-y-1">
            <span className="text-sm font-medium">Tone</span>
            <input
              className="w-full rounded border p-2 bg-transparent"
              value={form.tone}
              maxLength={200}
              placeholder="e.g. confident, data-driven"
              onChange={(e) => update("tone", e.target.value)}
              disabled={isBusy}
            />
          </label>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <label className="space-y-1">
            <span className="text-sm font-medium">Slide count</span>
            <input
              type="number"
              min={3}
              max={30}
              value={form.slide_count}
              onChange={(e) => update("slide_count", Math.max(3, Math.min(30, Number(e.target.value) || 10)))}
              className="w-full rounded border p-2 bg-transparent"
              disabled={isBusy}
            />
          </label>
          <label className="space-y-1">
            <span className="text-sm font-medium">Theme</span>
            <select
              value={form.theme}
              onChange={(e) => update("theme", e.target.value as Theme)}
              className="w-full rounded border p-2 bg-transparent"
              disabled={isBusy}
            >
              <option value="modern">Modern</option>
              <option value="minimal">Minimal</option>
              <option value="corporate">Corporate</option>
              <option value="investor">Investor Deck</option>
            </select>
          </label>
        </div>

        <label className="space-y-1">
          <span className="text-sm font-medium">Additional context</span>
          <textarea
            className="w-full rounded border p-2 min-h-[60px] bg-transparent"
            value={form.extra_context}
            maxLength={10000}
            placeholder="Any data, existing bullet points, constraints, or links."
            onChange={(e) => update("extra_context", e.target.value)}
            disabled={isBusy}
          />
        </label>

        <div className="flex flex-wrap gap-3 pt-2">
          <button
            type="button"
            onClick={fetchOutline}
            disabled={isBusy}
            className="px-4 py-2 rounded-lg border bg-neutral-100 dark:bg-neutral-800 hover:bg-neutral-200 disabled:opacity-50"
          >
            {status === "outlining" ? "Building outline…" : "Preview outline"}
          </button>
          <button
            type="button"
            onClick={generateAndDownload}
            disabled={isBusy}
            className="px-4 py-2 rounded-lg bg-black text-white hover:bg-neutral-800 disabled:opacity-50"
          >
            {status === "generating" ? "Generating .pptx…" : "Generate & Download"}
          </button>
          {downloadUrl && (
            <a
              href={downloadUrl}
              download={`${form.topic.replace(/[^a-z0-9]+/gi, "_").slice(0, 80) || "presentation"}.pptx`}
              className="px-4 py-2 rounded-lg border text-sm self-center"
            >
              Re-download last deck
            </a>
          )}
        </div>

        {error && (
          <p className="text-sm text-red-600 whitespace-pre-wrap">{error}</p>
        )}
      </section>

      {outline && outline.length > 0 && (
        <section className="rounded-xl border p-6 bg-white dark:bg-neutral-900">
          <h2 className="text-xl font-semibold mb-3">Outline preview</h2>
          <ol className="space-y-3 list-decimal list-inside">
            {outline.map((s, i) => (
              <li key={i} className="space-y-1">
                <div className="font-medium">{s.title}</div>
                {s.bullets && s.bullets.length > 0 && (
                  <ul className="list-disc list-inside pl-4 text-sm text-neutral-600 dark:text-neutral-400">
                    {s.bullets.map((b, j) => (
                      <li key={j}>{b}</li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}
