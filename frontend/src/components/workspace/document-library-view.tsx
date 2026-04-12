"use client";

import { memo, useCallback, useState } from "react";
import {
  FileText,
  Download,
  Eye,
  Sparkles,
  ChevronRight,
  CheckCircle2,
  Clock,
  AlertCircle,
  Loader2,
  Library,
  Target,
  Bookmark,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { DocumentLibraryItem, DocumentCategory } from "@/lib/firestore/models";

/* ── Category config ────────────────────────────────────────────── */

const CATEGORY_CONFIG: Record<DocumentCategory, {
  label: string;
  description: string;
  icon: typeof Library;
  color: string;
  bgColor: string;
}> = {
  benchmark: {
    label: "Benchmark Library",
    description: "Ideal candidate standard documents for this role",
    icon: Target,
    color: "text-amber-600",
    bgColor: "bg-amber-500/10",
  },
  fixed: {
    label: "Fixed Library",
    description: "Your persistent and evolving base document library",
    icon: Library,
    color: "text-blue-600",
    bgColor: "bg-blue-500/10",
  },
  tailored: {
    label: "Tailored Documents",
    description: "Job-specific documents crafted for this application",
    icon: Bookmark,
    color: "text-violet-600",
    bgColor: "bg-violet-500/10",
  },
};

/* ── Status badge ────────────────────────────────────────────────── */

function StatusBadge({ status }: { status: string }) {
  switch (status) {
    case "ready":
      return (
        <Badge variant="secondary" className="text-emerald-600 bg-emerald-500/10 border-0 text-[10px]">
          <CheckCircle2 className="h-3 w-3 mr-1" />
          Ready
        </Badge>
      );
    case "generating":
      return (
        <Badge variant="secondary" className="text-primary bg-primary/10 border-0 text-[10px]">
          <Loader2 className="h-3 w-3 mr-1 animate-spin" />
          Generating
        </Badge>
      );
    case "planned":
      return (
        <Badge variant="secondary" className="text-muted-foreground bg-muted text-[10px]">
          <Clock className="h-3 w-3 mr-1" />
          Planned
        </Badge>
      );
    case "error":
      return (
        <Badge variant="secondary" className="text-destructive bg-destructive/10 border-0 text-[10px]">
          <AlertCircle className="h-3 w-3 mr-1" />
          Error
        </Badge>
      );
    default:
      return null;
  }
}

/* ── Document Card ───────────────────────────────────────────────── */

interface DocumentCardProps {
  doc: DocumentLibraryItem;
  onView?: (doc: DocumentLibraryItem) => void;
  onGenerate?: (doc: DocumentLibraryItem) => void;
  onDownload?: (doc: DocumentLibraryItem) => void;
}

const DocumentCard = memo(function DocumentCard({
  doc,
  onView,
  onGenerate,
  onDownload,
}: DocumentCardProps) {
  return (
    <div className="group flex items-center gap-3 rounded-xl border border-border/50 p-3 hover:border-border transition-colors">
      <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${
        doc.status === "ready"
          ? "bg-emerald-500/10"
          : doc.status === "generating"
            ? "bg-primary/10"
            : "bg-muted/50"
      }`}>
        <FileText className={`h-4 w-4 ${
          doc.status === "ready"
            ? "text-emerald-500"
            : doc.status === "generating"
              ? "text-primary"
              : "text-muted-foreground/50"
        }`} />
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium truncate">{doc.label}</span>
          <StatusBadge status={doc.status} />
        </div>
        <p className="text-[11px] text-muted-foreground truncate">
          {doc.docType.replace(/_/g, " ")} · v{doc.version}
        </p>
      </div>

      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        {doc.status === "ready" && onView && (
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => onView(doc)}>
            <Eye className="h-3.5 w-3.5" />
          </Button>
        )}
        {doc.status === "ready" && onDownload && (
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => onDownload(doc)}>
            <Download className="h-3.5 w-3.5" />
          </Button>
        )}
        {(doc.status === "planned" || doc.status === "error") && onGenerate && (
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => onGenerate(doc)}>
            <Sparkles className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
    </div>
  );
});

/* ── Category Section ────────────────────────────────────────────── */

interface CategorySectionProps {
  category: DocumentCategory;
  documents: DocumentLibraryItem[];
  onViewDocument?: (doc: DocumentLibraryItem) => void;
  onGenerateDocument?: (doc: DocumentLibraryItem) => void;
  onDownloadDocument?: (doc: DocumentLibraryItem) => void;
  defaultExpanded?: boolean;
}

const CategorySection = memo(function CategorySection({
  category,
  documents,
  onViewDocument,
  onGenerateDocument,
  onDownloadDocument,
  defaultExpanded = false,
}: CategorySectionProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const config = CATEGORY_CONFIG[category];
  const readyCount = documents.filter((d) => d.status === "ready").length;
  const totalCount = documents.length;

  if (totalCount === 0) return null;

  return (
    <div className="rounded-xl border border-border/50 overflow-hidden">
      <button
        type="button"
        className="w-full flex items-center gap-3 p-4 hover:bg-muted/30 transition-colors text-left"
        onClick={() => setExpanded(!expanded)}
      >
        <div className={`flex h-10 w-10 items-center justify-center rounded-xl ${config.bgColor}`}>
          <config.icon className={`h-5 w-5 ${config.color}`} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold">{config.label}</span>
            <Badge variant="secondary" className="text-[10px]">
              {readyCount}/{totalCount}
            </Badge>
          </div>
          <p className="text-[11px] text-muted-foreground">{config.description}</p>
        </div>
        <ChevronRight
          className={`h-4 w-4 text-muted-foreground transition-transform duration-200 ${
            expanded ? "rotate-90" : ""
          }`}
        />
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-2">
          {documents.map((doc) => (
            <DocumentCard
              key={doc.id}
              doc={doc}
              onView={onViewDocument}
              onGenerate={onGenerateDocument}
              onDownload={onDownloadDocument}
            />
          ))}
        </div>
      )}
    </div>
  );
});

/* ── Main Document Library View ──────────────────────────────────── */

interface DocumentLibraryViewProps {
  documents: Record<string, DocumentLibraryItem[]>;
  onViewDocument?: (doc: DocumentLibraryItem) => void;
  onGenerateDocument?: (doc: DocumentLibraryItem) => void;
  onDownloadDocument?: (doc: DocumentLibraryItem) => void;
}

export function DocumentLibraryView({
  documents,
  onViewDocument,
  onGenerateDocument,
  onDownloadDocument,
}: DocumentLibraryViewProps) {
  const categories: DocumentCategory[] = ["tailored", "benchmark", "fixed"];

  const totalReady = Object.values(documents).flat().filter((d) => d.status === "ready").length;
  const totalDocs = Object.values(documents).flat().length;

  return (
    <div className="space-y-4">
      {/* Summary header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold">Document Library</h3>
          <p className="text-xs text-muted-foreground">
            {totalReady} of {totalDocs} documents ready
          </p>
        </div>
      </div>

      {/* Category sections */}
      <div className="space-y-3">
        {categories.map((cat) => (
          <CategorySection
            key={cat}
            category={cat}
            documents={documents[cat] || []}
            onViewDocument={onViewDocument}
            onGenerateDocument={onGenerateDocument}
            onDownloadDocument={onDownloadDocument}
            defaultExpanded={cat === "tailored"}
          />
        ))}
      </div>
    </div>
  );
}
