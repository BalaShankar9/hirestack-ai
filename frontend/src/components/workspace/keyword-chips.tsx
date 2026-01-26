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
                ? "bg-green-50 text-green-800 border-green-200"
                : "bg-amber-50 text-amber-900 border-amber-200"
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

