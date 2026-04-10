"use client";

import React, { useState, useEffect } from "react";
import { useAuth } from "@/components/providers";
import api from "@/lib/api";
import { cn } from "@/lib/utils";
import Link from "next/link";
import {
  CreditCard, ArrowLeft, Loader2,
  FileText, ScanSearch, Bot, Users,
} from "lucide-react";
import { RoleGate } from "@/components/role-gate";

export default function BillingPage() {
  const { session } = useAuth();
  const [billing, setBilling] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!session?.access_token) return;
    api.setToken(session.access_token);
    api.request("/billing/status").then((r: any) => setBilling(r)).catch(() => { setBilling(null); }).finally(() => setLoading(false));
  }, [session?.access_token]);

  const usage = billing?.usage || {};

  return (
    <RoleGate feature="billing" title="Usage" features={["View usage statistics"]}>
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <Link href="/settings" className="text-muted-foreground hover:text-foreground"><ArrowLeft className="h-5 w-5" /></Link>
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/10"><CreditCard className="h-5 w-5 text-emerald-500" /></div>
        <div>
          <h1 className="text-lg font-bold">Usage</h1>
          <p className="text-xs text-muted-foreground">Monitor your account usage</p>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-12"><Loader2 className="h-8 w-8 animate-spin mx-auto text-muted-foreground" /></div>
      ) : (
        <div className="rounded-2xl border bg-card p-5 shadow-soft-sm">
          <h2 className="font-semibold text-sm mb-4">Current Usage</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { key: "applications", label: "Applications", icon: FileText },
              { key: "ats_scans", label: "ATS Scans", icon: ScanSearch },
              { key: "ai_calls", label: "AI Calls", icon: Bot },
              { key: "members", label: "Members", icon: Users },
            ].map((meter) => {
              const used = usage[meter.key] || 0;
              return (
                <div key={meter.key} className="space-y-2">
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <meter.icon className="h-3 w-3" /> {meter.label}
                  </div>
                  <div className="text-lg font-bold tabular-nums">{used}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
    </RoleGate>
  );
}
