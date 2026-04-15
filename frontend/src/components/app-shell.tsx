"use client";

import React, { type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Home,
  ShieldCheck,
  LogOut,
  Menu,
  X,
  Plus,
  Sparkles,
  ChevronLeft,
  Loader2,
  Settings,
  Users,
  Search,
  ArrowRight,
  User,
} from "lucide-react";
import { useAuth } from "@/components/providers";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { CommandPalette } from "@/components/command-palette/command-palette";
import { ThemeToggle } from "@/components/theme-toggle";

type NavItem = {
  href: string;
  label: string;
  icon: typeof Home;
  description: string;
  /** Only show when user role matches */
  roleRequired?: "admin" | "enterprise";
};
type NavGroup = { title: string; items: NavItem[] };

/**
 * Navigation hierarchy:
 * - Core: The primary user journey (target role → generate → improve → track)
 * - Tools: Supporting tools that enhance the core flow
 * - Admin: Enterprise/org features, only visible when role permits
 *
 * Naming: Plain language first. Internal brand names removed from primary labels.
 */
const NAV_GROUPS: NavGroup[] = [
  {
    title: "Core",
    items: [
      { href: "/dashboard", label: "Overview", icon: Home, description: "Your command center" },
      { href: "/new", label: "New Application", icon: Plus, description: "Start a new application" },
      { href: "/evidence", label: "Evidence", icon: ShieldCheck, description: "Your proof library" },
      { href: "/nexus", label: "Profile", icon: User, description: "Your career identity" },
      { href: "/settings", label: "Settings", icon: Settings, description: "Account & organization" },
    ],
  },
  {
    title: "Admin",
    items: [
      { href: "/candidates", label: "Pipeline", icon: Users, description: "Candidate tracking", roleRequired: "enterprise" },
    ],
  },
];

export function AppShell({ children }: { children: ReactNode }) {
  const { user, signOut } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [sidebarOpen, setSidebarOpen] = React.useState(false);
  const [collapsed, setCollapsed] = React.useState(false);
  const [signingOut, setSigningOut] = React.useState(false);
  const [navSearch, setNavSearch] = React.useState("");

  // Role-based nav filtering: hide enterprise items unless user has that role
  // For now, we assume user metadata may contain role info
  const userRole = user?.user_metadata?.role as string | undefined;

  const filteredGroups = React.useMemo(() => {
    let groups = NAV_GROUPS.map((g) => ({
      ...g,
      items: g.items.filter((item) => {
        // Filter role-gated items
        if (item.roleRequired === "enterprise" && userRole !== "admin" && userRole !== "enterprise") {
          return false;
        }
        if (item.roleRequired === "admin" && userRole !== "admin") {
          return false;
        }
        return true;
      }),
    })).filter((g) => g.items.length > 0);

    if (!navSearch.trim()) return groups;
    const q = navSearch.toLowerCase();
    return groups.map((g) => ({
      ...g,
      items: g.items.filter(
        (item) =>
          item.label.toLowerCase().includes(q) ||
          item.description.toLowerCase().includes(q)
      ),
    })).filter((g) => g.items.length > 0);
  }, [navSearch, userRole]);

  const handleSignOut = async () => {
    setSigningOut(true);
    try {
      await signOut();
      router.replace("/login");
    } catch {
      setSigningOut(false);
    }
  };

  const initials = user?.displayName
    ? user.displayName
        .split(" ")
        .map((w) => w[0])
        .join("")
        .slice(0, 2)
        .toUpperCase()
    : user?.email?.slice(0, 2).toUpperCase() ?? "?";

  return (
    <div className="app-frame noise-overlay flex min-h-screen bg-transparent">
      {/* Living aurora background */}
      <div className="aurora-bg" aria-hidden="true" />
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[100] rounded-lg bg-card px-3 py-2 text-sm font-medium shadow-soft-md ring-2 ring-ring ring-offset-2 ring-offset-background"
      >
        Skip to content
      </a>
      {/* ── Sidebar (Desktop) ─────────────────────── */}
      <aside
        className={cn(
          "surface-premium z-10 hidden lg:flex flex-col border-r transition-all duration-300 ease-in-out",
          collapsed ? "w-[72px]" : "w-[272px]"
        )}
      >
        {/* Logo */}
        <div className="flex h-16 items-center gap-3 border-b border-border/70 px-4">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-violet-600 shadow-glow-sm ring-1 ring-white/50 dark:ring-white/10">
            <Sparkles className="h-4 w-4 text-white" />
          </div>
          {!collapsed && (
            <span className="text-base font-bold tracking-tight animate-fade-in">
              HireStack <span className="text-primary">AI</span>
            </span>
          )}
        </div>

        {/* Search */}
        {!collapsed && (
          <div className="px-3 pt-3">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground/60" aria-hidden="true" />
              <input
                type="text"
                placeholder="Search…"
                value={navSearch}
                onChange={(e) => setNavSearch(e.target.value)}
                aria-label="Search navigation"
                className="flex h-8 w-full rounded-lg border border-border/60 bg-muted/40 pl-8 pr-14 text-xs placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-primary/40 transition-colors"
              />
              <kbd className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 hidden sm:inline-flex items-center gap-0.5 rounded border bg-muted/60 px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground/70" aria-hidden="true">
                ⌘K
              </kbd>
            </div>
          </div>
        )}

        {/* Nav links */}
        <nav className="flex-1 overflow-y-auto px-3 py-3" aria-label="Main navigation">
          {filteredGroups.map((group, gi) => (
            <div key={group.title}>
              {gi > 0 && <div className="my-2 border-t border-border/50" />}
              {!collapsed && (
                <div className="mb-1 px-3 pt-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/50">
                  {group.title}
                </div>
              )}
              <div className="space-y-0.5">
                {group.items.map(({ href, label, icon: Icon, description }) => {
                  const active = pathname === href || (href !== "/dashboard" && pathname.startsWith(href));
                  const isExact = pathname === href;
                  const isDashboard = href === "/dashboard";
                  const show = isDashboard ? isExact : active;

                  return (
                    <Link key={href} href={href} onClick={() => setSidebarOpen(false)}>
                      <div
                        className={cn(
                          "group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-200",
                          show
                            ? "bg-gradient-to-r from-primary/14 to-primary/8 text-primary shadow-soft-sm"
                            : "text-muted-foreground hover:bg-muted/70 hover:text-foreground hover:translate-x-0.5"
                        )}
                      >
                        {show && (
                          <div className="absolute left-0 top-1/2 h-6 w-1 -translate-y-1/2 rounded-r-full bg-primary shadow-glow-sm" />
                        )}
                        <Icon className={cn("h-[18px] w-[18px] shrink-0 transition-colors", show && "text-primary")} />
                        {!collapsed && (
                          <div className="min-w-0">
                            <div className="truncate">{label}</div>
                            {!show && (
                              <div className="truncate text-[11px] text-muted-foreground/70 group-hover:text-muted-foreground transition-colors">
                                {description}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
          {filteredGroups.length === 0 && !collapsed && (
            <p className="px-3 py-6 text-center text-xs text-muted-foreground/60">No results</p>
          )}
          {!collapsed && !navSearch.trim() && (
            <div className="mt-3 mx-3 rounded-lg border border-dashed border-border/50 p-2.5 text-center">
              <p className="text-[10px] text-muted-foreground/60">
                More tools via{" "}
                <kbd className="inline-flex items-center gap-0.5 rounded border bg-muted/60 px-1 py-0.5 text-[10px] font-medium text-muted-foreground/70">⌘K</kbd>
              </p>
            </div>
          )}
        </nav>

        {/* Collapse toggle */}
        <div className="border-t border-border/70 px-3 py-2">
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="flex w-full items-center justify-center rounded-lg p-2 text-muted-foreground hover:bg-muted/60 hover:text-foreground transition-colors"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            <ChevronLeft className={cn("h-4 w-4 transition-transform duration-300", collapsed && "rotate-180")} />
          </button>
        </div>

        {/* User section */}
        <div className="border-t border-border/70 p-3">
          {user ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className={cn(
                  "flex w-full items-center gap-3 rounded-xl p-2 text-left hover:bg-muted/60 transition-colors",
                  collapsed && "justify-center"
                )}>
                  <Avatar className="h-8 w-8 ring-2 ring-primary/10 ring-offset-2 ring-offset-background">
                    <AvatarImage src={user?.photoURL ?? undefined} />
                    <AvatarFallback className="bg-primary/10 text-primary text-xs font-semibold">{initials}</AvatarFallback>
                  </Avatar>
                  {!collapsed && (
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{user?.displayName ?? "User"}</p>
                      <p className="truncate text-[11px] text-muted-foreground">{user?.email}</p>
                    </div>
                  )}
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" side="top" className="w-56">
                <div className="px-3 py-2">
                  <p className="text-sm font-medium">{user?.displayName ?? "User"}</p>
                  <p className="text-xs text-muted-foreground">{user?.email}</p>
                </div>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={handleSignOut} disabled={signingOut} className="text-destructive focus:text-destructive">
                  {signingOut ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <LogOut className="mr-2 h-4 w-4" />}
                  {signingOut ? "Signing out…" : "Sign Out"}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : (
            <div className={cn("flex flex-col gap-2", collapsed && "items-center")}>
              <Link href="/login" className="w-full">
                <Button variant="outline" size="sm" className={cn("w-full rounded-xl text-xs", collapsed && "w-9 p-0")}>
                  {collapsed ? <LogOut className="h-4 w-4 rotate-180" /> : "Sign In"}
                </Button>
              </Link>
              {!collapsed && (
                <Link href="/login?mode=register" className="w-full">
                  <Button size="sm" className="w-full rounded-xl text-xs gap-1.5 bg-primary shadow-glow-sm hover:shadow-glow-md transition-shadow">
                    Get Started <ArrowRight className="h-3 w-3" />
                  </Button>
                </Link>
              )}
            </div>
          )}
        </div>
      </aside>

      {/* ── Mobile Overlay ────────────────────────── */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" onClick={() => setSidebarOpen(false)}>
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm transition-opacity" />
          <aside
            className="surface-premium absolute left-0 top-0 h-full w-[286px] border-r shadow-soft-xl flex flex-col animate-drawer-in-left"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex h-16 items-center justify-between border-b px-4">
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-violet-600">
                  <Sparkles className="h-4 w-4 text-white" />
                </div>
                <span className="text-base font-bold tracking-tight">
                  HireStack <span className="text-primary">AI</span>
                </span>
              </div>
              <Button variant="ghost" size="icon" onClick={() => setSidebarOpen(false)} className="rounded-lg" aria-label="Close navigation menu">
                <X className="h-5 w-5" />
              </Button>
            </div>

            {/* Mobile search */}
            <div className="px-3 pt-3">
              <div className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground/60" aria-hidden="true" />
                <input
                  type="text"
                  placeholder="Search…"
                  value={navSearch}
                  onChange={(e) => setNavSearch(e.target.value)}
                  aria-label="Search navigation"
                  className="flex h-8 w-full rounded-lg border border-border/60 bg-muted/40 pl-8 pr-3 text-xs placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-primary/40 transition-colors"
                />
              </div>
            </div>

            <nav className="flex-1 overflow-y-auto p-3" aria-label="Mobile navigation">
              {filteredGroups.map((group, gi) => (
                <div key={group.title}>
                  {gi > 0 && <div className="my-2 border-t border-border/50" />}
                  <div className="mb-1 px-3 pt-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/50">
                    {group.title}
                  </div>
                  <div className="space-y-0.5">
                    {group.items.map(({ href, label, icon: Icon }) => {
                      const active = pathname === href || (href !== "/dashboard" && pathname.startsWith(href));
                      const isDashboard = href === "/dashboard";
                      const show = isDashboard ? pathname === href : active;
                      return (
                        <Link key={href} href={href} onClick={() => setSidebarOpen(false)}>
                          <div
                            className={cn(
                              "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-200",
                              show
                                ? "bg-primary/10 text-primary"
                                : "text-muted-foreground hover:bg-muted/60 hover:text-foreground hover:translate-x-0.5"
                            )}
                          >
                            <Icon className="h-[18px] w-[18px]" />
                            {label}
                          </div>
                        </Link>
                      );
                    })}
                  </div>
                </div>
              ))}
              {filteredGroups.length === 0 && (
                <p className="px-3 py-6 text-center text-xs text-muted-foreground/60">No results</p>
              )}
            </nav>

            {/* Mobile sidebar footer */}
            <div className="border-t border-border/70 p-3">
              {user ? (
                <div className="flex items-center gap-3 px-2">
                  <Avatar className="h-8 w-8">
                    <AvatarImage src={user?.photoURL ?? undefined} />
                    <AvatarFallback className="bg-primary/10 text-primary text-xs font-semibold">{initials}</AvatarFallback>
                  </Avatar>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{user?.displayName ?? "User"}</p>
                    <p className="truncate text-[11px] text-muted-foreground">{user?.email}</p>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col gap-2">
                  <Link href="/login" onClick={() => setSidebarOpen(false)}>
                    <Button variant="outline" size="sm" className="w-full rounded-xl text-xs">Sign In</Button>
                  </Link>
                  <Link href="/login?mode=register" onClick={() => setSidebarOpen(false)}>
                    <Button size="sm" className="w-full rounded-xl text-xs gap-1.5 bg-primary shadow-glow-sm">
                      Get Started <ArrowRight className="h-3 w-3" />
                    </Button>
                  </Link>
                </div>
              )}
            </div>
          </aside>
        </div>
      )}

      {/* ── Main Content ──────────────────────────── */}
      <div className="relative z-10 flex min-w-0 flex-1 flex-col">
        {/* Top bar */}
        <header className="surface-premium sticky top-0 z-30 flex h-16 items-center gap-4 border-b border-border/70 bg-background/70 px-4 lg:px-6">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden rounded-lg"
            onClick={() => setSidebarOpen(true)}
            aria-label="Open navigation menu"
          >
            <Menu className="h-5 w-5" />
          </Button>

          {/* Breadcrumb / title area */}
          {(() => {
            const PAGE_LABELS: Record<string, string> = {
              "/dashboard": "Overview",
              "/new": "New Application",
              "/evidence": "Evidence",
              "/nexus": "Profile",
              "/settings": "Settings",
              "/candidates": "Pipeline",
              "/ats-scanner": "ATS Scanner",
              "/interview": "Interview Prep",
              "/salary": "Salary Coach",
              "/career": "Career Improvement",
              "/career-analytics": "Career Analytics",
              "/job-board": "Job Board",
              "/learning": "Daily Learn",
              "/ab-lab": "Compare Versions",
              "/api-keys": "API Keys",
            };
            const label = PAGE_LABELS[pathname] || (pathname.startsWith("/applications/") ? "Workspace" : null);
            if (!label) return <div className="flex-1" />;
            return (
              <div className="flex-1 min-w-0">
                <span className="text-sm font-medium text-muted-foreground truncate">{label}</span>
              </div>
            );
          })()}

          <ThemeToggle />

          {/* Quick action */}
          <Button
            size="sm"
            className="flex gap-2 rounded-xl bg-primary btn-glow hover:shadow-glow-md transition-shadow"
            onClick={() => router.push("/new")}
            aria-label="New Application"
          >
            <Plus className="h-4 w-4" />
            <span className="hidden sm:inline">New Application</span>
          </Button>

          {/* Mobile user menu */}
          {user ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="rounded-full lg:hidden">
                  <Avatar className="h-8 w-8">
                    <AvatarImage src={user?.photoURL ?? undefined} />
                    <AvatarFallback className="bg-primary/10 text-primary text-xs font-semibold">{initials}</AvatarFallback>
                  </Avatar>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <div className="px-3 py-2">
                  <p className="text-sm font-medium">{user?.displayName ?? "User"}</p>
                  <p className="text-xs text-muted-foreground">{user?.email}</p>
                </div>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={handleSignOut} disabled={signingOut} className="text-destructive focus:text-destructive">
                  {signingOut ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <LogOut className="mr-2 h-4 w-4" />}
                  {signingOut ? "Signing out…" : "Sign Out"}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : (
            <Link href="/login" className="lg:hidden">
              <Button size="sm" className="rounded-xl text-xs gap-1.5">
                Sign In
              </Button>
            </Link>
          )}
        </header>

        {/* Page content */}
        <main id="main-content" tabIndex={-1} className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[1360px] px-4 py-6 lg:px-8">{children}</div>
        </main>
      </div>
      <CommandPalette />
    </div>
  );
}
