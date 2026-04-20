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
  const billingDisabled = billing?.plan === "billing_disabled" || billing?.billing_enabled === false;

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

      {billingDisabled && !loading ? (
        <div
          role="status"
          className="rounded-2xl border border-amber-300 bg-amber-50 p-5 shadow-soft-sm dark:border-amber-700/60 dark:bg-amber-950/40"
        >
          <h2 className="font-semibold text-sm text-amber-900 dark:text-amber-100">
            Beta access — billing is disabled
          </h2>
          <p className="mt-1 text-xs text-amber-800 dark:text-amber-200">
            HireStack AI is currently in private beta. Billing has not been enabled
            for this environment, so you will not be charged and all features
            available to your account are unrestricted. Usage metering still runs
            so we can give you a clean billing transition once the platform exits
            beta.
          </p>
        </div>
      ) : null}

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
