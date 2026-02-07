"use client";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

export function KeywordChips({
  keywords,
  isCovered,
  limit = 18,
}: {
  keywords: string[];
  isCovered: (keyword: string) => boolean;
  limit?: number;
}) {
  const list = keywords.slice(0, limit);
  return (
    <div className="flex flex-wrap gap-1.5">
      {list.map((k) => {
        const covered = isCovered(k);
        return (
          <Badge
            key={k}
            variant="secondary"
            className={cn(
              "text-[11px] border",
              covered
                ? "bg-emerald-500/10 text-emerald-700 border-emerald-200"
                : "bg-amber-500/10 text-amber-700 border-amber-200"
            )}
          >
            {k}
            <span className={cn("ml-1", covered ? "opacity-60" : "opacity-80")}>
              {covered ? "✓" : "•"}
            </span>
          </Badge>
        );
      })}
    </div>
  );
}

