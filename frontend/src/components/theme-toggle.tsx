"use client";

import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { Moon, Sun, Monitor } from "lucide-react";

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return <div className="h-9 w-9" />;
  }

  const next = theme === "dark" ? "light" : theme === "light" ? "system" : "dark";
  const Icon = theme === "dark" ? Moon : theme === "light" ? Sun : Monitor;
  const label =
    theme === "dark" ? "Dark mode" : theme === "light" ? "Light mode" : "System";

  return (
    <button
      onClick={() => setTheme(next)}
      className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-border/50 text-muted-foreground transition-all duration-200 hover:bg-muted/60 hover:text-foreground hover:border-border active:scale-90"
      title={`${label} — click to switch`}
      aria-label={`Current: ${label}. Click to switch.`}
    >
      <Icon className="h-4 w-4 transition-transform duration-300" />
    </button>
  );
}
