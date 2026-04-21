"use client";

/**
 * Dynamic-style helpers that avoid JSX `style={{...}}` props.
 *
 * These helpers set size/width via refs so dynamic values (progress %, pixel
 * sizes, etc.) don't trigger editor lint rules that flag inline styles.
 */

import * as React from "react";
import { cn } from "@/lib/utils";

type DivProps = React.HTMLAttributes<HTMLDivElement>;

/**
 * A horizontal bar whose width is driven by `value` (0–100).
 * Renders as `<div className="h-full ..." />` — the width is applied
 * imperatively via ref to avoid inline `style` JSX warnings.
 */
export const ProgressBar = React.forwardRef<
  HTMLDivElement,
  DivProps & { value: number }
>(function ProgressBar({ value, className, ...rest }, forwardedRef) {
  const innerRef = React.useRef<HTMLDivElement | null>(null);
  React.useEffect(() => {
    if (innerRef.current) {
      const clamped = Math.max(0, Math.min(100, Number(value) || 0));
      innerRef.current.style.width = `${clamped}%`;
    }
  }, [value]);
  return (
    <div
      {...rest}
      ref={(node) => {
        innerRef.current = node;
        if (typeof forwardedRef === "function") forwardedRef(node);
        else if (forwardedRef) forwardedRef.current = node;
      }}
      className={cn(className)}
    />
  );
});

/**
 * A wrapper that applies width/height in pixels via ref.
 * Use when you have a dynamic pixel size prop (e.g. an SVG ring wrapper).
 */
export const SizedBox = React.forwardRef<
  HTMLDivElement,
  DivProps & { width?: number | string; height?: number | string }
>(function SizedBox({ width, height, className, children, ...rest }, forwardedRef) {
  const innerRef = React.useRef<HTMLDivElement | null>(null);
  React.useEffect(() => {
    const el = innerRef.current;
    if (!el) return;
    if (width !== undefined) {
      el.style.width = typeof width === "number" ? `${width}px` : width;
    }
    if (height !== undefined) {
      el.style.height = typeof height === "number" ? `${height}px` : height;
    }
  }, [width, height]);
  return (
    <div
      {...rest}
      ref={(node) => {
        innerRef.current = node;
        if (typeof forwardedRef === "function") forwardedRef(node);
        else if (forwardedRef) forwardedRef.current = node;
      }}
      className={cn(className)}
    >
      {children}
    </div>
  );
});
