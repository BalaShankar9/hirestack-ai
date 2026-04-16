import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Dashboard — HireStack AI",
  description: "Your career command center. Track applications, manage your evidence library, and get AI-powered insights to accelerate your job search.",
};

export default function DashboardPageLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
