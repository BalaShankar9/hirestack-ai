import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Salary Coach — HireStack AI",
  description: "Understand your market value. Get AI-powered salary benchmarks, negotiation strategies, and compensation insights for your target role.",
};

export default function SalaryLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
