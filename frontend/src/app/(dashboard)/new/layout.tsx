import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "New Application — HireStack AI",
  description: "Paste a job description, upload your resume, and let AI agents build a complete, ATS-optimized application package in under 5 minutes.",
};

export default function NewApplicationLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
