"use client";

import React, { Component, type ErrorInfo, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { reportError } from "@/lib/error-reporting";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorCount: number;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null, errorCount: 0 };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    const count = this.state.errorCount + 1;
    this.setState({ errorCount: count });
    console.error("[ErrorBoundary]", error, errorInfo);
    reportError(error, errorInfo.componentStack ?? undefined);
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      const isCrashLoop = this.state.errorCount >= 3;

      return (
        <div className="flex min-h-[300px] flex-col items-center justify-center gap-4 rounded-lg border border-red-200 bg-red-50 p-8 text-center">
          <div className="text-4xl">⚠️</div>
          <h2 className="text-lg font-semibold text-red-800">Something went wrong</h2>
          <p className="max-w-md text-sm text-red-600">
            {this.state.error?.message ?? "An unexpected error occurred."}
          </p>
          {isCrashLoop && (
            <p className="max-w-md text-xs text-red-500">
              This error has occurred multiple times. Reloading the page may help.
            </p>
          )}
          <div className="flex gap-3">
            {!isCrashLoop && (
              <Button variant="outline" onClick={this.handleReset}>
                Try again
              </Button>
            )}
            <Button variant="outline" onClick={() => window.location.reload()}>
              Reload page
            </Button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

/**
 * Lightweight section-level error boundary.
 * Shows a compact inline error instead of crashing the whole page.
 */
export class SectionErrorBoundary extends Component<
  { children: ReactNode; label?: string },
  { hasError: boolean; error: Error | null }
> {
  constructor(props: { children: ReactNode; label?: string }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error(`[SectionErrorBoundary${this.props.label ? `: ${this.props.label}` : ""}]`, error, errorInfo);
    reportError(error, errorInfo.componentStack ?? undefined);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="rounded-xl border border-red-200 bg-red-50/50 p-4 text-center">
          <p className="text-xs text-red-600">
            {this.props.label ? `${this.props.label}: ` : ""}Failed to render this section.
          </p>
          <button
            className="mt-2 text-xs text-red-500 underline"
            onClick={() => this.setState({ hasError: false, error: null })}
          >
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
