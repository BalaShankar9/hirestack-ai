"use client";

import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useAuth } from "@/components/providers";
import { useQuota } from "@/contexts/quota-context";
import { PLANS } from "@/lib/plans";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
} from "@/components/ui/dialog";
import { Zap, Check, Crown, ArrowRight, Sparkles, TrendingUp } from "lucide-react";
import api from "@/lib/api";
import { cn } from "@/lib/utils";

interface UpgradeModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  feature?: string;
}

const PLAN_ICONS = [Zap, Crown, TrendingUp];
const PLAN_GRADIENTS = [
  "from-blue-500 to-cyan-500",
  "from-violet-500 to-purple-600",
  "from-amber-500 to-orange-500",
];

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
      if (resp?.url) window.location.href = resp.url;
    } catch {
      window.location.href = "/pricing";
    } finally {
      setUpgrading(null);
    }
  }

  const paidPlans = PLANS.filter((p) => p.price > 0);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl p-0 overflow-hidden border-0 shadow-2xl">
        {/* Header with gradient */}
        <div className="relative bg-gradient-to-br from-amber-500/10 via-orange-500/5 to-transparent px-8 pt-8 pb-6">
          <div className="absolute right-6 top-4 opacity-[0.06]">
            <Crown className="h-28 w-28" />
          </div>
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <div className="inline-flex items-center gap-1.5 rounded-full bg-amber-500/10 px-3 py-1 text-[10px] font-semibold text-amber-600 uppercase tracking-wider mb-3">
              <Sparkles className="h-3 w-3" /> Upgrade to unlock
            </div>
            <h2 className="text-xl font-bold">You&apos;re building great applications!</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              You&apos;ve used {used}/{limit} free {feature} this month. Upgrade to keep the momentum going.
            </p>

            {/* Usage bar */}
            <div className="mt-4 h-2 rounded-full bg-muted overflow-hidden">
              <motion.div
                className="h-full rounded-full bg-gradient-to-r from-amber-500 to-orange-500"
                initial={{ width: 0 }}
                animate={{ width: `${Math.min(100, (used / Math.max(limit, 1)) * 100)}%` }}
                transition={{ duration: 0.8, ease: "easeOut" }}
              />
            </div>
          </motion.div>
        </div>

        {/* Plan cards */}
        <div className="px-8 pb-8">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-2">
            {paidPlans.map((tier, i) => {
              const Icon = PLAN_ICONS[i];
              return (
                <motion.div
                  key={tier.key}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.1 + i * 0.1 }}
                  className={cn(
                    "rounded-2xl border p-5 relative transition-all hover:-translate-y-0.5",
                    tier.popular
                      ? "border-primary shadow-glow-sm bg-primary/[0.02] ring-1 ring-primary/20"
                      : "hover:border-primary/30 hover:shadow-soft-sm"
                  )}
                >
                  {tier.popular && (
                    <Badge className="absolute -top-2.5 left-1/2 -translate-x-1/2 bg-primary text-[10px] shadow-glow-sm">
                      Recommended
                    </Badge>
                  )}

                  <div className={`inline-flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br ${PLAN_GRADIENTS[i]} shadow-sm mb-3`}>
                    <Icon className="h-4 w-4 text-white" />
                  </div>

                  <h3 className="font-bold">{tier.name}</h3>
                  <div className="mt-1 flex items-baseline gap-0.5">
                    <span className="text-2xl font-bold">${tier.price}</span>
                    <span className="text-xs text-muted-foreground">/mo</span>
                  </div>

                  <ul className="mt-4 space-y-2">
                    {tier.features.slice(0, 4).map((f, j) => (
                      <li key={j} className="flex items-start gap-2 text-[11px] text-muted-foreground">
                        <Check className="h-3 w-3 text-emerald-500 mt-0.5 shrink-0" />
                        {f}
                      </li>
                    ))}
                  </ul>

                  <Button
                    className={cn("w-full mt-5 rounded-xl h-9 text-xs gap-1.5 transition-all",
                      tier.popular && "shadow-glow-sm hover:shadow-glow-md"
                    )}
                    variant={tier.popular ? "default" : "outline"}
                    onClick={() => handleUpgrade(tier.key)}
                    disabled={upgrading !== null}
                  >
                    {upgrading === tier.key ? (
                      <span className="animate-pulse">Processing...</span>
                    ) : (
                      <>
                        Get {tier.name}
                        <ArrowRight className="h-3 w-3" />
                      </>
                    )}
                  </Button>
                </motion.div>
              );
            })}
          </div>

          <motion.button
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.5 }}
            className="w-full text-center text-xs text-muted-foreground/60 hover:text-muted-foreground transition-colors mt-5"
            onClick={() => onOpenChange(false)}
          >
            Continue with free plan
          </motion.button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
