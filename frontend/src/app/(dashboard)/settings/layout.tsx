import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Settings — HireStack AI",
  description: "Manage your account, billing, team members, and API keys.",
};

export default function SettingsLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
