import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Career Analytics — HireStack AI",
  description: "Track your application progress, win rates, and career momentum over time. Data-driven insights to sharpen your job search strategy.",
};

export default function CareerAnalyticsLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
