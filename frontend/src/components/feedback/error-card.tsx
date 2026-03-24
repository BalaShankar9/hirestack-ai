"use client";

import { AlertCircle } from "lucide-react";
import { RetryButton } from "./retry-button";

interface ErrorCardProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  className?: string;
}

export function ErrorCard({ title = "Something went wrong", message, onRetry, className = "" }: ErrorCardProps) {
  return (
    <div
      role="alert"
      aria-live="assertive"
      className={`rounded-xl border border-destructive/30 bg-destructive/5 p-4 ${className}`}
    >
      <div className="flex items-start gap-3">
        <AlertCircle className="h-5 w-5 text-destructive shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <p className="font-medium text-destructive text-sm">{title}</p>
          <p className="text-sm text-muted-foreground mt-1">{message}</p>
          {onRetry && <RetryButton onClick={onRetry} className="mt-3" />}
        </div>
      </div>
    </div>
  );
}
