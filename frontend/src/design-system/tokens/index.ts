/**
 * HireStack Design System — Token Exports
 *
 * Centralized exports for all design tokens.
 * Import from here to access colors, typography, spacing, and motion.
 */

export * from "./colors";
export * from "./typography";
export * from "./spacing";
export * from "./motion";

// Convenience re-exports for common use cases
export { baseColors, semanticColors, lightModeVars, darkModeVars } from "./colors";
export { typeScale, textStyles, fontFamilies, fontWeights } from "./typography";
export { space, componentSpacing, radii, shadows } from "./spacing";
export { durations, easings, transitions, interactions } from "./motion";
