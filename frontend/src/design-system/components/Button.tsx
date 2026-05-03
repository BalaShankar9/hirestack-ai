/**
 * Button Component
 *
 * Accessible, animated button with multiple variants and sizes.
 * Uses design system tokens for consistent styling.
 */

import { cva, type VariantProps } from "class-variance-authority";
import { motion, type HTMLMotionProps } from "framer-motion";
import { Loader2 } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/utils";
import { interactions } from "../tokens/motion";

// ─────────────────────────────────────────────────────────────────────────────
// Variants
// ─────────────────────────────────────────────────────────────────────────────

const buttonVariants = cva(
  // Base styles
  "inline-flex items-center justify-center rounded-md font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        primary:
          "bg-[var(--color-primary)] text-[var(--color-primary-foreground)] hover:bg-[var(--color-primary-hover)] active:bg-[var(--color-primary-active)]",
        secondary:
          "bg-[var(--color-secondary)] text-[var(--color-secondary-foreground)] hover:bg-[var(--color-secondary-hover)] active:bg-[var(--color-secondary-active)]",
        outline:
          "border border-[var(--color-border)] bg-transparent hover:bg-[var(--color-accent)] hover:text-[var(--color-accent-foreground)]",
        ghost:
          "hover:bg-[var(--color-accent)] hover:text-[var(--color-accent-foreground)]",
        danger:
          "bg-[var(--color-destructive)] text-[var(--color-destructive-foreground)] hover:bg-[var(--color-destructive-hover)]",
        link: "text-[var(--color-primary)] underline-offset-4 hover:underline",
      },
      size: {
        sm: "h-8 px-3 text-xs",
        md: "h-10 px-4 text-sm",
        lg: "h-12 px-6 text-base",
        icon: "h-10 w-10",
        "icon-sm": "h-8 w-8",
        "icon-lg": "h-12 w-12",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  }
);

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

export interface ButtonProps
  extends Omit<HTMLMotionProps<"button">, "size">,
    VariantProps<typeof buttonVariants> {
  loading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
  asChild?: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant,
      size,
      loading = false,
      leftIcon,
      rightIcon,
      children,
      disabled,
      asChild = false,
      ...props
    },
    ref
  ) => {
    const isIconOnly = size?.startsWith("icon") && !children;
    const content = (
      <>
        {loading && (
          <Loader2
            className={cn(
              "animate-spin",
              isIconOnly ? "h-4 w-4" : "mr-2 h-4 w-4"
            )}
          />
        )}
        {!loading && leftIcon && (
          <span className={isIconOnly ? "" : "mr-2"}>{leftIcon}</span>
        )}
        {children}
        {!loading && rightIcon && (
          <span className={isIconOnly ? "" : "ml-2"}>{rightIcon}</span>
        )}
      </>
    );

    return (
      <motion.button
        ref={ref}
        className={cn(buttonVariants({ variant, size, className }))}
        disabled={disabled || loading}
        whileTap={interactions.buttonTap}
        {...props}
      >
        {content}
      </motion.button>
    );
  }
);

Button.displayName = "Button";

export { Button, buttonVariants };
