import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Profile — HireStack AI",
  description: "Build your career identity. Complete your profile so HireStack AI can generate evidence-backed applications tailored to every role.",
};

export default function NexusLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
