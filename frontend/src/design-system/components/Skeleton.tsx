/**
 * Skeleton Component
 *
 * Loading placeholder with animated shimmer effect.
 * Accessible - hidden from screen readers while loading.
 */

import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";
import { cn } from "@/lib/utils";

// ─────────────────────────────────────────────────────────────────────────────
// Variants
// ─────────────────────────────────────────────────────────────────────────────

const skeletonVariants = cva(
  "relative overflow-hidden rounded-md bg-[var(--color-muted)] animate-pulse",
  {
    variants: {
      variant: {
        text: "h-4 w-full",
        title: "h-6 w-3/4",
        heading: "h-8 w-1/2",
        avatar: "h-10 w-10 rounded-full",
        thumbnail: "h-20 w-20 rounded-md",
        image: "h-48 w-full rounded-lg",
        card: "h-32 w-full rounded-lg",
        circle: "rounded-full",
      },
    },
    defaultVariants: {
      variant: "text",
    },
  }
);

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export interface SkeletonProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof skeletonVariants> {
  animate?: boolean;
  count?: number;
}

const Skeleton = React.forwardRef<HTMLDivElement, SkeletonProps>(
  (
    { className, variant, animate = true, count = 1, style, ...props },
    ref
  ) => {
    const SkeletonItem = () => (
      <div
        ref={ref}
        className={cn(skeletonVariants({ variant }), animate && "animate-pulse", className)}
        style={style}
        aria-hidden="true"
        {...props}
      >
        {/* Shimmer overlay */}
        <div className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-[var(--color-background)]/20 to-transparent" />
      </div>
    );

    if (count > 1) {
      return (
        <div className="space-y-2">
          {Array.from({ length: count }).map((_, i) => (
            <SkeletonItem key={i} />
          ))}
        </div>
      );
    }

    return <SkeletonItem />;
  }
);

Skeleton.displayName = "Skeleton";

// ─────────────────────────────────────────────────────────────────────────────
// Skeleton Card
// ─────────────────────────────────────────────────────────────────────────────

export interface SkeletonCardProps extends React.HTMLAttributes<HTMLDivElement> {
  lines?: number;
  hasHeader?: boolean;
  hasFooter?: boolean;
}

const SkeletonCard = React.forwardRef<HTMLDivElement, SkeletonCardProps>(
  ({ className, lines = 3, hasHeader = true, hasFooter = true, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        "rounded-lg border border-[var(--color-border)] bg-[var(--color-background-elevated)] p-6",
        className
      )}
      {...props}
    >
      {hasHeader && (
        <div className="flex items-center space-x-4 pb-4">
          <Skeleton variant="avatar" className="h-12 w-12" />
          <div className="flex-1 space-y-2">
            <Skeleton variant="title" className="h-5 w-1/3" />
            <Skeleton variant="text" className="h-3 w-1/4" />
          </div>
        </div>
      )}

      <div className="space-y-2">
        {Array.from({ length: lines }).map((_, i) => (
          <Skeleton
            key={i}
            variant="text"
            className={cn(i === lines - 1 && "w-3/4")}
          />
        ))}
      </div>

      {hasFooter && (
        <div className="flex justify-end space-x-2 pt-4">
          <Skeleton variant="text" className="h-9 w-24" />
          <Skeleton variant="text" className="h-9 w-24" />
        </div>
      )}
    </div>
  )
);

SkeletonCard.displayName = "SkeletonCard";

// ─────────────────────────────────────────────────────────────────────────────
// Exports
// ─────────────────────────────────────────────────────────────────────────────

export { Skeleton, SkeletonCard };
