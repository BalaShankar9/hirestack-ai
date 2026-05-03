/**
 * HireStack Design System — Typography Tokens
 *
 * Fluid type scale using clamp() for responsive sizing.
 * Optimized for readability at all breakpoints.
 */

export const fontFamilies = {
  sans: 'var(--font-sans), system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  mono: 'var(--font-mono), "SF Mono", "Fira Code", Consolas, monospace',
  serif: 'var(--font-serif), Georgia, "Times New Roman", serif',
} as const;

export const fontWeights = {
  light: 300,
  normal: 400,
  medium: 500,
  semibold: 600,
  bold: 700,
} as const;

export const lineHeights = {
  none: 1,
  tight: 1.2,
  snug: 1.375,
  normal: 1.5,
  relaxed: 1.625,
  loose: 2,
} as const;

export const letterSpacing = {
  tighter: "-0.05em",
  tight: "-0.025em",
  normal: "0em",
  wide: "0.025em",
  wider: "0.05em",
  widest: "0.1em",
} as const;

/**
 * Fluid type scale using CSS clamp().
 * Min size at 375px viewport, max at 1400px.
 */
export const typeScale = {
  display: {
    size: "clamp(2.5rem, 5vw + 1rem, 4rem)",
    lineHeight: lineHeights.tight,
    weight: fontWeights.bold,
    letterSpacing: letterSpacing.tight,
  },
  title: {
    size: "clamp(2rem, 3vw + 0.5rem, 3rem)",
    lineHeight: lineHeights.tight,
    weight: fontWeights.bold,
    letterSpacing: letterSpacing.tight,
  },
  heading: {
    size: "clamp(1.5rem, 2vw + 0.25rem, 2.25rem)",
    lineHeight: lineHeights.snug,
    weight: fontWeights.semibold,
    letterSpacing: letterSpacing.normal,
  },
  subheading: {
    size: "clamp(1.25rem, 1.5vw + 0.25rem, 1.75rem)",
    lineHeight: lineHeights.snug,
    weight: fontWeights.semibold,
    letterSpacing: letterSpacing.normal,
  },
  bodyLarge: {
    size: "clamp(1.125rem, 1vw + 0.5rem, 1.25rem)",
    lineHeight: lineHeights.relaxed,
    weight: fontWeights.normal,
    letterSpacing: letterSpacing.normal,
  },
  body: {
    size: "clamp(0.875rem, 0.5vw + 0.75rem, 1rem)",
    lineHeight: lineHeights.relaxed,
    weight: fontWeights.normal,
    letterSpacing: letterSpacing.normal,
  },
  bodySmall: {
    size: "clamp(0.75rem, 0.5vw + 0.5rem, 0.875rem)",
    lineHeight: lineHeights.normal,
    weight: fontWeights.normal,
    letterSpacing: letterSpacing.normal,
  },
  caption: {
    size: "0.75rem",
    lineHeight: lineHeights.normal,
    weight: fontWeights.medium,
    letterSpacing: letterSpacing.wide,
  },
  label: {
    size: "0.75rem",
    lineHeight: lineHeights.normal,
    weight: fontWeights.semibold,
    letterSpacing: letterSpacing.wide,
  },
  code: {
    size: "0.875rem",
    lineHeight: lineHeights.normal,
    weight: fontWeights.normal,
    letterSpacing: letterSpacing.normal,
  },
} as const;

/**
 * Text styles combining size, weight, line-height, and letter-spacing.
 * Use these for consistent typography across components.
 */
export const textStyles = {
  display: {
    fontSize: typeScale.display.size,
    fontWeight: typeScale.display.weight,
    lineHeight: typeScale.display.lineHeight,
    letterSpacing: typeScale.display.letterSpacing,
  },
  title: {
    fontSize: typeScale.title.size,
    fontWeight: typeScale.title.weight,
    lineHeight: typeScale.title.lineHeight,
    letterSpacing: typeScale.title.letterSpacing,
  },
  heading: {
    fontSize: typeScale.heading.size,
    fontWeight: typeScale.heading.weight,
    lineHeight: typeScale.heading.lineHeight,
    letterSpacing: typeScale.heading.letterSpacing,
  },
  subheading: {
    fontSize: typeScale.subheading.size,
    fontWeight: typeScale.subheading.weight,
    lineHeight: typeScale.subheading.lineHeight,
    letterSpacing: typeScale.subheading.letterSpacing,
  },
  bodyLarge: {
    fontSize: typeScale.bodyLarge.size,
    fontWeight: typeScale.bodyLarge.weight,
    lineHeight: typeScale.bodyLarge.lineHeight,
    letterSpacing: typeScale.bodyLarge.letterSpacing,
  },
  body: {
    fontSize: typeScale.body.size,
    fontWeight: typeScale.body.weight,
    lineHeight: typeScale.body.lineHeight,
    letterSpacing: typeScale.body.letterSpacing,
  },
  bodySmall: {
    fontSize: typeScale.bodySmall.size,
    fontWeight: typeScale.bodySmall.weight,
    lineHeight: typeScale.bodySmall.lineHeight,
    letterSpacing: typeScale.bodySmall.letterSpacing,
  },
  caption: {
    fontSize: typeScale.caption.size,
    fontWeight: typeScale.caption.weight,
    lineHeight: typeScale.caption.lineHeight,
    letterSpacing: typeScale.caption.letterSpacing,
    textTransform: "uppercase" as const,
  },
  label: {
    fontSize: typeScale.label.size,
    fontWeight: typeScale.label.weight,
    lineHeight: typeScale.label.lineHeight,
    letterSpacing: typeScale.label.letterSpacing,
  },
} as const;
