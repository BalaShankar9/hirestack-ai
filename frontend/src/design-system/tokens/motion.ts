/**
 * HireStack Design System — Motion Tokens
 *
 * Consistent animation timing and easing across the application.
 * Supports reduced motion preferences.
 */

/**
 * Duration tokens in seconds.
 */
export const durations = {
  instant: 0.05,
  fast: 0.15,
  normal: 0.3,
  slow: 0.5,
  slower: 0.7,
  slowest: 1.0,
} as const;

/**
 * Easing functions.
 */
export const easings = {
  linear: "linear",
  ease: "ease",
  easeIn: "ease-in",
  easeOut: "ease-out",
  easeInOut: "ease-in-out",

  // Custom easings for more natural feel
  easeOutExpo: "cubic-bezier(0.16, 1, 0.3, 1)",
  easeInExpo: "cubic-bezier(0.7, 0, 0.84, 0)",
  easeOutBack: "cubic-bezier(0.34, 1.56, 0.64, 1)",
  easeSpring: "cubic-bezier(0.175, 0.885, 0.32, 1.275)",

  // Framer Motion spring configs
  springGentle: { type: "spring" as const, stiffness: 300, damping: 30 },
  springBouncy: { type: "spring" as const, stiffness: 500, damping: 25 },
  springStiff: { type: "spring" as const, stiffness: 1000, damping: 40 },
  springSoft: { type: "spring" as const, stiffness: 150, damping: 20 },
} as const;

/**
 * Animation presets for common transitions.
 * Use these instead of ad-hoc animations for consistency.
 */
export const transitions = {
  fade: {
    initial: { opacity: 0 },
    animate: { opacity: 1 },
    exit: { opacity: 0 },
    transition: { duration: durations.normal, ease: easings.easeOut },
  },

  fadeIn: {
    initial: { opacity: 0, y: 10 },
    animate: { opacity: 1, y: 0 },
    exit: { opacity: 0, y: -10 },
    transition: { duration: durations.normal, ease: easings.easeOutExpo },
  },

  fadeInUp: {
    initial: { opacity: 0, y: 20 },
    animate: { opacity: 1, y: 0 },
    exit: { opacity: 0, y: -20 },
    transition: { duration: durations.slow, ease: easings.easeOutExpo },
  },

  fadeInScale: {
    initial: { opacity: 0, scale: 0.95 },
    animate: { opacity: 1, scale: 1 },
    exit: { opacity: 0, scale: 0.95 },
    transition: { duration: durations.normal, ease: easings.easeOutExpo },
  },

  slideIn: {
    initial: { x: -20, opacity: 0 },
    animate: { x: 0, opacity: 1 },
    exit: { x: 20, opacity: 0 },
    transition: { duration: durations.normal, ease: easings.easeOutExpo },
  },

  slideUp: {
    initial: { y: 40, opacity: 0 },
    animate: { y: 0, opacity: 1 },
    exit: { y: -20, opacity: 0 },
    transition: { duration: durations.slow, ease: easings.easeOutExpo },
  },

  scale: {
    initial: { scale: 0.9, opacity: 0 },
    animate: { scale: 1, opacity: 1 },
    exit: { scale: 0.9, opacity: 0 },
    transition: { duration: durations.fast, ease: easings.easeSpring },
  },

  pop: {
    initial: { scale: 0.8, opacity: 0 },
    animate: { scale: 1, opacity: 1 },
    exit: { scale: 0.8, opacity: 0 },
    transition: easings.springBouncy,
  },

  stagger: {
    container: {
      animate: {
        transition: {
          staggerChildren: 0.05,
          delayChildren: 0.1,
        },
      },
    },
    item: {
      initial: { opacity: 0, y: 10 },
      animate: { opacity: 1, y: 0 },
      transition: { duration: durations.fast, ease: easings.easeOut },
    },
  },

  list: {
    container: {
      animate: {
        transition: {
          staggerChildren: 0.03,
        },
      },
    },
    item: {
      initial: { opacity: 0, x: -10 },
      animate: { opacity: 1, x: 0 },
      exit: { opacity: 0, x: 10 },
      transition: { duration: durations.fast },
    },
  },

  modal: {
    overlay: {
      initial: { opacity: 0 },
      animate: { opacity: 1 },
      exit: { opacity: 0 },
      transition: { duration: durations.fast },
    },
    content: {
      initial: { opacity: 0, scale: 0.95, y: 10 },
      animate: { opacity: 1, scale: 1, y: 0 },
      exit: { opacity: 0, scale: 0.95, y: 10 },
      transition: { duration: durations.normal, ease: easings.easeOutExpo },
    },
  },

  dropdown: {
    initial: { opacity: 0, y: -4, scale: 0.98 },
    animate: { opacity: 1, y: 0, scale: 1 },
    exit: { opacity: 0, y: -4, scale: 0.98 },
    transition: { duration: durations.fast, ease: easings.easeOutExpo },
  },

  tooltip: {
    initial: { opacity: 0, scale: 0.95 },
    animate: { opacity: 1, scale: 1 },
    exit: { opacity: 0, scale: 0.95 },
    transition: { duration: durations.instant },
  },

  skeleton: {
    animate: {
      opacity: [0.5, 1, 0.5],
      transition: {
        duration: 1.5,
        repeat: Infinity,
        ease: "linear",
      },
    },
  },

  pulse: {
    animate: {
      scale: [1, 1.05, 1],
      transition: {
        duration: 2,
        repeat: Infinity,
        ease: "easeInOut",
      },
    },
  },
} as const;

/**
 * Hover/tap micro-interactions.
 */
export const interactions = {
  buttonTap: { scale: 0.97, transition: { duration: durations.instant } },
  buttonHover: { scale: 1.02, transition: { duration: durations.fast } },
  cardHover: { y: -4, transition: { duration: durations.normal, ease: easings.springGentle } },
  linkHover: { x: 2, transition: { duration: durations.fast } },
  iconHover: { scale: 1.15, transition: { duration: durations.fast } },
} as const;
