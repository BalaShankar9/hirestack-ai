import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Job Board — HireStack AI",
  description: "Find jobs matched to your skills and profile. AI-curated listings with instant match scores so you apply to the right roles.",
};

export default function JobBoardLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
