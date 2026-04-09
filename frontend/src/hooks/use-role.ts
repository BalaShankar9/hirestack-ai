"use client";

import { useAuth } from "@/components/providers";
import { useOrg } from "@/contexts/org-context";

export type GlobalRole = "admin" | "enterprise" | "user" | null;
export type OrgRole = "owner" | "admin" | "recruiter" | "member" | "viewer" | null;

/**
 * Unified role hook that exposes both global (Supabase user_metadata.role)
 * and org-level (member_role) roles, plus permission helpers.
 */
export function useRole() {
  const { user } = useAuth();
  const { currentOrg } = useOrg();

  const globalRole: GlobalRole = (user?.user_metadata?.role as GlobalRole) ?? "user";
  const orgRole: OrgRole = (currentOrg?.member_role as OrgRole) ?? null;

  const isGlobalAdmin = globalRole === "admin";
  const isEnterprise = globalRole === "enterprise" || isGlobalAdmin;

  // Org-level permission checks
  const isOrgOwner = orgRole === "owner";
  const isOrgAdmin = orgRole === "admin" || isOrgOwner;
  const isOrgRecruiter = orgRole === "recruiter" || isOrgAdmin;
  const isOrgMember = orgRole === "member" || isOrgRecruiter;

  /** Check if user can access a given admin feature */
  function canAccess(feature: "pipeline" | "settings" | "members" | "billing" | "audit" | "api_keys"): boolean {
    // TESTING MODE: all features unlocked — re-enable for production
    return true;
  }

  return {
    globalRole,
    orgRole,
    isGlobalAdmin,
    isEnterprise,
    isOrgOwner,
    isOrgAdmin,
    isOrgRecruiter,
    isOrgMember,
    canAccess,
  };
}
