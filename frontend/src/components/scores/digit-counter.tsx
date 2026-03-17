"use client";

import { memo, useEffect, useState } from "react";
import { cn } from "@/lib/utils";

interface DigitCounterProps {
  value: number;
  suffix?: string;
  className?: string;
  duration?: number;
}

export const DigitCounter = memo(function DigitCounter({
  value,
  suffix = "",
  className,
  duration = 600,
}: DigitCounterProps) {
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    const start = display;
    const diff = value - start;
    if (diff === 0) return;

    const startTime = performance.now();
    let raf: number;

    function step(now: number) {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(Math.round(start + diff * eased));
      if (progress < 1) raf = requestAnimationFrame(step);
    }

    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value, duration]);

  return (
    <span className={cn("font-mono font-semibold tabular-nums", className)}>
      {display}{suffix}
    </span>
  );
});
