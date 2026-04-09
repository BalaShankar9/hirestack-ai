"use client";

import React from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@radix-ui/react-tooltip";

interface Requirement {
  label: string;
  met: boolean;
}

interface RequiredActionButtonProps {
  /** Button label */
  children: React.ReactNode;
  /** List of requirements that must be met */
  requirements: Requirement[];
  /** Fires when all requirements are met and button is clicked */
  onClick: () => void;
  /** Button loading state */
  loading?: boolean;
  /** Additional button className */
  className?: string;
  /** Button size */
  size?: "default" | "sm" | "lg";
  /** Icon to show in the button */
  icon?: React.ReactNode;
}

/**
 * A CTA button that shows disabled state with exact reasons when
 * prerequisites are not met. When all requirements pass, functions normally.
 */
export function RequiredActionButton({
  children,
  requirements,
  onClick,
  loading = false,
  className,
  size = "default",
  icon,
}: RequiredActionButtonProps) {
  const allMet = requirements.every((r) => r.met);
  const missing = requirements.filter((r) => !r.met);

  if (allMet) {
    return (
      <Button
        className={cn("gap-2 rounded-xl", className)}
        onClick={onClick}
        disabled={loading}
        size={size}
      >
        {icon}
        {children}
      </Button>
    );
  }

  return (
    <div className="relative group">
      <Button
        className={cn("gap-2 rounded-xl", className)}
        disabled
        size={size}
      >
        {icon}
        {children}
      </Button>
      {/* Requirements tooltip on hover */}
      <div className="absolute left-1/2 -translate-x-1/2 top-full mt-2 z-50 hidden group-hover:block">
        <div className="rounded-xl border bg-popover px-4 py-3 shadow-md text-left min-w-[220px]">
          <p className="text-xs font-semibold text-foreground mb-2">Required to continue:</p>
          <ul className="space-y-1.5">
            {missing.map((req, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-muted-foreground">
                <div className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />
                {req.label}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
