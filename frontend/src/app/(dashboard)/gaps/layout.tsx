import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Gap Report — HireStack AI",
  description: "See exactly what you're missing vs. the ideal candidate for your target role. Get actionable steps to close every gap before you apply.",
};

export default function GapsLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
