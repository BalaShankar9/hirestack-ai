import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Evidence Library — HireStack AI",
  description: "Build your proof library. Add certifications, projects, and quantified achievements — the AI matches them to every application automatically.",
};

export default function EvidenceLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
