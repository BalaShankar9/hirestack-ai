"use client";

import { ReactNode } from "react";
import { useRole } from "@/hooks/use-role";
import { LockedState } from "@/components/ui/locked-state";

interface RoleGateProps {
  /** Which admin feature is being guarded */
  feature: "pipeline" | "settings" | "members" | "billing" | "audit" | "api_keys";
  /** Page title shown in locked state */
  title: string;
  /** Description shown in locked state */
  description?: string;
  /** Feature list shown in locked state */
  features?: string[];
  children: ReactNode;
}

/**
 * Wraps an admin page and shows a locked state if the user's role
 * doesn't have access to the given feature.
 */
export function RoleGate({ feature, title, description, features, children }: RoleGateProps) {
  const { canAccess } = useRole();

  if (!canAccess(feature)) {
    return (
      <div className="max-w-2xl mx-auto py-12">
        <LockedState
          title={title}
          description={description || "You don't have permission to access this page. Contact your organization admin for access."}
          features={features || []}
          actionLabel="Go to Overview"
          actionHref="/dashboard"
        />
      </div>
    );
  }

  return <>{children}</>;
}
