"use client";

import React, { type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Home,
  Briefcase,
  GraduationCap,
  ShieldCheck,
  LogOut,
  Menu,
  X,
  Plus,
  Sparkles,
  ChevronLeft,
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

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: Home, description: "Overview & stats" },
  { href: "/new", label: "New Application", icon: Plus, description: "Start a workspace" },
  { href: "/career", label: "Career Lab", icon: GraduationCap, description: "Skill sprints" },
  { href: "/evidence", label: "Evidence Vault", icon: ShieldCheck, description: "Proof library" },
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  const { user, signOut } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [sidebarOpen, setSidebarOpen] = React.useState(false);
  const [collapsed, setCollapsed] = React.useState(false);

  const handleSignOut = async () => {
    await signOut();
    router.replace("/login");
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
    <div className="flex min-h-screen bg-background">
      {/* ── Sidebar (Desktop) ─────────────────────── */}
      <aside
        className={cn(
          "hidden lg:flex flex-col border-r bg-card/50 backdrop-blur-sm transition-all duration-300 ease-in-out",
          collapsed ? "w-[68px]" : "w-[260px]"
        )}
      >
        {/* Logo */}
        <div className="flex h-16 items-center gap-3 border-b px-4">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-violet-600 shadow-glow-sm">
            <Sparkles className="h-4 w-4 text-white" />
          </div>
          {!collapsed && (
            <span className="text-base font-bold tracking-tight animate-fade-in">
              HireStack <span className="text-primary">AI</span>
            </span>
          )}
        </div>

        {/* Nav links */}
        <nav className="flex-1 space-y-1 px-3 py-4">
          {NAV.map(({ href, label, icon: Icon, description }) => {
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
                      ? "bg-primary/10 text-primary shadow-sm"
                      : "text-muted-foreground hover:bg-muted/60 hover:text-foreground"
                  )}
                >
                  {show && (
                    <div className="absolute left-0 top-1/2 h-6 w-1 -translate-y-1/2 rounded-r-full bg-primary" />
                  )}
                  <Icon className={cn("h-[18px] w-[18px] shrink-0", show && "text-primary")} />
                  {!collapsed && (
                    <div className="min-w-0">
                      <div className="truncate">{label}</div>
                      {!active && (
                        <div className="truncate text-[11px] text-muted-foreground/70 group-hover:text-muted-foreground">
                          {description}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </Link>
            );
          })}
        </nav>

        {/* Collapse toggle */}
        <div className="border-t px-3 py-2">
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="flex w-full items-center justify-center rounded-lg p-2 text-muted-foreground hover:bg-muted/60 hover:text-foreground transition-colors"
          >
            <ChevronLeft className={cn("h-4 w-4 transition-transform duration-300", collapsed && "rotate-180")} />
          </button>
        </div>

        {/* User section */}
        <div className="border-t p-3">
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
              <DropdownMenuItem onClick={handleSignOut} className="text-destructive focus:text-destructive">
                <LogOut className="mr-2 h-4 w-4" />
                Sign Out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </aside>

      {/* ── Mobile Overlay ────────────────────────── */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" onClick={() => setSidebarOpen(false)}>
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />
          <aside
            className="absolute left-0 top-0 h-full w-[280px] border-r bg-card shadow-soft-xl animate-slide-in-left"
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
              <Button variant="ghost" size="icon" onClick={() => setSidebarOpen(false)} className="rounded-lg">
                <X className="h-5 w-5" />
              </Button>
            </div>
            <nav className="space-y-1 p-3">
              {NAV.map(({ href, label, icon: Icon }) => {
                const active = pathname === href || (href !== "/dashboard" && pathname.startsWith(href));
                const isDashboard = href === "/dashboard";
                const show = isDashboard ? pathname === href : active;
                return (
                  <Link key={href} href={href} onClick={() => setSidebarOpen(false)}>
                    <div
                      className={cn(
                        "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
                        show
                          ? "bg-primary/10 text-primary"
                          : "text-muted-foreground hover:bg-muted/60 hover:text-foreground"
                      )}
                    >
                      <Icon className="h-[18px] w-[18px]" />
                      {label}
                    </div>
                  </Link>
                );
              })}
            </nav>
          </aside>
        </div>
      )}

      {/* ── Main Content ──────────────────────────── */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top bar */}
        <header className="sticky top-0 z-30 flex h-16 items-center gap-4 border-b bg-background/80 backdrop-blur-xl px-4 lg:px-6">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden rounded-lg"
            onClick={() => setSidebarOpen(true)}
          >
            <Menu className="h-5 w-5" />
          </Button>

          {/* Breadcrumb / title area */}
          <div className="flex-1" />

          {/* Quick action */}
          <Button
            size="sm"
            className="hidden sm:flex gap-2 rounded-xl bg-primary shadow-glow-sm hover:shadow-glow-md transition-shadow"
            onClick={() => router.push("/new")}
          >
            <Plus className="h-4 w-4" />
            New Application
          </Button>

          {/* Mobile user menu */}
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
              <DropdownMenuItem onClick={handleSignOut} className="text-destructive focus:text-destructive">
                <LogOut className="mr-2 h-4 w-4" />
                Sign Out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-7xl px-4 py-6 lg:px-8">{children}</div>
        </main>
      </div>
    </div>
  );
}
