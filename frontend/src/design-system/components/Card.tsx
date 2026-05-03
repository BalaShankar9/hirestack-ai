/**
 * Card Component
 *
 * Versatile card component with header, content, and footer sections.
 * Supports hover animations and multiple elevation levels.
 */

import { cva, type VariantProps } from "class-variance-authority";
import { motion } from "framer-motion";
import * as React from "react";
import { cn } from "@/lib/utils";
import { interactions } from "../tokens/motion";

// ─────────────────────────────────────────────────────────────────────────────
// Variants
// ─────────────────────────────────────────────────────────────────────────────

const cardVariants = cva(
  "rounded-lg border bg-[var(--color-background-elevated)] text-[var(--color-foreground)]",
  {
    variants: {
      elevation: {
        flat: "border-[var(--color-border)]",
        raised:
          "border-[var(--color-border)] shadow-md hover:shadow-lg transition-shadow",
        floating:
          "border-transparent shadow-xl hover:shadow-2xl transition-shadow",
      },
      padding: {
        none: "",
        sm: "p-4",
        md: "p-6",
        lg: "p-8",
      },
      interactive: {
        true: "cursor-pointer",
        false: "",
      },
    },
    defaultVariants: {
      elevation: "raised",
      padding: "md",
      interactive: false,
    },
  }
);

// ─────────────────────────────────────────────────────────────────────────────
// Root Component
// ─────────────────────────────────────────────────────────────────────────────

export interface CardProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof cardVariants> {
  as?: React.ElementType;
}

const Card = React.forwardRef<HTMLDivElement, CardProps>(
  (
    { className, elevation, padding, interactive, as: Component = "div", ...props },
    ref
  ) => {
    const MotionComponent = motion(Component as any);

    return (
      <MotionComponent
        ref={ref}
        className={cn(cardVariants({ elevation, padding, interactive, className }))}
        whileHover={interactive ? interactions.cardHover : undefined}
        {...props}
      />
    );
  }
);

Card.displayName = "Card";

// ─────────────────────────────────────────────────────────────────────────────
// Header
// ─────────────────────────────────────────────────────────────────────────────

export interface CardHeaderProps extends React.HTMLAttributes<HTMLDivElement> {
  title?: string;
  description?: string;
  action?: React.ReactNode;
}

const CardHeader = React.forwardRef<HTMLDivElement, CardHeaderProps>(
  ({ className, title, description, action, children, ...props }, ref) => (
    <div
      ref={ref}
      className={cn("flex items-start justify-between space-y-0 pb-4", className)}
      {...props}
    >
      <div className="flex-1 space-y-1">
        {title && (
          <h3 className="text-lg font-semibold leading-none tracking-tight">
            {title}
          </h3>
        )}
        {description && (
          <p className="text-sm text-[var(--color-muted-foreground)]">
            {description}
          </p>
        )}
        {children}
      </div>
      {action && <div className="ml-4">{action}</div>}
    </div>
  )
);

CardHeader.displayName = "CardHeader";

// ─────────────────────────────────────────────────────────────────────────────
// Content
// ─────────────────────────────────────────────────────────────────────────────

export interface CardContentProps extends React.HTMLAttributes<HTMLDivElement> {}

const CardContent = React.forwardRef<HTMLDivElement, CardContentProps>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("", className)} {...props} />
  )
);

CardContent.displayName = "CardContent";

// ─────────────────────────────────────────────────────────────────────────────
// Footer
// ─────────────────────────────────────────────────────────────────────────────

export interface CardFooterProps extends React.HTMLAttributes<HTMLDivElement> {
  align?: "left" | "center" | "right" | "between";
}

const CardFooter = React.forwardRef<HTMLDivElement, CardFooterProps>(
  ({ className, align = "between", ...props }, ref) => {
    const alignClasses = {
      left: "justify-start",
      center: "justify-center",
      right: "justify-end",
      between: "justify-between",
    };

    return (
      <div
        ref={ref}
        className={cn(
          "flex items-center pt-4",
          alignClasses[align],
          className
        )}
        {...props}
      />
    );
  }
);

CardFooter.displayName = "CardFooter";

// ─────────────────────────────────────────────────────────────────────────────
// Exports
// ─────────────────────────────────────────────────────────────────────────────

export { Card, CardHeader, CardContent, CardFooter };
