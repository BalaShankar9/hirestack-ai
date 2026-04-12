"use client";

import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import { useAuth } from "@/components/providers";
import api from "@/lib/api";

interface Org {
  id: string;
  name: string;
  slug: string;
  tier: string;
  logo_url?: string;
  member_role?: string;
  settings?: Record<string, any>;
}

interface OrgContextType {
  currentOrg: Org | null;
  orgs: Org[];
  loading: boolean;
  switchOrg: (orgId: string) => void;
  refreshOrgs: () => Promise<void>;
  createOrg: (name: string) => Promise<Org | null>;
}

const OrgContext = createContext<OrgContextType>({
  currentOrg: null,
  orgs: [],
  loading: true,
  switchOrg: () => {},
  refreshOrgs: async () => {},
  createOrg: async () => null,
});

export function useOrg() {
  return useContext(OrgContext);
}

export function OrgProvider({ children }: { children: React.ReactNode }) {
  const { user, session } = useAuth();
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [currentOrg, setCurrentOrg] = useState<Org | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshOrgs = useCallback(async () => {
    const token = session?.access_token;
    if (!token) { setLoading(false); return; }
    api.setToken(token);
    try {
      const result = await api.request("/orgs");
      const orgList = Array.isArray(result) ? result : [];
      setOrgs(orgList);
      // Auto-select first org if none selected
      if (!currentOrg && orgList.length > 0) {
        const saved = typeof window !== "undefined" ? localStorage.getItem("hirestack_org_id") : null;
        const match = saved ? orgList.find((o: Org) => o.id === saved) : null;
        setCurrentOrg(match || orgList[0]);
      }
    } catch (err) {
      console.error("refreshOrgs failed:", err);
      setOrgs([]);
    }
    setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.access_token]);

  useEffect(() => { refreshOrgs(); }, [refreshOrgs]);

  const switchOrg = (orgId: string) => {
    const org = orgs.find((o) => o.id === orgId);
    if (org) {
      setCurrentOrg(org);
      if (typeof window !== "undefined") localStorage.setItem("hirestack_org_id", orgId);
    }
  };

  const createOrg = async (name: string): Promise<Org | null> => {
    try {
      const slug = name.toLowerCase().replace(/[^a-z0-9-]/g, "-").replace(/-+/g, "-").slice(0, 50);
      const org = await api.request("/orgs", { method: "POST", body: { name, slug } });
      if (org?.id) {
        await refreshOrgs();
        setCurrentOrg(org);
        return org;
      }
    } catch (err) {
      console.error("createOrg failed:", err);
    }
    return null;
  };

  return (
    <OrgContext.Provider value={{ currentOrg, orgs, loading, switchOrg, refreshOrgs, createOrg }}>
      {children}
    </OrgContext.Provider>
  );
}
