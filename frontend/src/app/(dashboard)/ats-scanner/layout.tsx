import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "ATS Scanner — HireStack AI",
  description: "Check your resume against any job description for ATS compatibility. Get keyword match scores, format analysis, and concrete fix suggestions.",
};

export default function ATSScannerLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
