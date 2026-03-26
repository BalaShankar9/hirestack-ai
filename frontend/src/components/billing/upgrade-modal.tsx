"use client";

import React from "react";
import { useAuth } from "@/components/providers";
import { useQuota } from "@/contexts/quota-context";
import { PLANS } from "@/lib/plans";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Zap, Check, Crown } from "lucide-react";
import api from "@/lib/api";
import { cn } from "@/lib/utils";

interface UpgradeModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  feature?: string;
}

export function UpgradeModal({ open, onOpenChange, feature = "exports" }: UpgradeModalProps) {
  const { session } = useAuth();
  const { plan, usage } = useQuota();
  const [upgrading, setUpgrading] = React.useState<string | null>(null);

  const used = usage[feature] ?? 0;
  const limit = plan.limits[feature as keyof typeof plan.limits] ?? 0;

  async function handleUpgrade(planKey: string) {
    if (!session?.access_token) return;
    setUpgrading(planKey);
    try {
      api.setToken(session.access_token);
      const resp = await api.request("/billing/checkout", {
        method: "POST",
        body: {
          plan: planKey,
          success_url: `${window.location.origin}/settings/billing?success=true`,
          cancel_url: `${window.location.origin}/settings/billing?canceled=true`,
        },
      });
      if (resp?.url) {
        window.location.href = resp.url;
      }
    } catch {
      // Stripe not configured — redirect to pricing
      window.location.href = "/pricing";
    } finally {
      setUpgrading(null);
    }
  }

  const paidPlans = PLANS.filter((p) => p.price > 0);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-amber-500 to-orange-600 shadow-glow-sm mb-2">
            <Crown className="h-5 w-5 text-white" />
          </div>
          <DialogTitle className="text-center text-xl">
            You&apos;ve used all your free {feature}
          </DialogTitle>
          <DialogDescription className="text-center">
            {used}/{limit} used this month. Upgrade to continue building amazing applications.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-4">
          {paidPlans.map((tier) => (
            <div
              key={tier.key}
              className={cn(
                "rounded-2xl border p-4 relative transition-all",
                tier.popular
                  ? "border-primary shadow-glow-sm bg-primary/[0.02]"
                  : "hover:border-primary/30"
              )}
            >
              {tier.popular && (
                <Badge className="absolute -top-2.5 left-1/2 -translate-x-1/2 bg-primary text-[10px]">
                  Most Popular
                </Badge>
              )}
              <div className="text-center mb-3">
                <h3 className="font-semibold text-sm">{tier.name}</h3>
                <div className="mt-1">
                  <span className="text-2xl font-bold">${tier.price}</span>
                  <span className="text-xs text-muted-foreground">/mo</span>
                </div>
              </div>
              <ul className="space-y-1.5 mb-4">
                {tier.features.slice(0, 5).map((f, i) => (
                  <li key={i} className="flex items-start gap-1.5 text-[11px] text-muted-foreground">
                    <Check className="h-3 w-3 text-emerald-500 mt-0.5 shrink-0" />
                    {f}
                  </li>
                ))}
              </ul>
              <Button
                className={cn("w-full rounded-xl h-9 text-xs gap-1.5",
                  tier.popular && "bg-primary shadow-glow-sm"
                )}
                variant={tier.popular ? "default" : "outline"}
                onClick={() => handleUpgrade(tier.key)}
                disabled={upgrading !== null}
              >
                {upgrading === tier.key ? (
                  <span className="animate-pulse">Processing...</span>
                ) : (
                  <>
                    <Zap className="h-3 w-3" />
                    Upgrade to {tier.name}
                  </>
                )}
              </Button>
            </div>
          ))}
        </div>

        <button
          className="w-full text-center text-xs text-muted-foreground hover:text-foreground transition-colors mt-2"
          onClick={() => onOpenChange(false)}
        >
          Maybe later
        </button>
      </DialogContent>
    </Dialog>
  );
}
