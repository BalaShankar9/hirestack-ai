"use client";

import React from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ArrowRight } from "lucide-react";

interface EmptyStateProps {
  icon: React.ElementType;
  title: string;
  description: string;
  /** Primary call-to-action */
  actionLabel?: string;
  actionHref?: string;
  onAction?: () => void;
  /** Secondary action */
  secondaryLabel?: string;
  secondaryHref?: string;
  onSecondary?: () => void;
  /** Visual style */
  variant?: "default" | "dashed" | "compact";
  /** Optional children (e.g. sample preview) */
  children?: React.ReactNode;
  className?: string;
}

/**
 * Reusable empty state component.
 * Every empty state must: explain why it is empty, explain what the user gets next,
 * and provide one clear CTA.
 */
export function EmptyState({
  icon: Icon,
  title,
  description,
  actionLabel,
  actionHref,
  onAction,
  secondaryLabel,
  secondaryHref,
  onSecondary,
  variant = "default",
  children,
  className,
}: EmptyStateProps) {
  const ActionWrapper = actionHref ? "a" : "button";
  const SecondaryWrapper = secondaryHref ? "a" : "button";

  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center",
        variant === "dashed" && "rounded-2xl border border-dashed bg-card/50 p-10",
        variant === "default" && "rounded-2xl border bg-card p-10",
        variant === "compact" && "rounded-xl border bg-card/50 p-6",
        className
      )}
    >
      <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10">
        <Icon className="h-6 w-6 text-primary" />
      </div>
      <h3 className="mt-4 text-sm font-semibold">{title}</h3>
      <p className="mt-1.5 max-w-sm text-xs text-muted-foreground leading-relaxed">
        {description}
      </p>

      {children && <div className="mt-5 w-full">{children}</div>}

      {(actionLabel || secondaryLabel) && (
        <div className="mt-5 flex items-center gap-3">
          {actionLabel && (
            <Button
              className="gap-2 rounded-xl"
              onClick={onAction}
              {...(actionHref ? { asChild: true } : {})}
            >
              {actionHref ? (
                <a href={actionHref}>
                  {actionLabel}
                  <ArrowRight className="h-3.5 w-3.5" />
                </a>
              ) : (
                <>
                  {actionLabel}
                  <ArrowRight className="h-3.5 w-3.5" />
                </>
              )}
            </Button>
          )}
          {secondaryLabel && (
            <Button
              variant="outline"
              className="rounded-xl"
              onClick={onSecondary}
              {...(secondaryHref ? { asChild: true } : {})}
            >
              {secondaryHref ? (
                <a href={secondaryHref}>{secondaryLabel}</a>
              ) : (
                secondaryLabel
              )}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
