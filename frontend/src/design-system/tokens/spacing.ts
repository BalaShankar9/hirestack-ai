/**
 * HireStack Design System — Spacing Tokens
 *
 * 4px base grid with semantic naming.
 * Supports component-specific spacing needs.
 */

/**
 * Base spacing scale (multiples of 4px).
 */
export const space = {
  0: "0px",
  0.5: "2px",
  1: "4px",
  2: "8px",
  3: "12px",
  4: "16px",
  5: "20px",
  6: "24px",
  8: "32px",
  10: "40px",
  12: "48px",
  16: "64px",
  20: "80px",
  24: "96px",
  32: "128px",
  40: "160px",
  48: "192px",
} as const;

/**
 * Semantic spacing tokens for common use cases.
 */
export const componentSpacing = {
  // Gap within components
  gap: {
    xs: space[1],   // 4px — tight spacing (icon + label)
    sm: space[2],   // 8px — compact spacing
    md: space[4],   // 16px — standard spacing
    lg: space[6],   // 24px — relaxed spacing
    xl: space[8],   // 32px — generous spacing
  },

  // Padding within containers
  padding: {
    xs: space[2],   // 8px — small buttons, badges
    sm: space[3],   // 12px — compact cards
    md: space[4],   // 16px — standard cards
    lg: space[6],   // 24px — large cards, modals
    xl: space[8],   // 32px — page sections
  },

  // Margin between components
  margin: {
    xs: space[2],   // 8px — related elements
    sm: space[4],   // 16px — grouped components
    md: space[6],   // 24px — section breaks
    lg: space[8],   // 32px — major sections
    xl: space[12],  // 48px — page sections
  },

  // Form spacing
  form: {
    labelGap: "6px",  // 6px — label to input
    fieldGap: space[4],    // 16px — field to field
    sectionGap: space[6],   // 24px — form sections
    groupGap: space[3],    // 12px — checkbox/radio groups
  },

  // Card spacing
  card: {
    padding: space[6],
    headerPadding: space[4],
    footerPadding: space[4],
    contentGap: space[4],
    sectionGap: space[4],
  },

  // Modal spacing
  modal: {
    padding: space[6],
    headerPadding: space[5],
    footerPadding: space[5],
    contentGap: space[5],
    maxWidth: "560px",
    wideMaxWidth: "720px",
  },

  // Page layout
  page: {
    maxWidth: "1440px",
    paddingX: {
      mobile: space[4],
      tablet: space[6],
      desktop: space[8],
    },
    paddingY: {
      mobile: space[6],
      tablet: space[8],
      desktop: space[12],
    },
    sectionGap: space[16],
  },
} as const;

/**
 * Border radius scale.
 */
export const radii = {
  none: "0px",
  xs: "2px",
  sm: "4px",
  md: "8px",
  lg: "12px",
  xl: "16px",
  "2xl": "24px",
  full: "9999px",
} as const;

/**
 * Shadow scale.
 */
export const shadows = {
  xs: "0 1px 2px 0 rgb(0 0 0 / 0.05)",
  sm: "0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)",
  md: "0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)",
  lg: "0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)",
  xl: "0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1)",
  "2xl": "0 25px 50px -12px rgb(0 0 0 / 0.25)",
  inner: "inset 0 2px 4px 0 rgb(0 0 0 / 0.05)",
  focus: "0 0 0 3px var(--color-ring)",
} as const;
