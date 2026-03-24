"use client";

import { memo, useMemo, useState } from "react";
import { diffWordsWithSpace } from "diff";
import {
  Download,
  FileType,
  FileImage,
  ClipboardCopy,
  Layers,
  Loader2,
  RefreshCw,
  UploadCloud,
  Check,
} from "lucide-react";

import { TipTapEditor } from "@/components/editor/tiptap-editor";
import { KeywordChips } from "@/components/workspace/keyword-chips";
import { ModeToggle, type DocMode } from "@/components/workspace/diff-toggle";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { sanitizeHtml } from "@/lib/sanitize";

function stripHtml(html: string) {
  return (html || "").replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
}

/* ------------------------------------------------------------------ */
/*  DocumentPreview — formatted read-only document display             */
/* ------------------------------------------------------------------ */

const DocumentPreview = memo(function DocumentPreview({ html }: { html: string }) {
  if (!html || !html.trim()) {
    return (
      <div className="rounded-2xl border border-dashed bg-card/50 p-12 text-center">
        <p className="text-sm text-muted-foreground">No content generated yet.</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[800px]">
      <div
        className="doc-preview"
        dangerouslySetInnerHTML={{ __html: sanitizeHtml(html) }}
      />
    </div>
  );
});

/* ------------------------------------------------------------------ */
/*  DiffView — memoized word-level diff                                */
/* ------------------------------------------------------------------ */

const DiffView = memo(function DiffView({
  baseHtml,
  nextHtml,
}: {
  baseHtml: string;
  nextHtml: string;
}) {
  const diffs = useMemo(() => {
    const base = stripHtml(baseHtml);
    const next = stripHtml(nextHtml);
    return diffWordsWithSpace(base, next);
  }, [baseHtml, nextHtml]);

  return (
    <div className="rounded-2xl border bg-card">
      <div className="px-4 py-3 text-sm font-semibold">
        Diff (base → tailored)
      </div>
      <Separator />
      <ScrollArea className="h-[520px]">
        <div className="p-4 text-sm leading-relaxed">
          {diffs.map((part, idx) => (
            <span
              key={idx}
              className={
                part.added
                  ? "bg-emerald-500/10 text-emerald-800 dark:text-emerald-400"
                  : part.removed
                    ? "bg-rose-500/10 text-rose-800 dark:text-rose-400 line-through"
                    : ""
              }
            >
              {part.value}
            </span>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
});

/* ------------------------------------------------------------------ */
/*  DocEditorModule — view + editor + keyword sidebar                  */
/* ------------------------------------------------------------------ */

interface DocEditorModuleProps {
  title: string;
  subtitle: string;
  mode: DocMode;
  onModeChange: (m: DocMode) => void;
  keywords: string[];
  missingKeywords: string[];
  isCovered: (k: string) => boolean;
  value: string;
  onChange: (html: string) => void;
  editorRef: any;
  onEditorReady?: (editor: any | null) => void;
  onPickEvidence: () => void;
  onRegenerate: () => void;
  onOpenVersions: () => void;
  baseHtml: string;
  isRegenerating?: boolean;
}

export const DocEditorModule = memo(function DocEditorModule({
  title,
  subtitle,
  mode,
  onModeChange,
  keywords,
  missingKeywords,
  isCovered,
  value,
  onChange,
  editorRef,
  onEditorReady,
  onPickEvidence,
  onRegenerate,
  onOpenVersions,
  baseHtml,
  isRegenerating = false,
}: DocEditorModuleProps) {
  const isViewMode = mode === "view";

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border bg-card p-5 shadow-soft-sm">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-sm font-semibold">{title}</div>
            <div className="mt-1 text-xs text-muted-foreground">{subtitle}</div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <ModeToggle mode={mode} onChange={onModeChange} />
            {!isViewMode && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-2 rounded-xl"
                  onClick={onOpenVersions}
                >
                  <Layers className="h-4 w-4" />
                  Versions
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-2 rounded-xl"
                  onClick={onPickEvidence}
                >
                  <UploadCloud className="h-4 w-4" />
                  Use evidence
                </Button>
              </>
            )}
            <Button
              variant="outline"
              size="sm"
              className="gap-2 rounded-xl"
              onClick={onRegenerate}
              disabled={isRegenerating}
            >
              {isRegenerating ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              {isRegenerating ? "Working…" : "Regenerate"}
            </Button>
          </div>
        </div>

        <Separator className="my-4" />

        {isViewMode ? (
          <DocumentPreview html={value} />
        ) : (
          <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
            <div className="min-w-0">
              {mode === "diff" ? (
                <DiffView baseHtml={baseHtml} nextHtml={value} />
              ) : (
                <TipTapEditor
                  content={value}
                  onChange={onChange}
                  editorRef={editorRef}
                  onReady={onEditorReady}
                  className="min-h-[560px]"
                />
              )}
            </div>

            <aside className="lg:sticky lg:top-28 h-fit space-y-3">
              <div className="rounded-2xl border bg-card p-4">
                <div className="text-sm font-semibold">Keyword coverage</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  Green = covered in doc text. Amber = missing.
                </div>
                <div className="mt-3">
                  <KeywordChips keywords={keywords} isCovered={isCovered} />
                </div>
              </div>

              <div className="rounded-2xl border bg-card p-4">
                <div className="text-sm font-semibold">Suggestions</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  Confirmed vs recommended — keep it honest.
                </div>

                <Separator className="my-3" />

                <div>
                  <div className="text-xs font-semibold">Recommended fixes</div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {missingKeywords.slice(0, 10).map((k) => (
                      <Badge
                        key={k}
                        variant="secondary"
                        className="border bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800 text-[11px]"
                      >
                        {k}
                      </Badge>
                    ))}
                  </div>
                  <div className="mt-3 text-xs text-muted-foreground">
                    Click &quot;Use evidence&quot; to insert a proof bullet. Then
                    add missing keywords naturally.
                  </div>
                </div>
              </div>
            </aside>
          </div>
        )}
      </div>
    </div>
  );
});

/* ------------------------------------------------------------------ */
/*  ExportCard                                                         */
/* ------------------------------------------------------------------ */

export function ExportCard({
  title,
  description,
  hasContent,
  onDownloadPdf,
  onDownloadDocx,
  onDownloadImage,
  onCopyText,
}: {
  title: string;
  description: string;
  hasContent: boolean;
  onDownloadPdf: () => Promise<void>;
  onDownloadDocx: () => Promise<void>;
  onDownloadImage: () => Promise<void>;
  onCopyText: () => void;
}) {
  const [downloading, setDownloading] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    onCopyText();
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = async (format: string, fn: () => Promise<void>) => {
    setDownloading(format);
    try {
      await fn();
    } catch (err) {
      console.error(`${format} export failed:`, err);
    } finally {
      setDownloading(null);
    }
  };

  return (
    <div className="rounded-2xl border bg-card p-4 transition-all duration-300 hover:shadow-soft-sm">
      <div className="text-sm font-semibold">{title}</div>
      <div className="mt-1 text-xs text-muted-foreground">{description}</div>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          className="gap-1.5"
          disabled={!hasContent || !!downloading}
          onClick={() => handleDownload("pdf", onDownloadPdf)}
        >
          {downloading === "pdf" ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Download className="h-3.5 w-3.5" />
          )}
          PDF
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5"
          disabled={!hasContent || !!downloading}
          onClick={() => handleDownload("docx", onDownloadDocx)}
        >
          {downloading === "docx" ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <FileType className="h-3.5 w-3.5" />
          )}
          Word
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5"
          disabled={!hasContent || !!downloading}
          onClick={() => handleDownload("jpg", onDownloadImage)}
        >
          {downloading === "jpg" ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <FileImage className="h-3.5 w-3.5" />
          )}
          JPG
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5"
          disabled={!hasContent}
          onClick={handleCopy}
        >
          {copied ? (
            <Check className="h-3.5 w-3.5 text-emerald-600" />
          ) : (
            <ClipboardCopy className="h-3.5 w-3.5" />
          )}
          {copied ? "Copied!" : "Copy"}
        </Button>
      </div>
      {!hasContent && (
        <div className="mt-2 text-[10px] text-muted-foreground">
          Generate this document first to enable export.
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  EmptyState                                                         */
/* ------------------------------------------------------------------ */

export function EmptyState({
  title,
  body,
  action,
}: {
  title: string;
  body: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-dashed bg-card/50 p-6 text-center">
      <div className="text-sm font-semibold">{title}</div>
      <div className="mt-1 text-xs text-muted-foreground">{body}</div>
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}
