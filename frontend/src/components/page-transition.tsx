"use client";

import { usePathname } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { type ReactNode } from "react";

/**
 * Wraps page content with a fast enter animation.
 *
 * Intentionally NO `mode="wait"` and NO exit animation — those force the
 * browser to hold the old page on screen while the new one is waiting to
 * mount, which feels like multi-second click latency on mobile. The new
 * route just renders immediately; only a ~120ms fade-in is applied.
 */
export function PageTransition({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <AnimatePresence initial={false}>
      <motion.div
        key={pathname}
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.12, ease: "easeOut" }}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
}
