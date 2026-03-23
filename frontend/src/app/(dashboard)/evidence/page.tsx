"use client";

import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import {
  Plus,
  Upload,
  Link2,
  FileText,
  Trash2,
  ExternalLink,
  Loader2,
  Search,
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
import { toast } from "@/hooks/use-toast";

import { Button } from "@/components/ui/button";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
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
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

const EVIDENCE_TYPES = [
  { value: "cert", label: "Certification" },
  { value: "project", label: "Project" },
  { value: "course", label: "Course" },
  { value: "award", label: "Award" },
  { value: "publication", label: "Publication" },
  { value: "other", label: "Other" },
] as const;

export default function EvidenceVaultPage() {
  const router = useRouter();
  const { user } = useAuth();

  const { data: evidence = [], loading, addItem, removeItem } = useEvidence(user?.uid ?? null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

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

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!user) return;
    setUploading(true);

    try {
      let storageUrl: string | undefined;
      let fileName: string | undefined;

      if (kind === "file" && fileRef.current?.files?.[0]) {
        const file = fileRef.current.files[0];
        // M10-F3: Validate file type and size
        const MAX_FILE_SIZE = 25 * 1024 * 1024; // 25 MB
        const ALLOWED_TYPES = /\.(pdf|doc|docx|txt|rtf|odt|png|jpg|jpeg|gif|webp|csv|xlsx|xls|pptx|ppt|md|json)$/i;
        if (!ALLOWED_TYPES.test(file.name)) {
          toast.error("Invalid file type", "Allowed: PDF, DOC, DOCX, images, spreadsheets, text files.");
          setUploading(false);
          return;
        }
        if (file.size > MAX_FILE_SIZE) {
          toast.error("File too large", "Maximum file size is 25 MB.");
          setUploading(false);
          return;
        }
        fileName = file.name;
        storageUrl = await uploadEvidenceFile(user.uid, file);
      }

      const parsedSkills = skills
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const parsedTools = tools
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const parsedTags = tags
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);

      const id = await createEvidence(user.uid, {
        userId: user.uid,
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
        userId: user.uid,
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
      toast({ title: "Evidence added", description: `"${title}" has been saved to your vault.`, variant: "success" });
    } catch (err) {
      console.error("Failed to create evidence:", err);
    } finally {
      setUploading(false);
    }
  }

  function handleDelete(id: string) {
    setDeleteTarget(id);
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeletingId(deleteTarget);
    setDeleteTarget(null);
    try {
      await deleteEvidence(deleteTarget);
      removeItem(deleteTarget);
      toast({ title: "Evidence deleted", description: "The evidence item has been removed.", variant: "success" });
    } catch (err) {
      console.error("Failed to delete evidence:", err);
    } finally {
      setDeletingId(null);
    }
  }

  if (loading) {
    return (
      <div className="space-y-4">
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
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Evidence Vault</h1>
          <p className="text-muted-foreground text-sm">
            Collect and organize proof of your skills — certifications, projects, links, and more.
          </p>
        </div>

        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button className="rounded-xl">
              <Plus className="mr-2 h-4 w-4" />
              Add Evidence
            </Button>
          </DialogTrigger>

          <DialogContent className="max-w-lg rounded-2xl p-0 overflow-hidden">
            <div className="flex max-h-[85vh] flex-col">
              <DialogHeader className="px-6 pt-6">
                <DialogTitle>Add Evidence</DialogTitle>
                <DialogDescription>
                  Add a link or file that proves a skill. Keep it specific so you can reuse it across applications.
                </DialogDescription>
              </DialogHeader>

              <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col gap-4 px-6 pb-6 pt-4">
                <div className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-2">
                  {/* Kind toggle */}
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      variant={kind === "link" ? "default" : "outline"}
                      size="sm"
                      className="rounded-xl"
                      onClick={() => setKind("link")}
                    >
                      <Link2 className="mr-1.5 h-4 w-4" />
                      Link
                    </Button>
                    <Button
                      type="button"
                      variant={kind === "file" ? "default" : "outline"}
                      size="sm"
                      className="rounded-xl"
                      onClick={() => setKind("file")}
                    >
                      <Upload className="mr-1.5 h-4 w-4" />
                      File
                    </Button>
                  </div>

                  <div className="space-y-1.5">
                    <Label htmlFor="evidence-title">Title</Label>
                    <Input
                      id="evidence-title"
                      required
                      className="rounded-xl h-11"
                      placeholder="e.g. AWS Solutions Architect cert"
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                    />
                  </div>

                  <div className="space-y-1.5">
                    <Label htmlFor="evidence-type">Type</Label>
                    <Select value={type} onValueChange={setType}>
                      <SelectTrigger id="evidence-type">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {EVIDENCE_TYPES.map((t) => (
                          <SelectItem key={t.value} value={t.value}>
                            {t.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-1.5">
                    <Label htmlFor="evidence-desc">Description</Label>
                    <Textarea
                      id="evidence-desc"
                      rows={2}
                      placeholder="What does this prove?"
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      maxLength={5000}
                    />
                  </div>

                  {kind === "link" ? (
                    <div key="evidence-url" className="space-y-1.5">
                      <Label htmlFor="evidence-url">URL</Label>
                      <Input
                        id="evidence-url"
                        type="url"
                        placeholder="https://..."
                        value={url}
                        onChange={(e) => setUrl(e.target.value)}
                      />
                    </div>
                  ) : (
                    <div key="evidence-file" className="space-y-1.5">
                      <Label htmlFor="evidence-file">File</Label>
                      <Input id="evidence-file" type="file" ref={fileRef} accept=".pdf,.doc,.docx,.txt,.rtf,.odt,.png,.jpg,.jpeg,.gif,.webp,.csv,.xlsx,.xls,.pptx,.ppt,.md,.json" />
                    </div>
                  )}

                  <div className="space-y-1.5">
                    <Label htmlFor="evidence-skills">Skills (comma-separated)</Label>
                    <Input
                      id="evidence-skills"
                      placeholder="React, TypeScript, Node.js"
                      value={skills}
                      onChange={(e) => setSkills(e.target.value)}
                    />
                  </div>

                  <div className="space-y-1.5">
                    <Label htmlFor="evidence-tools">Tools (comma-separated)</Label>
                    <Input
                      id="evidence-tools"
                      placeholder="Docker, AWS, Figma"
                      value={tools}
                      onChange={(e) => setTools(e.target.value)}
                    />
                  </div>

                  <div className="space-y-1.5">
                    <Label htmlFor="evidence-tags">Tags (comma-separated)</Label>
                    <Input
                      id="evidence-tags"
                      placeholder="frontend, performance, leadership"
                      value={tags}
                      onChange={(e) => setTags(e.target.value)}
                    />
                  </div>
                </div>

                <Button type="submit" className="w-full rounded-xl" disabled={uploading}>
                  {uploading ? "Uploading…" : "Add Evidence"}
                </Button>
              </form>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {/* Search & Filter */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search by title or skill…"
            className="pl-9 rounded-xl h-10"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Select value={typeFilter} onValueChange={setTypeFilter}>
          <SelectTrigger className="w-full sm:w-[180px] rounded-xl h-10">
            <SelectValue placeholder="All types" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All types</SelectItem>
            {EVIDENCE_TYPES.map((t) => (
              <SelectItem key={t.value} value={t.value}>
                {t.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {(() => {
        const filtered = evidence.filter((ev: EvidenceDoc) => {
          const q = search.toLowerCase();
          const matchesSearch =
            !q ||
            ev.title.toLowerCase().includes(q) ||
            (Array.isArray(ev.skills) && ev.skills.some((s: string) => s.toLowerCase().includes(q)));
          const matchesType = typeFilter === "all" || ev.type === typeFilter;
          return matchesSearch && matchesType;
        });

        return filtered.length === 0 ? (
          <div className="rounded-2xl border border-dashed bg-card/50">
            <div className="flex flex-col items-center justify-center py-12">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10">
                <Search className="h-6 w-6 text-primary" />
              </div>
              <p className="mt-4 text-sm text-muted-foreground">
                {evidence.length === 0
                  ? 'No evidence yet. Click "Add Evidence" to get started.'
                  : "No evidence matches your search."}
              </p>
            </div>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.map((ev: EvidenceDoc) => {
              const link = ev.kind === "link" ? ev.url : ev.storageUrl ?? ev.fileUrl;
              return (
                <div key={ev.id} className="relative group rounded-2xl border bg-card shadow-soft-sm hover:shadow-soft-md transition-all duration-300 overflow-hidden">
                  <div className="p-4 pb-2">
                    <div className="flex items-start justify-between gap-2">
                      <div className="text-sm font-semibold truncate">{ev.title}</div>
                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-all duration-200">
                        {link && (
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7"
                            aria-label={ev.kind === "link" ? "Open link" : "Open file"}
                            onClick={async () => {
                              try {
                                const resolved =
                                  ev.kind === "link"
                                    ? link
                                    : await resolveFileUrl(link);
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
                          aria-label="Delete evidence"
                          onClick={() => handleDelete(ev.id)}
                        >
                          {deletingId === ev.id ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Trash2 className="h-3.5 w-3.5" />
                          )}
                        </Button>
                      </div>
                    </div>
                  </div>
                  <div className="px-4 pb-4 space-y-2">
                    {ev.description && (
                      <p className="text-xs text-muted-foreground line-clamp-2">
                        {ev.description}
                      </p>
                    )}
                    <div className="flex flex-wrap gap-1">
                      <Badge variant="outline" className="text-[10px]">
                        {ev.type}
                      </Badge>
                      {(Array.isArray(ev.skills) ? ev.skills : []).slice(0, 3).map((s: string) => (
                        <Badge key={s} variant="secondary" className="text-[10px]">
                          {s}
                        </Badge>
                      ))}
                      {(Array.isArray(ev.tools) ? ev.tools : []).slice(0, 3).map((t: string) => (
                        <Badge key={t} variant="secondary" className="text-[10px]">
                          {t}
                        </Badge>
                      ))}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        );
      })()}

      {/* Delete Confirmation AlertDialog (P1-10) */}
      <AlertDialog open={!!deleteTarget} onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this evidence?</AlertDialogTitle>
            <AlertDialogDescription>
              This action cannot be undone. The evidence item will be permanently removed from your vault.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
