"use client";

import { usePathname } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { type ReactNode, useEffect, useState } from "react";

/**
 * Wraps page content with a subtle enter/exit animation.
 *
 * Safety: A CSS fallback ensures content becomes visible even if
 * framer-motion fails to trigger (e.g. JS hydration issue, bundle
 * race condition). After 400ms the wrapper forces opacity:1 via CSS
 * so the page is never permanently invisible.
 */
export function PageTransition({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [safetyVisible, setSafetyVisible] = useState(false);

  // CSS safety net: force content visible after 400ms regardless of animation
  useEffect(() => {
    const t = setTimeout(() => setSafetyVisible(true), 400);
    return () => clearTimeout(t);
  }, [pathname]);

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={pathname}
        initial={{ opacity: 0, y: 8, filter: "blur(4px)" }}
        animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
        exit={{ opacity: 0, y: -4, filter: "blur(2px)" }}
        transition={{ duration: 0.2, ease: [0.22, 0.68, 0, 1] }}
        style={safetyVisible ? { opacity: 1, transform: "none", filter: "none" } : undefined}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
}
