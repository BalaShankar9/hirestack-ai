"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import type { User } from "firebase/auth";
import { onIdTokenChanged } from "firebase/auth";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/components/providers";
import { auth } from "@/lib/firebase";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { user, loading } = useAuth();
  const [authUser, setAuthUser] = useState<User | null>(() => auth.currentUser);
  const [authReady, setAuthReady] = useState(false);

  useEffect(() => {
    return onIdTokenChanged(auth, (nextUser) => {
      setAuthUser(nextUser);
      setAuthReady(true);
    });
  }, []);

  const effectiveUser = useMemo(() => user ?? authUser, [authUser, user]);
  const gateLoading = loading || !authReady;

  useEffect(() => {
    if (gateLoading) {
      return;
    }

    if (!effectiveUser) {
      router.replace("/login");
      return;
    }
  }, [effectiveUser, gateLoading, router]);

  if (gateLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (!effectiveUser) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  const pathname = usePathname();
  const routeMeta = getRouteMeta(pathname);

  return (
    <AppShell
      pageTitle={routeMeta.title}
      pageHint={routeMeta.hint}
      actions={
        routeMeta.showNewCta ? (
          <Button onClick={() => router.push("/new")}>New application</Button>
        ) : null
      }
    >
      {children}
    </AppShell>
  );
}

function getRouteMeta(pathname: string): { title: string; hint: string; showNewCta: boolean } {
  if (pathname.startsWith("/applications/")) {
    return {
      title: "Application Workspace",
      hint: "Diagnose → plan → build proof → ship → track",
      showNewCta: false,
    };
  }
  if (pathname === "/new") {
    return {
      title: "New Application Wizard",
      hint: "Lock facts, sharpen the JD, then generate modules with a progress stepper.",
      showNewCta: false,
    };
  }
  if (pathname === "/evidence") {
    return {
      title: "Evidence Vault",
      hint: "Proof you can reuse across applications — links, files, and tagged wins.",
      showNewCta: true,
    };
  }
  if (pathname === "/career") {
    return {
      title: "Career Lab",
      hint: "Skill sprints + learning plan — built from your gaps.",
      showNewCta: true,
    };
  }
  return {
    title: "Dashboard",
    hint: "Your workspaces, action queue, and next-best moves.",
    showNewCta: true,
  };
}
