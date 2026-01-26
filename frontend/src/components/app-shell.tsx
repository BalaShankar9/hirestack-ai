"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutGrid,
  Sparkles,
  Briefcase,
  FolderKanban,
  LogOut,
  Command as CommandIcon,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import { signOut } from "firebase/auth";

import { cn } from "@/lib/utils";
import { auth } from "@/lib/firebase";
import { useAuth } from "@/components/providers";
import { useApplications } from "@/lib/firestore";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

type NavItem = {
  name: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  description: string;
};

const NAV: NavItem[] = [
  {
    name: "Dashboard",
    href: "/dashboard",
    icon: LayoutGrid,
    description: "Your application workspaces and queue",
  },
  {
    name: "New Application",
    href: "/new",
    icon: Sparkles,
    description: "Diagnose → plan → build → ship",
  },
  {
    name: "Evidence Vault",
    href: "/evidence",
    icon: FolderKanban,
    description: "Proof library you can reuse",
  },
  {
    name: "Career Lab",
    href: "/career",
    icon: Briefcase,
    description: "Skill sprints + learning plan",
  },
];

function initials(email?: string | null) {
  if (!email) return "U";
  return email.slice(0, 2).toUpperCase();
}

type CommandItem = {
  group: string;
  title: string;
  subtitle?: string;
  onSelect: () => void;
};

export function AppShell({
  children,
  pageTitle,
  pageHint,
  actions,
}: {
  children: React.ReactNode;
  pageTitle?: string;
  pageHint?: string;
  actions?: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const { user } = useAuth();
  const { data: apps } = useApplications(user?.uid || null, 6);

  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [cmdOpen, setCmdOpen] = useState(false);
  const [cmdQuery, setCmdQuery] = useState("");

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCmdOpen(true);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const commandItems: CommandItem[] = useMemo(() => {
    const navItems: CommandItem[] = NAV.map((n) => ({
      group: "Navigate",
      title: n.name,
      subtitle: n.description,
      onSelect: () => router.push(n.href),
    }));

    const recentApps: CommandItem[] = apps.slice(0, 5).map((a) => ({
      group: "Recent Workspaces",
      title: a.job.title || "Untitled application",
      subtitle: a.job.company ? `@ ${a.job.company}` : "Workspace",
      onSelect: () => router.push(`/applications/${a.id}`),
    }));

    return [...navItems, ...recentApps];
  }, [apps, router]);

  const filtered = useMemo(() => {
    const q = cmdQuery.trim().toLowerCase();
    if (!q) return commandItems;
    return commandItems.filter((i) => {
      const hay = `${i.title} ${i.subtitle || ""}`.toLowerCase();
      return hay.includes(q);
    });
  }, [cmdQuery, commandItems]);

  const grouped = useMemo(() => {
    const map = new Map<string, CommandItem[]>();
    for (const item of filtered) {
      map.set(item.group, [...(map.get(item.group) || []), item]);
    }
    return Array.from(map.entries());
  }, [filtered]);

  const handleSignOut = async () => {
    await signOut(auth);
    router.push("/login");
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Command palette */}
      <Dialog open={cmdOpen} onOpenChange={setCmdOpen}>
        <DialogContent className="max-w-xl p-0 overflow-hidden">
          <DialogHeader className="px-4 pt-4 pb-2">
            <DialogTitle className="text-sm font-semibold text-muted-foreground">
              Command palette
            </DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground">
              Jump to a workspace or page.
            </DialogDescription>
          </DialogHeader>
          <div className="px-4 pb-4">
            <Input
              autoFocus
              placeholder="Jump to… (Dashboard, New Application, Evidence, a workspace)"
              value={cmdQuery}
              onChange={(e) => setCmdQuery(e.target.value)}
            />
          </div>
          <Separator />
          <ScrollArea className="max-h-[340px]">
            <div className="p-2">
              {grouped.length === 0 ? (
                <div className="px-3 py-6 text-sm text-muted-foreground">
                  No matches. Try a different query.
                </div>
              ) : (
                grouped.map(([group, items]) => (
                  <div key={group} className="mb-2">
                    <div className="px-3 py-2 text-xs font-medium text-muted-foreground">
                      {group}
                    </div>
                    <div className="space-y-1">
                      {items.map((item) => (
                        <button
                          key={`${group}:${item.title}`}
                          className="w-full rounded-md px-3 py-2 text-left hover:bg-muted transition-colors"
                          onClick={() => {
                            setCmdOpen(false);
                            setCmdQuery("");
                            item.onSelect();
                          }}
                        >
                          <div className="text-sm font-medium">{item.title}</div>
                          {item.subtitle ? (
                            <div className="text-xs text-muted-foreground">
                              {item.subtitle}
                            </div>
                          ) : null}
                        </button>
                      ))}
                    </div>
                  </div>
                ))
              )}
            </div>
          </ScrollArea>
        </DialogContent>
      </Dialog>

      <div className="flex">
        {/* Sidebar */}
        <aside
          className={cn(
            "sticky top-0 h-screen border-r bg-white/60 backdrop-blur supports-[backdrop-filter]:bg-white/40",
            sidebarCollapsed ? "w-20" : "w-72"
          )}
        >
          <div className="flex items-center justify-between px-4 py-4">
            <Link href="/dashboard" className="flex items-center gap-2">
              <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-600 flex items-center justify-center text-white font-semibold">
                H
              </div>
              {!sidebarCollapsed && (
                <div className="leading-tight">
                  <div className="text-sm font-semibold">HireStack</div>
                  <div className="text-xs text-muted-foreground">
                    Application Intelligence
                  </div>
                </div>
              )}
            </Link>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setSidebarCollapsed((v) => !v)}
              className="text-muted-foreground"
              aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            >
              {sidebarCollapsed ? (
                <PanelLeftOpen className="h-4 w-4" />
              ) : (
                <PanelLeftClose className="h-4 w-4" />
              )}
            </Button>
          </div>

          <nav className="px-3 pb-4">
            <div className="space-y-1">
              {NAV.map((item) => {
                const active = pathname === item.href || pathname.startsWith(item.href + "/");
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                      active
                        ? "bg-blue-50 text-blue-700"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground"
                    )}
                    title={sidebarCollapsed ? item.name : undefined}
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    {!sidebarCollapsed && (
                      <div className="min-w-0">
                        <div className="truncate">{item.name}</div>
                        <div className="truncate text-[11px] font-normal text-muted-foreground">
                          {item.description}
                        </div>
                      </div>
                    )}
                  </Link>
                );
              })}
            </div>
          </nav>

          {!sidebarCollapsed && (
            <div className="px-4">
              <div className="text-xs font-medium text-muted-foreground mb-2">
                Recent workspaces
              </div>
              <div className="space-y-1">
                {apps.length === 0 ? (
                  <div className="rounded-lg border bg-white p-3 text-xs text-muted-foreground">
                    No applications yet. Start with <span className="font-medium">New Application</span>.
                  </div>
                ) : (
                  apps.slice(0, 4).map((a) => (
                    <Link
                      key={a.id}
                      href={`/applications/${a.id}`}
                      className="block rounded-lg border bg-white px-3 py-2 hover:bg-muted transition-colors"
                    >
                      <div className="text-sm font-medium truncate">
                        {a.job.title || "Untitled application"}
                      </div>
                      <div className="text-xs text-muted-foreground truncate">
                        {a.job.company || "Workspace"}
                      </div>
                    </Link>
                  ))
                )}
              </div>
            </div>
          )}

          <div className="absolute bottom-0 left-0 right-0 border-t bg-white/70 backdrop-blur supports-[backdrop-filter]:bg-white/50">
            <div className={cn("px-4 py-3 flex items-center gap-3", sidebarCollapsed && "justify-center")}>
              <div className="h-9 w-9 rounded-full bg-muted flex items-center justify-center text-sm font-semibold">
                {initials(user?.email)}
              </div>
              {!sidebarCollapsed && (
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium truncate">
                    {user?.displayName || user?.email || "User"}
                  </div>
                  <div className="text-xs text-muted-foreground truncate">
                    Signed in
                  </div>
                </div>
              )}
              <Button
                variant="ghost"
                size="icon"
                onClick={handleSignOut}
                aria-label="Sign out"
                className="text-muted-foreground"
              >
                <LogOut className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </aside>

        {/* Main */}
        <div className="min-w-0 flex-1">
          <header className="sticky top-0 z-30 border-b bg-white/70 backdrop-blur supports-[backdrop-filter]:bg-white/50">
            <div className="flex items-center gap-3 px-6 py-4">
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold truncate">
                  {pageTitle || "Workspace"}
                </div>
                {pageHint ? (
                  <div className="text-xs text-muted-foreground truncate">
                    {pageHint}
                  </div>
                ) : null}
              </div>
              {actions ? <div className="hidden sm:flex items-center gap-2">{actions}</div> : null}
              <Button
                variant="outline"
                size="sm"
                onClick={() => setCmdOpen(true)}
                className="gap-2"
              >
                <CommandIcon className="h-4 w-4" />
                <span className="hidden sm:inline">Search</span>
                <span className="hidden sm:inline text-xs text-muted-foreground">⌘K</span>
              </Button>
            </div>
          </header>

          <main className="px-6 py-6">{children}</main>
        </div>
      </div>
    </div>
  );
}
