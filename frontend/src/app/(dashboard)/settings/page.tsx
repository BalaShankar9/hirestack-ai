"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useAuth } from "@/components/providers";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  Settings, Users, CreditCard, Shield, Building2, Plus,
  ArrowRight, Loader2, CheckCircle, Crown,
} from "lucide-react";
import { toast } from "@/hooks/use-toast";

const SETTINGS_LINKS = [
  { href: "/settings/members", label: "Team Members", desc: "Invite and manage your team", icon: Users, color: "text-blue-500 bg-blue-500/10" },
  { href: "/settings/billing", label: "Billing & Plans", desc: "Manage subscription and usage", icon: CreditCard, color: "text-emerald-500 bg-emerald-500/10" },
  { href: "/settings/audit", label: "Audit Log", desc: "Activity history and compliance", icon: Shield, color: "text-violet-500 bg-violet-500/10" },
  { href: "/api-keys", label: "API Keys", desc: "Manage API access tokens", icon: Settings, color: "text-amber-500 bg-amber-500/10" },
];

export default function SettingsPage() {
  const { user, session } = useAuth();
  const [orgs, setOrgs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newOrgName, setNewOrgName] = useState("");
  const [showCreate, setShowCreate] = useState(false);

  useEffect(() => {
    if (session?.access_token) {
      api.setToken(session.access_token);
      api.request("/orgs").then((r: any) => setOrgs(Array.isArray(r) ? r : [])).catch(() => {}).finally(() => setLoading(false));
    }
  }, [session?.access_token]);

  const createOrg = async () => {
    if (!newOrgName.trim()) return;
    setCreating(true);
    try {
      const slug = newOrgName.toLowerCase().replace(/[^a-z0-9-]/g, "-").slice(0, 50);
      const org = await api.request("/orgs", { method: "POST", body: { name: newOrgName, slug } });
      if (org) {
        setOrgs((prev) => [...prev, org]);
        setNewOrgName("");
        setShowCreate(false);
        toast({ title: "Organization created!" });
      }
    } catch (e: any) {
      toast({ title: "Failed", description: e.message });
    }
    setCreating(false);
  };

  const currentOrg = orgs[0];

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-gray-500 to-zinc-600 shadow-glow-sm">
          <Settings className="h-6 w-6 text-white" />
        </div>
        <div>
          <h1 className="text-xl font-bold">Settings</h1>
          <p className="text-sm text-muted-foreground">Organization, team, billing, and security settings</p>
        </div>
      </div>

      {/* Organization Card */}
      <div className="rounded-2xl border bg-card p-6 shadow-soft-sm">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold flex items-center gap-2"><Building2 className="h-4 w-4" /> Organization</h2>
          {currentOrg && (
            <Badge variant="outline" className={cn("text-[10px]",
              currentOrg.tier === "enterprise" ? "border-violet-500/30 text-violet-500" :
              currentOrg.tier === "pro" ? "border-emerald-500/30 text-emerald-500" :
              "border-border"
            )}>
              <Crown className="h-2.5 w-2.5 mr-1" />
              {currentOrg.tier?.charAt(0).toUpperCase() + currentOrg.tier?.slice(1) || "Free"}
            </Badge>
          )}
        </div>

        {loading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading...</div>
        ) : currentOrg ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-4">
              <div><label className="text-2xs text-muted-foreground">Name</label><p className="text-sm font-medium">{currentOrg.name}</p></div>
              <div><label className="text-2xs text-muted-foreground">Slug</label><p className="text-sm font-mono">{currentOrg.slug}</p></div>
              <div><label className="text-2xs text-muted-foreground">Your Role</label><p className="text-sm capitalize">{currentOrg.member_role || "owner"}</p></div>
              <div><label className="text-2xs text-muted-foreground">Plan</label><p className="text-sm capitalize">{currentOrg.tier || "free"}</p></div>
            </div>
          </div>
        ) : (
          <div className="text-center py-6">
            <Building2 className="h-10 w-10 text-muted-foreground/20 mx-auto mb-3" />
            <h3 className="font-semibold text-sm">No Organization</h3>
            <p className="text-xs text-muted-foreground mt-1 max-w-sm mx-auto">Create an organization to unlock team features, billing, and API access.</p>
            {!showCreate ? (
              <Button className="mt-4 rounded-xl gap-2" onClick={() => setShowCreate(true)}><Plus className="h-4 w-4" /> Create Organization</Button>
            ) : (
              <div className="flex gap-2 mt-4 max-w-sm mx-auto">
                <Input placeholder="Organization name" value={newOrgName} onChange={(e) => setNewOrgName(e.target.value)} className="rounded-xl" />
                <Button onClick={createOrg} disabled={creating || !newOrgName.trim()} className="rounded-xl gap-1 shrink-0">
                  {creating ? <Loader2 className="h-3 w-3 animate-spin" /> : <CheckCircle className="h-3 w-3" />} Create
                </Button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Settings Links */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {SETTINGS_LINKS.map((link) => (
          <Link key={link.href} href={link.href} className="rounded-2xl border bg-card p-4 hover:shadow-soft-sm hover:border-primary/20 transition-all group">
            <div className="flex items-center gap-3">
              <div className={cn("flex h-10 w-10 items-center justify-center rounded-xl", link.color)}>
                <link.icon className="h-5 w-5" />
              </div>
              <div className="flex-1">
                <p className="font-semibold text-sm group-hover:text-primary transition-colors">{link.label}</p>
                <p className="text-2xs text-muted-foreground">{link.desc}</p>
              </div>
              <ArrowRight className="h-4 w-4 text-muted-foreground group-hover:text-primary transition-colors" />
            </div>
          </Link>
        ))}
      </div>

      {/* All Organizations */}
      {orgs.length > 1 && (
        <div className="rounded-2xl border bg-card p-5">
          <h2 className="font-semibold text-sm mb-3">All Organizations</h2>
          <div className="space-y-2">
            {orgs.map((org) => (
              <div key={org.id} className="flex items-center justify-between rounded-xl border p-3">
                <div>
                  <p className="text-sm font-medium">{org.name}</p>
                  <p className="text-2xs text-muted-foreground capitalize">{org.member_role || "member"} · {org.tier || "free"}</p>
                </div>
                <Badge variant="outline" className="text-[10px]">{org.slug}</Badge>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
