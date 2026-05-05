/**
 * HireStack Design System — Color Tokens
 *
 * Semantic naming over literal colors.
 * Supports light/dark mode via CSS variables.
 */

export const baseColors = {
  // Brand colors
  brand: {
    50: "#eff6ff",
    100: "#dbeafe",
    200: "#bfdbfe",
    300: "#93c5fd",
    400: "#60a5fa",
    500: "#3b82f6", // Primary brand
    600: "#2563eb",
    700: "#1d4ed8",
    800: "#1e40af",
    900: "#1e3a8a",
    950: "#172554",
  },

  // Neutral scale
  gray: {
    0: "#ffffff",
    50: "#f9fafb",
    100: "#f3f4f6",
    200: "#e5e7eb",
    300: "#d1d5db",
    400: "#9ca3af",
    500: "#6b7280",
    600: "#4b5563",
    700: "#374151",
    800: "#1f2937",
    900: "#111827",
    950: "#030712",
  },

  // Semantic colors
  success: {
    50: "#f0fdf4",
    100: "#dcfce7",
    200: "#bbf7d0",
    300: "#86efac",
    400: "#4ade80",
    500: "#22c55e",
    600: "#16a34a",
    700: "#15803d",
    800: "#166534",
    900: "#14532d",
  },

  warning: {
    50: "#fffbeb",
    100: "#fef3c7",
    200: "#fde68a",
    300: "#fcd34d",
    400: "#fbbf24",
    500: "#f59e0b",
    600: "#d97706",
    700: "#b45309",
    800: "#92400e",
    900: "#78350f",
  },

  danger: {
    50: "#fef2f2",
    100: "#fee2e2",
    200: "#fecaca",
    300: "#fca5a5",
    400: "#f87171",
    500: "#ef4444",
    600: "#dc2626",
    700: "#b91c1c",
    800: "#991b1b",
    900: "#7f1d1d",
    950: "#450a0a",
  },

  info: {
    50: "#f0f9ff",
    100: "#e0f2fe",
    200: "#bae6fd",
    300: "#7dd3fc",
    400: "#38bdf8",
    500: "#0ea5e9",
    600: "#0284c7",
    700: "#0369a1",
    800: "#075985",
    900: "#0c4a6e",
  },
} as const;

/**
 * Semantic color tokens — these are what components use.
 * Maps to CSS variables that change in light/dark mode.
 */
export const semanticColors = {
  // Backgrounds
  background: {
    DEFAULT: "var(--color-background)",
    subtle: "var(--color-background-subtle)",
    muted: "var(--color-background-muted)",
    elevated: "var(--color-background-elevated)",
    overlay: "var(--color-background-overlay)",
  },

  // Text
  foreground: {
    DEFAULT: "var(--color-foreground)",
    muted: "var(--color-foreground-muted)",
    subtle: "var(--color-foreground-subtle)",
    inverted: "var(--color-foreground-inverted)",
  },

  // Brand
  primary: {
    DEFAULT: "var(--color-primary)",
    hover: "var(--color-primary-hover)",
    active: "var(--color-primary-active)",
    subtle: "var(--color-primary-subtle)",
    foreground: "var(--color-primary-foreground)",
  },

  // Secondary
  secondary: {
    DEFAULT: "var(--color-secondary)",
    hover: "var(--color-secondary-hover)",
    active: "var(--color-secondary-active)",
    foreground: "var(--color-secondary-foreground)",
  },

  // Destructive
  destructive: {
    DEFAULT: "var(--color-destructive)",
    hover: "var(--color-destructive-hover)",
    subtle: "var(--color-destructive-subtle)",
    foreground: "var(--color-destructive-foreground)",
  },

  // States
  muted: {
    DEFAULT: "var(--color-muted)",
    foreground: "var(--color-muted-foreground)",
  },

  accent: {
    DEFAULT: "var(--color-accent)",
    hover: "var(--color-accent-hover)",
    foreground: "var(--color-accent-foreground)",
  },

  // Borders
  border: {
    DEFAULT: "var(--color-border)",
    hover: "var(--color-border-hover)",
    focus: "var(--color-border-focus)",
  },

  // Focus ring
  ring: {
    DEFAULT: "var(--color-ring)",
    offset: "var(--color-ring-offset)",
  },
} as const;

/**
 * CSS variable definitions for light mode.
 */
export const lightModeVars = {
  "--color-background": baseColors.gray[0],
  "--color-background-subtle": baseColors.gray[50],
  "--color-background-muted": baseColors.gray[100],
  "--color-background-elevated": baseColors.gray[0],
  "--color-background-overlay": "rgba(0, 0, 0, 0.4)",

  "--color-foreground": baseColors.gray[900],
  "--color-foreground-muted": baseColors.gray[600],
  "--color-foreground-subtle": baseColors.gray[400],
  "--color-foreground-inverted": baseColors.gray[0],

  "--color-primary": baseColors.brand[600],
  "--color-primary-hover": baseColors.brand[700],
  "--color-primary-active": baseColors.brand[800],
  "--color-primary-subtle": baseColors.brand[50],
  "--color-primary-foreground": baseColors.gray[0],

  "--color-secondary": baseColors.gray[200],
  "--color-secondary-hover": baseColors.gray[300],
  "--color-secondary-active": baseColors.gray[400],
  "--color-secondary-foreground": baseColors.gray[900],

  "--color-destructive": baseColors.danger[600],
  "--color-destructive-hover": baseColors.danger[700],
  "--color-destructive-subtle": baseColors.danger[50],
  "--color-destructive-foreground": baseColors.gray[0],

  "--color-muted": baseColors.gray[100],
  "--color-muted-foreground": baseColors.gray[600],

  "--color-accent": baseColors.gray[100],
  "--color-accent-hover": baseColors.gray[200],
  "--color-accent-foreground": baseColors.gray[900],

  "--color-border": baseColors.gray[200],
  "--color-border-hover": baseColors.gray[300],
  "--color-border-focus": baseColors.brand[500],

  "--color-ring": baseColors.brand[500],
  "--color-ring-offset": baseColors.gray[0],
} as const;

/**
 * CSS variable definitions for dark mode.
 */
export const darkModeVars = {
  "--color-background": baseColors.gray[950],
  "--color-background-subtle": baseColors.gray[900],
  "--color-background-muted": baseColors.gray[800],
  "--color-background-elevated": baseColors.gray[900],
  "--color-background-overlay": "rgba(0, 0, 0, 0.7)",

  "--color-foreground": baseColors.gray[0],
  "--color-foreground-muted": baseColors.gray[400],
  "--color-foreground-subtle": baseColors.gray[600],
  "--color-foreground-inverted": baseColors.gray[950],

  "--color-primary": baseColors.brand[500],
  "--color-primary-hover": baseColors.brand[400],
  "--color-primary-active": baseColors.brand[300],
  "--color-primary-subtle": baseColors.brand[950],
  "--color-primary-foreground": baseColors.gray[0],

  "--color-secondary": baseColors.gray[800],
  "--color-secondary-hover": baseColors.gray[700],
  "--color-secondary-active": baseColors.gray[600],
  "--color-secondary-foreground": baseColors.gray[0],

  "--color-destructive": baseColors.danger[500],
  "--color-destructive-hover": baseColors.danger[400],
  "--color-destructive-subtle": baseColors.danger[950],
  "--color-destructive-foreground": baseColors.gray[0],

  "--color-muted": baseColors.gray[800],
  "--color-muted-foreground": baseColors.gray[400],

  "--color-accent": baseColors.gray[800],
  "--color-accent-hover": baseColors.gray[700],
  "--color-accent-foreground": baseColors.gray[0],

  "--color-border": baseColors.gray[800],
  "--color-border-hover": baseColors.gray[700],
  "--color-border-focus": baseColors.brand[400],

  "--color-ring": baseColors.brand[500],
  "--color-ring-offset": baseColors.gray[950],
} as const;

// Type exports
type BaseColors = typeof baseColors;
type SemanticColors = typeof semanticColors;
export type { BaseColors, SemanticColors };
