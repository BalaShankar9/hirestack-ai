"use client";

import { useMemo, useState, useRef } from "react";
import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  Plus,
  Upload,
  Link2,
  FileText,
  Trash2,
  ExternalLink,
  Loader2,
  Search,
  Award,
  BookOpen,
  Code2,
  Trophy,
  Newspaper,
  CheckSquare,
  Square,
  Package,
  ShieldCheck,
  Presentation,
  GitBranch,
  Globe,
  UserCheck,
  BarChart3,
  ArrowRight,
} from "lucide-react";

import { useAuth } from "@/components/providers";
import { useEvidence } from "@/lib/firestore";
import {
  createEvidence,
  deleteEvidence,
  uploadEvidenceFile,
} from "@/lib/firestore/ops";
import type { EvidenceDoc } from "@/lib/firestore/models";
import { resolveFileUrl } from "@/lib/storage";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState } from "@/components/ui/empty-state";
import { AITrace } from "@/components/ui/ai-trace";
import { toast } from "@/hooks/use-toast";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

/**
 * Extended evidence types per brief requirements.
 * Each evidence item supports: title, summary, tags, relevance,
 * proof strength, source link/file, suggested use.
 */
const EVIDENCE_TYPES = [
  { value: "cert", label: "Certification", icon: Award, color: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-800" },
  { value: "project", label: "Project", icon: Code2, color: "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-800" },
  { value: "achievement", label: "Quantified Achievement", icon: BarChart3, color: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800" },
  { value: "course", label: "Course", icon: BookOpen, color: "bg-violet-500/10 text-violet-600 dark:text-violet-400 border-violet-200 dark:border-violet-800" },
  { value: "award", label: "Award", icon: Trophy, color: "bg-teal-500/10 text-teal-600 dark:text-teal-400 border-teal-200 dark:border-teal-800" },
  { value: "writing", label: "Writing Sample", icon: FileText, color: "bg-cyan-500/10 text-cyan-600 dark:text-cyan-400 border-cyan-200 dark:border-cyan-800" },
  { value: "presentation", label: "Presentation", icon: Presentation, color: "bg-pink-500/10 text-pink-600 dark:text-pink-400 border-pink-200 dark:border-pink-800" },
  { value: "repo", label: "Repository", icon: GitBranch, color: "bg-gray-500/10 text-gray-600 dark:text-gray-400 border-gray-200 dark:border-gray-800" },
  { value: "portfolio", label: "Portfolio Item", icon: Globe, color: "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border-indigo-200 dark:border-indigo-800" },
  { value: "recommendation", label: "Recommendation", icon: UserCheck, color: "bg-orange-500/10 text-orange-600 dark:text-orange-400 border-orange-200 dark:border-orange-800" },
  { value: "publication", label: "Publication", icon: Newspaper, color: "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-200 dark:border-rose-800" },
  { value: "other", label: "Other", icon: Package, color: "bg-muted text-muted-foreground border-border" },
] as const;

function getTypeConfig(type: string) {
  return EVIDENCE_TYPES.find((t) => t.value === type) ?? EVIDENCE_TYPES[EVIDENCE_TYPES.length - 1];
}

export default function EvidenceVaultPage() {
  const router = useRouter();
  const { user } = useAuth();
  const userId = user?.uid || user?.id || null;

  const { data: evidence = [], loading, addItem, removeItem } = useEvidence(userId);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [filterType, setFilterType] = useState<string>("all");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);

  // Form state
  const [kind, setKind] = useState<"link" | "file">("link");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [type, setType] = useState("other");
  const [url, setUrl] = useState("");
  const [skills, setSkills] = useState("");
  const [tools, setTools] = useState("");
  const [tags, setTags] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  function resetForm() {
    setKind("link");
    setTitle("");
    setDescription("");
    setType("other");
    setUrl("");
    setSkills("");
    setTools("");
    setTags("");
  }

  const filtered = useMemo(() => {
    let items = evidence;
    if (filterType !== "all") {
      items = items.filter((e) => e.type === filterType);
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      items = items.filter(
        (e) =>
          e.title?.toLowerCase().includes(q) ||
          e.description?.toLowerCase().includes(q) ||
          (e.skills ?? []).some((s: string) => s.toLowerCase().includes(q)) ||
          (e.tools ?? []).some((t: string) => t.toLowerCase().includes(q))
      );
    }
    return items;
  }, [evidence, search, filterType]);

  const typeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const ev of evidence) {
      counts[ev.type] = (counts[ev.type] || 0) + 1;
    }
    return counts;
  }, [evidence]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!userId) return;
    setUploading(true);

    try {
      let storageUrl: string | undefined;
      let fileName: string | undefined;

      if (kind === "file" && fileRef.current?.files?.[0]) {
        const file = fileRef.current.files[0];
        const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50 MB
        const ALLOWED_TYPES = ["application/pdf", "image/png", "image/jpeg", "image/webp", "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "text/plain"];
        if (file.size > MAX_FILE_SIZE) {
          toast({ title: "File too large", description: "Maximum file size is 50 MB.", variant: "error" });
          setUploading(false);
          return;
        }
        if (!ALLOWED_TYPES.includes(file.type)) {
          toast({ title: "Unsupported file type", description: "Upload a PDF, Word doc, image, or text file.", variant: "error" });
          setUploading(false);
          return;
        }
        fileName = file.name;
        storageUrl = await uploadEvidenceFile(userId, file);
      }

      const parsedSkills = skills.split(",").map((s) => s.trim()).filter(Boolean);
      const parsedTools = tools.split(",").map((s) => s.trim()).filter(Boolean);
      const parsedTags = tags.split(",").map((s) => s.trim()).filter(Boolean);

      const id = await createEvidence(userId, {
        userId,
        applicationId: null,
        kind,
        type: type as EvidenceDoc["type"],
        title,
        description: description || undefined,
        url: kind === "link" ? url : undefined,
        storageUrl,
        fileUrl: undefined,
        fileName,
        skills: parsedSkills,
        tools: parsedTools,
        tags: parsedTags,
      });

      addItem({
        id,
        userId,
        applicationId: null,
        kind,
        type: type as EvidenceDoc["type"],
        title,
        description: description || undefined,
        url: kind === "link" ? url : undefined,
        storageUrl,
        fileUrl: undefined,
        fileName,
        skills: parsedSkills,
        tools: parsedTools,
        tags: parsedTags,
        createdAt: Date.now(),
        updatedAt: Date.now(),
      });

      resetForm();
      setDialogOpen(false);
    } catch (err) {
      toast({ title: "Failed to save evidence", description: "Please try again.", variant: "error" });
    } finally {
      setUploading(false);
    }
  }

  async function confirmDelete() {
    if (!deleteTargetId) return;
    setDeletingId(deleteTargetId);
    try {
      await deleteEvidence(deleteTargetId);
      removeItem(deleteTargetId);
      setSelectedIds((prev) => { const n = new Set(prev); n.delete(deleteTargetId); return n; });
      toast({ title: "Evidence deleted" });
    } catch (err) {
      toast({ title: "Delete failed", description: "Please try again.", variant: "error" });
    } finally {
      setDeletingId(null);
      setDeleteTargetId(null);
    }
  }

  async function confirmBulkDelete() {
    if (selectedIds.size === 0) return;
    setBulkDeleting(true);
    const ids = Array.from(selectedIds);
    let failed = 0;
    for (const id of ids) {
      try {
        await deleteEvidence(id);
        removeItem(id);
      } catch {
        failed++;
      }
    }
    setSelectedIds(new Set());
    setBulkDeleting(false);
    if (failed === 0) {
      toast({ title: `${ids.length} item${ids.length !== 1 ? "s" : ""} deleted` });
    } else {
      toast({ title: `Deleted ${ids.length - failed} of ${ids.length}`, variant: "error", description: `${failed} item${failed !== 1 ? "s" : ""} could not be deleted.` });
    }
  }

  function toggleSelect(id: string) {
    setSelectedIds((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  }

  function toggleSelectAll() {
    if (selectedIds.size === filtered.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filtered.map((e) => e.id)));
    }
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-48" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-40 rounded-2xl" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <>
    <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }} className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-violet-500/10">
            <ShieldCheck className="h-5 w-5 text-violet-600 dark:text-violet-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold">Evidence</h1>
            <p className="text-xs text-muted-foreground">
              {evidence.length} proof item{evidence.length !== 1 ? "s" : ""} — certifications, projects, achievements, and more
            </p>
          </div>
        </div>

        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button className="rounded-xl gap-2">
              <Plus className="h-4 w-4" />
              Add Evidence
            </Button>
          </DialogTrigger>

          <DialogContent className="max-w-lg rounded-2xl p-0 overflow-hidden">
            <div className="flex max-h-[85vh] flex-col">
              <DialogHeader className="px-6 pt-6">
                <DialogTitle>Add Evidence</DialogTitle>
                <DialogDescription>
                  Add a link or file that proves a skill. Specific is better — reuse it across applications.
                </DialogDescription>
              </DialogHeader>

              <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col gap-4 px-6 pb-6 pt-4">
                <div className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-2">
                  <div className="flex gap-2">
                    <Button type="button" variant={kind === "link" ? "default" : "outline"} size="sm" className="rounded-xl" onClick={() => setKind("link")}>
                      <Link2 className="mr-1.5 h-4 w-4" />Link
                    </Button>
                    <Button type="button" variant={kind === "file" ? "default" : "outline"} size="sm" className="rounded-xl" onClick={() => setKind("file")}>
                      <Upload className="mr-1.5 h-4 w-4" />File
                    </Button>
                  </div>

                  <div className="space-y-1.5">
                    <Label>Title</Label>
                    <Input required className="rounded-xl h-11" placeholder="e.g. AWS Solutions Architect cert" value={title} onChange={(e) => setTitle(e.target.value)} />
                  </div>

                  <div className="space-y-1.5">
                    <Label>Type</Label>
                    <Select value={type} onValueChange={setType}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {EVIDENCE_TYPES.map((t) => (
                          <SelectItem key={t.value} value={t.value}>
                            <span className="flex items-center gap-2"><t.icon className="h-3.5 w-3.5" />{t.label}</span>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-1.5">
                    <Label>Description</Label>
                    <Textarea rows={2} placeholder="What does this prove?" value={description} onChange={(e) => setDescription(e.target.value)} />
                  </div>

                  {kind === "link" ? (
                    <div className="space-y-1.5">
                      <Label>URL</Label>
                      <Input type="url" placeholder="https://..." value={url} onChange={(e) => setUrl(e.target.value)} />
                    </div>
                  ) : (
                    <div className="space-y-1.5">
                      <Label>File</Label>
                      <Input type="file" ref={fileRef} />
                    </div>
                  )}

                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="space-y-1.5">
                      <Label>Skills (comma-separated)</Label>
                      <Input placeholder="React, TypeScript" value={skills} onChange={(e) => setSkills(e.target.value)} />
                    </div>
                    <div className="space-y-1.5">
                      <Label>Tools (comma-separated)</Label>
                      <Input placeholder="Docker, AWS" value={tools} onChange={(e) => setTools(e.target.value)} />
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <Label>Tags (comma-separated)</Label>
                    <Input placeholder="frontend, performance, leadership" value={tags} onChange={(e) => setTags(e.target.value)} />
                  </div>
                </div>

                <Button type="submit" className="w-full rounded-xl" disabled={uploading}>
                  {uploading ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Uploading…</> : "Add Evidence"}
                </Button>
              </form>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {/* Search + Filter */}
      {evidence.length > 0 && (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              className="pl-9 rounded-xl h-10"
              placeholder="Search evidence..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className="flex flex-wrap gap-1.5">
            <Badge
              variant={filterType === "all" ? "default" : "secondary"}
              className="cursor-pointer text-xs rounded-lg"
              onClick={() => setFilterType("all")}
            >
              All ({evidence.length})
            </Badge>
            {EVIDENCE_TYPES.map((t) => {
              const count = typeCounts[t.value] || 0;
              if (count === 0) return null;
              return (
                <Badge
                  key={t.value}
                  variant={filterType === t.value ? "default" : "secondary"}
                  className={cn("cursor-pointer text-xs rounded-lg border", filterType === t.value ? "" : t.color)}
                  onClick={() => setFilterType(filterType === t.value ? "all" : t.value)}
                >
                  <t.icon className="h-3 w-3 mr-1" />
                  {t.label} ({count})
                </Badge>
              );
            })}
          </div>
        </div>
      )}

      {/* Bulk-select toolbar */}
      {filtered.length > 0 && (
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            className="gap-1.5 text-xs rounded-xl h-8"
            onClick={toggleSelectAll}
          >
            {selectedIds.size === filtered.length && filtered.length > 0 ? (
              <CheckSquare className="h-3.5 w-3.5" />
            ) : (
              <Square className="h-3.5 w-3.5" />
            )}
            {selectedIds.size === filtered.length && filtered.length > 0 ? "Deselect all" : "Select all"}
          </Button>
          {selectedIds.size > 0 && (
            <Button
              variant="destructive"
              size="sm"
              className="gap-1.5 text-xs rounded-xl h-8"
              onClick={confirmBulkDelete}
              disabled={bulkDeleting}
            >
              {bulkDeleting ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Trash2 className="h-3.5 w-3.5" />
              )}
              Delete {selectedIds.size} selected
            </Button>
          )}
        </div>
      )}

      {/* AI Intelligence Trace */}
      {evidence.length > 0 && (
        <AITrace
          variant="banner"
          items={[
            { label: "proof items collected", value: evidence.length, done: true },
            { label: "evidence types used", value: Object.keys(typeCounts).length, done: true },
            ...(Object.keys(typeCounts).length < 3
              ? [{ label: "Add more types to strengthen your applications" }]
              : []),
          ]}
        />
      )}

      {/* Grid */}
      {evidence.length === 0 ? (
        <div className="rounded-2xl border border-dashed bg-card/50">
          <div className="flex flex-col items-center justify-center py-16">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10">
              <ShieldCheck className="h-7 w-7 text-primary" />
            </div>
            <h3 className="mt-4 text-sm font-semibold">Build your proof library</h3>
            <p className="mt-1 text-xs text-muted-foreground max-w-sm text-center">
              Most candidates submit claims. You submit proof. Add certifications, projects,
              quantified achievements, and more — the AI matches them to every application.
            </p>
            <Button className="mt-5 gap-2 rounded-xl" onClick={() => setDialogOpen(true)}>
              <Plus className="h-4 w-4" /> Add your first proof item
            </Button>
          </div>
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-2xl border border-dashed bg-card/50 p-8 text-center">
          <p className="text-sm text-muted-foreground">No evidence matches your search.</p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((ev: EvidenceDoc) => {
            const link = ev.kind === "link" ? ev.url : ev.storageUrl ?? ev.fileUrl;
            const typeConfig = getTypeConfig(ev.type);
            const TypeIcon = typeConfig.icon;

            return (
              <div key={ev.id} className={cn("relative group rounded-2xl border bg-card shadow-soft-sm hover:shadow-soft-md hover:-translate-y-0.5 transition-all duration-300 overflow-hidden card-spotlight", selectedIds.has(ev.id) && "ring-2 ring-primary/50 border-primary/30")}>
                {/* Type indicator strip */}
                <div className={cn("h-1 w-full", typeConfig.color.split(" ")[0])} />

                {/* Checkbox (top-left corner) */}
                <button
                  type="button"
                  aria-label={selectedIds.has(ev.id) ? "Deselect" : "Select"}
                  onClick={() => toggleSelect(ev.id)}
                  className="absolute left-2 top-3 z-10 text-muted-foreground hover:text-primary transition-colors"
                >
                  {selectedIds.has(ev.id) ? (
                    <CheckSquare className="h-4 w-4 text-primary" />
                  ) : (
                    <Square className="h-4 w-4 opacity-0 group-hover:opacity-100" />
                  )}
                </button>

                <div className="p-4 pl-8 space-y-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-start gap-2.5 min-w-0">
                      <div className={cn("flex h-8 w-8 items-center justify-center rounded-lg shrink-0", typeConfig.color)}>
                        <TypeIcon className="h-4 w-4" />
                      </div>
                      <div className="min-w-0">
                        <div className="text-sm font-semibold truncate">{ev.title}</div>
                        <div className="text-[11px] text-muted-foreground capitalize">{typeConfig.label}</div>
                      </div>
                    </div>
                    <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-all duration-200">
                      {link && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7"
                          onClick={async () => {
                            try {
                              const resolved = ev.kind === "link" ? link : await resolveFileUrl(link);
                              if (resolved) window.open(resolved, "_blank", "noopener");
                            } catch (err) {
                              console.error("Failed to open evidence:", err);
                            }
                          }}
                        >
                          <ExternalLink className="h-3.5 w-3.5" />
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-destructive"
                        disabled={deletingId === ev.id}
                        onClick={() => setDeleteTargetId(ev.id)}
                      >
                        {deletingId === ev.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                      </Button>
                    </div>
                  </div>

                  {ev.description && (
                    <p className="text-xs text-muted-foreground line-clamp-2">{ev.description}</p>
                  )}

                  {((ev.skills?.length ?? 0) > 0 || (ev.tools?.length ?? 0) > 0) && (
                    <div className="flex flex-wrap gap-1">
                      {(ev.skills ?? []).slice(0, 3).map((s: string) => (
                        <Badge key={s} variant="secondary" className="text-[10px]">{s}</Badge>
                      ))}
                      {(ev.tools ?? []).slice(0, 2).map((t: string) => (
                        <Badge key={t} variant="outline" className="text-[10px]">{t}</Badge>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </motion.div>

    <ConfirmDialog
      open={!!deleteTargetId}
      onOpenChange={(open) => { if (!open) setDeleteTargetId(null); }}
      title="Delete evidence item?"
      description="This item will be permanently removed. This cannot be undone."
      confirmLabel="Delete"
      variant="destructive"
      onConfirm={confirmDelete}
    />
    </>
  );
}
