import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Daily Learn — HireStack AI",
  description: "Close skill gaps with daily AI-curated learning modules. Earn streaks and XP while building the skills your target roles require.",
};

export default function LearningLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
