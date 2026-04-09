"use client";

import React from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Lock, ArrowRight, Eye } from "lucide-react";

interface LockedStateProps {
  /** What this page/feature does */
  title: string;
  /** What the user gets when they sign in */
  description: string;
  /** Bullet points of what unlocks */
  features?: string[];
  /** Custom icon (defaults to Lock) */
  icon?: React.ElementType;
  /** CTA label (defaults to "Sign in to unlock") */
  actionLabel?: string;
  /** CTA href (defaults to /login) */
  actionHref?: string;
  onAction?: () => void;
  /** Optional demo/preview content shown below the lock message */
  preview?: React.ReactNode;
  className?: string;
}

/**
 * Reusable locked-state component for auth-gated pages.
 * Shows: what this page does, what's locked, what unlocks after sign-in,
 * and optionally a sample/demo preview.
 */
export function LockedState({
  title,
  description,
  features,
  icon: Icon = Lock,
  actionLabel = "Sign in to unlock",
  actionHref = "/login",
  onAction,
  preview,
  className,
}: LockedStateProps) {
  return (
    <div className={cn("space-y-6", className)}>
      {/* Lock message card */}
      <div className="rounded-2xl border bg-card p-8 text-center">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10">
          <Icon className="h-6 w-6 text-primary" />
        </div>
        <h2 className="mt-4 text-lg font-semibold">{title}</h2>
        <p className="mt-2 max-w-md mx-auto text-sm text-muted-foreground leading-relaxed">
          {description}
        </p>

        {features && features.length > 0 && (
          <ul className="mt-4 mx-auto max-w-sm space-y-2 text-left">
            {features.map((feature, i) => (
              <li key={i} className="flex items-start gap-2.5 text-sm text-muted-foreground">
                <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10">
                  <svg viewBox="0 0 12 12" className="h-3 w-3 text-primary">
                    <path
                      d="M2 6l3 3 5-5"
                      stroke="currentColor"
                      strokeWidth="2"
                      fill="none"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </div>
                {feature}
              </li>
            ))}
          </ul>
        )}

        <div className="mt-6">
          <Button className="gap-2 rounded-xl" asChild>
            <a href={actionHref} onClick={onAction}>
              {actionLabel}
              <ArrowRight className="h-3.5 w-3.5" />
            </a>
          </Button>
        </div>
      </div>

      {/* Optional demo preview */}
      {preview && (
        <div className="relative">
          <div className="absolute -top-3 left-4 z-10 flex items-center gap-1.5 rounded-full border bg-card px-3 py-1 text-xs font-medium text-muted-foreground shadow-sm">
            <Eye className="h-3 w-3" />
            Preview
          </div>
          <div className="rounded-2xl border bg-card/50 p-6 opacity-60 pointer-events-none select-none">
            {preview}
          </div>
        </div>
      )}
    </div>
  );
}
