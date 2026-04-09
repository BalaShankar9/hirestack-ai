"use client";

import React, { useState, useEffect } from "react";
import { useAuth } from "@/components/providers";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import Link from "next/link";
import {
  CreditCard, ArrowLeft, Loader2, CheckCircle, Crown,
  Zap, Users, FileText, ScanSearch, Bot, ArrowRight,
} from "lucide-react";
import { toast } from "@/hooks/use-toast";
import { RoleGate } from "@/components/role-gate";

const PLANS = [
  {
    key: "free", name: "Free", price: 0, desc: "For individuals getting started",
    features: ["5 applications/mo", "10 ATS scans/mo", "50 AI calls/mo", "2 team members", "Standard documents"],
    color: "border-border",
  },
  {
    key: "pro", name: "Pro", price: 49, desc: "For professionals and small teams",
    features: ["50 applications/mo", "200 ATS scans/mo", "1,000 AI calls/mo", "10 team members", "All 35+ document types", "Company intel", "Read-only API"],
    color: "border-emerald-500", popular: true,
  },
  {
    key: "enterprise", name: "Enterprise", price: 199, desc: "For recruitment agencies",
    features: ["Unlimited applications", "Unlimited ATS scans", "Unlimited AI calls", "Unlimited team members", "All documents + custom", "Full API + webhooks", "White-label branding", "Dedicated support"],
    color: "border-violet-500",
  },
];

export default function BillingPage() {
  const { session } = useAuth();
  const [billing, setBilling] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [upgrading, setUpgrading] = useState("");

  useEffect(() => {
    if (!session?.access_token) return;
    api.setToken(session.access_token);
    api.request("/billing/status").then((r: any) => setBilling(r)).catch(() => {}).finally(() => setLoading(false));
  }, [session?.access_token]);

  const upgrade = async (plan: string) => {
    setUpgrading(plan);
    try {
      const result = await api.request("/billing/checkout", {
        method: "POST",
        body: { plan, success_url: `${window.location.origin}/settings/billing?success=true`, cancel_url: `${window.location.origin}/settings/billing` },
      });
      if (result?.url) {
        window.location.href = result.url;
      } else {
        toast({ title: "Stripe not configured", description: "Set STRIPE_SECRET_KEY to enable billing." });
      }
    } catch (e: any) { toast({ title: "Failed", description: e.message }); }
    setUpgrading("");
  };

  const currentPlan = billing?.plan || "free";
  const usage = billing?.usage || {};
  const limits = billing?.limits || {};

  return (
    <RoleGate feature="billing" title="Billing & Plans" features={["Manage subscription plans", "View usage & invoices", "Upgrade or downgrade plans"]}>
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <Link href="/settings" className="text-muted-foreground hover:text-foreground"><ArrowLeft className="h-5 w-5" /></Link>
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/10"><CreditCard className="h-5 w-5 text-emerald-500" /></div>
        <div>
          <h1 className="text-lg font-bold">Billing & Plans</h1>
          <p className="text-xs text-muted-foreground">Manage your subscription and monitor usage</p>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-12"><Loader2 className="h-8 w-8 animate-spin mx-auto text-muted-foreground" /></div>
      ) : (
        <>
          {/* Usage meters */}
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
                const limit = limits[meter.key] || 0;
                const pct = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
                const isUnlimited = limit === -1;
                return (
                  <div key={meter.key} className="space-y-2">
                    <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                      <meter.icon className="h-3 w-3" /> {meter.label}
                    </div>
                    <div className="text-lg font-bold tabular-nums">
                      {used}{isUnlimited ? "" : `/${limit}`}
                    </div>
                    {!isUnlimited && (
                      <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                        <div className={cn("h-full rounded-full transition-all", pct >= 90 ? "bg-rose-500" : pct >= 70 ? "bg-amber-500" : "bg-emerald-500")} style={{ width: `${pct}%` }} />
                      </div>
                    )}
                    {isUnlimited && <p className="text-2xs text-emerald-500">Unlimited</p>}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Plans */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {PLANS.map((plan) => (
              <div key={plan.key} className={cn("rounded-2xl border bg-card p-5 transition-all relative", plan.color, plan.popular && "shadow-glow-sm")}>
                {plan.popular && <Badge className="absolute -top-2 right-4 text-[10px]">Most Popular</Badge>}
                <div className="mb-4">
                  <h3 className="font-bold text-lg">{plan.name}</h3>
                  <p className="text-2xs text-muted-foreground">{plan.desc}</p>
                  <div className="mt-2">
                    <span className="text-3xl font-bold">${plan.price}</span>
                    {plan.price > 0 && <span className="text-sm text-muted-foreground">/month</span>}
                  </div>
                </div>
                <ul className="space-y-1.5 mb-4">
                  {plan.features.map((f, i) => (
                    <li key={i} className="text-xs flex items-start gap-1.5">
                      <CheckCircle className="h-3 w-3 text-emerald-500 mt-0.5 shrink-0" /> {f}
                    </li>
                  ))}
                </ul>
                {currentPlan === plan.key ? (
                  <Button variant="outline" className="w-full rounded-xl" disabled>
                    <Crown className="h-3 w-3 mr-1" /> Current Plan
                  </Button>
                ) : plan.price > (PLANS.find((p) => p.key === currentPlan)?.price || 0) ? (
                  <Button className="w-full rounded-xl gap-1" onClick={() => upgrade(plan.key)} disabled={!!upgrading}>
                    {upgrading === plan.key ? <Loader2 className="h-3 w-3 animate-spin" /> : <Zap className="h-3 w-3" />}
                    Upgrade to {plan.name}
                  </Button>
                ) : (
                  <Button variant="outline" className="w-full rounded-xl" disabled>Downgrade</Button>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
    </RoleGate>
  );
}
