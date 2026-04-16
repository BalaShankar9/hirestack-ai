import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Interview Prep — HireStack AI",
  description: "Simulate real interview sessions with AI. Practice common and role-specific questions and get detailed feedback on your answers.",
};

export default function InterviewLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
