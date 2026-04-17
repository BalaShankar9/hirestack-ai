"use client";

import { memo, useMemo, useState } from "react";
import {
  FileText,
  Download,
  Eye,
  Sparkles,
  CheckCircle2,
  Clock,
  AlertCircle,
  Loader2,
  Crown,
  ChevronRight,
  Search,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { UniverseDocType } from "@/lib/document-universe";
import { GROUP_META } from "@/lib/document-universe";

/* ── Types ───────────────────────────────────────────────────────── */

export interface DocStatus {
  status: "ready" | "generating" | "planned" | "error";
  version?: number;
  htmlContent?: string;
  updatedAt?: number;
  label?: string;
}

interface DocumentUniverseGridProps {
  /** The full document universe for this tier */
  universe: UniverseDocType[];
  /** Actual status map: key → latest doc status. Missing = not generated */
  statusMap: Map<string, DocStatus>;
  /** Called when user clicks View on a ready doc */
  onView?: (key: string) => void;
  /** Called when user clicks Generate on an ungenerated doc */
  onGenerate?: (key: string, label: string) => void;
  /** Called when user clicks Download on a ready doc */
  onDownload?: (key: string) => void;
  /** Title override */
  title?: string;
  /** Whether to show the core package section */
  showCoreSection?: boolean;
  /** Whether to show search */
  showSearch?: boolean;
}

/* ── Status indicator ────────────────────────────────────────────── */

function StatusIndicator({ status }: { status?: DocStatus }) {
  if (!status) {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] text-muted-foreground/50">
        <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/20" />
        Not generated
      </span>
    );
  }
  switch (status.status) {
    case "ready":
      return (
        <span className="inline-flex items-center gap-1 text-[10px] text-emerald-600">
          <CheckCircle2 className="h-3 w-3" /> Ready{status.version && status.version > 1 ? ` · v${status.version}` : ""}
        </span>
      );
    case "generating":
      return (
        <span className="inline-flex items-center gap-1 text-[10px] text-primary">
          <Loader2 className="h-3 w-3 animate-spin" /> Generating
        </span>
      );
    case "planned":
      return (
        <span className="inline-flex items-center gap-1 text-[10px] text-muted-foreground">
          <Clock className="h-3 w-3" /> Planned
        </span>
      );
    case "error":
      return (
        <span className="inline-flex items-center gap-1 text-[10px] text-destructive">
          <AlertCircle className="h-3 w-3" /> Error
        </span>
      );
  }
}

/* ── Single document card ────────────────────────────────────────── */

interface DocCardProps {
  def: UniverseDocType;
  status?: DocStatus;
  onView?: () => void;
  onGenerate?: () => void;
  onDownload?: () => void;
  compact?: boolean;
}

const DocCard = memo(function DocCard({ def, status, onView, onGenerate, onDownload, compact }: DocCardProps) {
  const isReady = status?.status === "ready";
  const isGenerating = status?.status === "generating";
  const canGenerate = !status || status.status === "planned" || status.status === "error";

  return (
    <div className={`group relative flex items-start gap-3 rounded-xl border transition-all ${
      isReady
        ? "border-emerald-500/20 bg-emerald-500/[0.02]"
        : isGenerating
          ? "border-primary/20 bg-primary/[0.02]"
          : "border-border/40 hover:border-border/70"
    } ${compact ? "p-2.5" : "p-3"}`}>
      {/* Icon */}
      <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${
        isReady ? "bg-emerald-500/10" : isGenerating ? "bg-primary/10" : "bg-muted/40"
      }`}>
        <FileText className={`h-4 w-4 ${
          isReady ? "text-emerald-500" : isGenerating ? "text-primary" : "text-muted-foreground/40"
        }`} />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className={`text-sm font-medium truncate ${!status ? "text-muted-foreground/70" : ""}`}>
            {def.label}
          </span>
          {def.core && (
            <Badge variant="secondary" className="text-[9px] gap-0.5 bg-amber-500/10 text-amber-600 border-0 px-1.5 py-0">
              <Crown className="h-2.5 w-2.5" /> Core
            </Badge>
          )}
        </div>
        {!compact && (
          <p className="text-[11px] text-muted-foreground/70 mt-0.5 line-clamp-1">{def.description}</p>
        )}
        <div className="mt-1">
          <StatusIndicator status={status} />
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
        {isReady && onView && (
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onView}>
            <Eye className="h-3.5 w-3.5" />
          </Button>
        )}
        {isReady && onDownload && (
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onDownload}>
            <Download className="h-3.5 w-3.5" />
          </Button>
        )}
        {canGenerate && onGenerate && (
          <Button variant="ghost" size="sm" className="h-7 gap-1 text-[11px]" onClick={onGenerate}>
            <Sparkles className="h-3 w-3" />
            Generate
          </Button>
        )}
      </div>
    </div>
  );
});

/* ── Group section ───────────────────────────────────────────────── */

interface GroupSectionProps {
  group: string;
  docs: UniverseDocType[];
  statusMap: Map<string, DocStatus>;
  onView?: (key: string) => void;
  onGenerate?: (key: string, label: string) => void;
  onDownload?: (key: string) => void;
  defaultExpanded?: boolean;
}

const GroupSection = memo(function GroupSection({
  group, docs, statusMap, onView, onGenerate, onDownload, defaultExpanded = false,
}: GroupSectionProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const meta = GROUP_META[group] || { label: group, order: 99 };
  const readyCount = docs.filter((d) => statusMap.get(d.key)?.status === "ready").length;

  return (
    <div>
      <button
        type="button"
        className="flex items-center gap-2 w-full py-2 text-left"
        onClick={() => setExpanded(!expanded)}
      >
        <ChevronRight className={`h-3.5 w-3.5 text-muted-foreground transition-transform ${expanded ? "rotate-90" : ""}`} />
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">{meta.label}</span>
        <span className="text-[10px] text-muted-foreground/60">
          {readyCount}/{docs.length}
        </span>
      </button>
      {expanded && (
        <div className="grid gap-2 sm:grid-cols-2 pl-5">
          {docs.map((def) => (
            <DocCard
              key={def.key}
              def={def}
              status={statusMap.get(def.key)}
              onView={onView ? () => onView(def.key) : undefined}
              onGenerate={onGenerate ? () => onGenerate(def.key, def.label) : undefined}
              onDownload={onDownload ? () => onDownload(def.key) : undefined}
              compact
            />
          ))}
        </div>
      )}
    </div>
  );
});

/* ── Main Grid ───────────────────────────────────────────────────── */

export function DocumentUniverseGrid({
  universe,
  statusMap,
  onView,
  onGenerate,
  onDownload,
  title,
  showCoreSection = true,
  showSearch = true,
}: DocumentUniverseGridProps) {
  const [search, setSearch] = useState("");

  const coreDocs = useMemo(() => universe.filter((d) => d.core), [universe]);
  const extendedDocs = useMemo(() => universe.filter((d) => !d.core), [universe]);

  // Group extended docs and filter by search
  const filteredExtended = useMemo(() => {
    let list = extendedDocs;
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(
        (d) => d.label.toLowerCase().includes(q) || d.description.toLowerCase().includes(q) || d.group.includes(q),
      );
    }
    return list;
  }, [extendedDocs, search]);

  const groupedExtended = useMemo(() => {
    const map = new Map<string, UniverseDocType[]>();
    for (const d of filteredExtended) {
      const arr = map.get(d.group) || [];
      arr.push(d);
      map.set(d.group, arr);
    }
    return [...map.entries()].sort(
      (a, b) => (GROUP_META[a[0]]?.order ?? 99) - (GROUP_META[b[0]]?.order ?? 99),
    );
  }, [filteredExtended]);

  // Stats
  const totalReady = universe.filter((d) => statusMap.get(d.key)?.status === "ready").length;
  const coreReady = coreDocs.filter((d) => statusMap.get(d.key)?.status === "ready").length;

  return (
    <div className="space-y-5">
      {/* ── Header ── */}
      {title && (
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold">{title}</h3>
            <p className="text-[11px] text-muted-foreground">
              {totalReady}/{universe.length} generated · {universe.length} document types available
            </p>
          </div>
          {showSearch && (
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <input
                type="text"
                placeholder="Search documents…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="h-8 w-44 rounded-lg border border-border/60 bg-background pl-8 pr-3 text-xs outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/20 transition-colors"
              />
            </div>
          )}
        </div>
      )}

      {/* ── Core Package ── */}
      {showCoreSection && coreDocs.length > 0 && (
        <div className="rounded-xl border border-amber-500/20 bg-amber-500/[0.02] p-4 space-y-3">
          <div className="flex items-center gap-2">
            <Crown className="h-4 w-4 text-amber-500" />
            <span className="text-sm font-semibold">Core Package</span>
            <Badge variant="secondary" className="text-[10px] bg-amber-500/10 text-amber-600 border-0">
              {coreReady}/{coreDocs.length} ready
            </Badge>
            <span className="text-[11px] text-muted-foreground ml-1">
              Highest-impact documents for every application
            </span>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            {coreDocs.map((def) => (
              <DocCard
                key={def.key}
                def={def}
                status={statusMap.get(def.key)}
                onView={onView ? () => onView(def.key) : undefined}
                onGenerate={onGenerate ? () => onGenerate(def.key, def.label) : undefined}
                onDownload={onDownload ? () => onDownload(def.key) : undefined}
              />
            ))}
          </div>
        </div>
      )}

      {/* ── Extended Catalogue ── */}
      {groupedExtended.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-semibold text-muted-foreground mb-2">
            Extended Catalogue · {filteredExtended.length} additional document types
          </p>
          {groupedExtended.map(([group, docs]) => (
            <GroupSection
              key={group}
              group={group}
              docs={docs}
              statusMap={statusMap}
              onView={onView}
              onGenerate={onGenerate}
              onDownload={onDownload}
            />
          ))}
        </div>
      )}

      {filteredExtended.length === 0 && search.trim() && (
        <p className="text-xs text-muted-foreground text-center py-4">
          No documents matching &ldquo;{search}&rdquo;
        </p>
      )}
    </div>
  );
}
