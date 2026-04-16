"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X } from "lucide-react";
import type { Achievement } from "@/hooks/use-achievements";
import { cn } from "@/lib/utils";

/* Tiny confetti burst using framer-motion */
function ConfettiBurst() {
  const pieces = Array.from({ length: 12 }, (_, i) => i);
  const colors = ["#f59e0b", "#10b981", "#6366f1", "#ef4444", "#3b82f6", "#ec4899"];
  return (
    <div className="pointer-events-none absolute -top-3 left-1/2 -translate-x-1/2">
      {pieces.map((i) => {
        const angle = (i / pieces.length) * 360;
        const dist = 30 + Math.random() * 20;
        const color = colors[i % colors.length];
        return (
          <motion.div
            key={i}
            className="absolute h-1.5 w-1.5 rounded-sm"
            style={{ backgroundColor: color, originX: "50%", originY: "50%" }}
            initial={{ opacity: 1, x: 0, y: 0, scale: 1, rotate: 0 }}
            animate={{
              opacity: 0,
              x: Math.cos((angle * Math.PI) / 180) * dist,
              y: Math.sin((angle * Math.PI) / 180) * dist - 10,
              scale: 0.3,
              rotate: angle * 2,
            }}
            transition={{ duration: 0.7, ease: "easeOut", delay: 0.1 }}
          />
        );
      })}
    </div>
  );
}

interface AchievementToastProps {
  achievement: Achievement | null;
  onDismiss: () => void;
}

export function AchievementToast({ achievement, onDismiss }: AchievementToastProps) {
  const [showConfetti, setShowConfetti] = useState(false);

  useEffect(() => {
    if (!achievement) { setShowConfetti(false); return; }
    setShowConfetti(true);
    const t = setTimeout(onDismiss, 5500);
    return () => clearTimeout(t);
  }, [achievement, onDismiss]);

  return (
    <AnimatePresence>
      {achievement && (
        <motion.div
          initial={{ opacity: 0, y: 60, scale: 0.9 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 40, scale: 0.9 }}
          transition={{ type: "spring", stiffness: 400, damping: 28 }}
          className={cn(
            "fixed bottom-6 right-6 z-[200] flex items-center gap-3",
            "rounded-2xl border border-amber-500/30 bg-card shadow-2xl px-4 py-3",
            "max-w-xs backdrop-blur-sm",
          )}
        >
          {/* Glow ring */}
          <div className="absolute inset-0 rounded-2xl bg-gradient-to-br from-amber-500/10 to-orange-500/5 pointer-events-none" />

          {/* Confetti burst on mount */}
          {showConfetti && <ConfettiBurst />}

          {/* Badge emoji */}
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-amber-500/10 text-2xl">
            {achievement.emoji}
          </div>

          {/* Text */}
          <div className="flex-1 min-w-0 relative">
            <p className="text-[10px] font-semibold uppercase tracking-widest text-amber-500">
              Achievement Unlocked
            </p>
            <p className="text-sm font-bold truncate">{achievement.title}</p>
            <p className="text-[11px] text-muted-foreground truncate">{achievement.description}</p>
            <p className="text-[10px] text-amber-500/80 font-semibold mt-0.5">+{achievement.xp} XP</p>
          </div>

          {/* Dismiss */}
          <button
            type="button"
            aria-label="Dismiss achievement"
            onClick={onDismiss}
            className="shrink-0 text-muted-foreground hover:text-foreground transition-colors relative"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
