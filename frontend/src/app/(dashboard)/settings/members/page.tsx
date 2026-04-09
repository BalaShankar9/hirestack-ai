"use client";

import React, { useState, useEffect } from "react";
import { useAuth } from "@/components/providers";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { Users, Plus, Loader2, Mail, Shield, Crown, UserX, ArrowLeft } from "lucide-react";
import { toast } from "@/hooks/use-toast";
import Link from "next/link";
import { RoleGate } from "@/components/role-gate";

const ROLE_COLORS: Record<string, string> = {
  owner: "bg-violet-500/10 text-violet-500 border-violet-500/20",
  admin: "bg-blue-500/10 text-blue-500 border-blue-500/20",
  recruiter: "bg-emerald-500/10 text-emerald-500 border-emerald-500/20",
  member: "bg-gray-500/10 text-gray-500 border-gray-500/20",
  viewer: "bg-amber-500/10 text-amber-500 border-amber-500/20",
};

export default function MembersPage() {
  const { session } = useAuth();
  const [org, setOrg] = useState<any>(null);
  const [members, setMembers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("member");
  const [inviting, setInviting] = useState(false);

  useEffect(() => {
    if (!session?.access_token) return;
    api.setToken(session.access_token);
    api.request("/orgs").then(async (orgs: any[]) => {
      if (orgs?.length > 0) {
        setOrg(orgs[0]);
        const m = await api.request(`/orgs/${orgs[0].id}/members`);
        setMembers(Array.isArray(m) ? m : []);
      }
    }).catch(() => { toast({ title: "Error", description: "Failed to load team members" }); }).finally(() => setLoading(false));
  }, [session?.access_token]);

  const invite = async () => {
    if (!org || !inviteEmail.trim()) return;
    setInviting(true);
    try {
      await api.request(`/orgs/${org.id}/members`, { method: "POST", body: { email: inviteEmail, role: inviteRole } });
      toast({ title: "Invitation sent!", description: `${inviteEmail} invited as ${inviteRole}` });
      setInviteEmail("");
      const m = await api.request(`/orgs/${org.id}/members`);
      setMembers(Array.isArray(m) ? m : []);
    } catch (e: any) { toast({ title: "Failed", description: e.message }); }
    setInviting(false);
  };

  const changeRole = async (userId: string, role: string) => {
    if (!org) return;
    try {
      await api.request(`/orgs/${org.id}/members/${userId}`, { method: "PUT", body: { role } });
      setMembers((prev) => prev.map((m) => m.user_id === userId ? { ...m, role } : m));
      toast({ title: "Role updated" });
    } catch (e: any) { toast({ title: "Failed", description: e.message }); }
  };

  const removeMember = async (userId: string) => {
    if (!org || !confirm("Remove this member?")) return;
    try {
      await api.request(`/orgs/${org.id}/members/${userId}`, { method: "DELETE" });
      setMembers((prev) => prev.filter((m) => m.user_id !== userId));
      toast({ title: "Member removed" });
    } catch (e: any) { toast({ title: "Failed", description: e.message }); }
  };

  return (
    <RoleGate feature="members" title="Team Members" features={["Invite & manage team members", "Assign roles & permissions", "Organization management"]}>
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <Link href="/settings" className="text-muted-foreground hover:text-foreground"><ArrowLeft className="h-5 w-5" /></Link>
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-500/10"><Users className="h-5 w-5 text-blue-500" /></div>
        <div>
          <h1 className="text-lg font-bold">Team Members</h1>
          <p className="text-xs text-muted-foreground">{org?.name || "Organization"} · {members.length} members</p>
        </div>
      </div>

      {/* Invite form */}
      <div className="rounded-2xl border bg-card p-5 shadow-soft-sm">
        <h2 className="font-semibold text-sm mb-3">Invite Team Member</h2>
        <div className="flex gap-2">
          <Input placeholder="email@company.com" value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} className="rounded-xl flex-1" />
          <Select value={inviteRole} onValueChange={setInviteRole}>
            <SelectTrigger className="w-32 rounded-xl"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="admin">Admin</SelectItem>
              <SelectItem value="recruiter">Recruiter</SelectItem>
              <SelectItem value="member">Member</SelectItem>
              <SelectItem value="viewer">Viewer</SelectItem>
            </SelectContent>
          </Select>
          <Button onClick={invite} disabled={inviting || !inviteEmail.trim()} className="rounded-xl gap-1">
            {inviting ? <Loader2 className="h-3 w-3 animate-spin" /> : <Mail className="h-3 w-3" />} Invite
          </Button>
        </div>
      </div>

      {/* Members list */}
      {loading ? (
        <div className="text-center py-8"><Loader2 className="h-6 w-6 animate-spin mx-auto text-muted-foreground" /></div>
      ) : (
        <div className="space-y-2">
          {members.map((m) => (
            <div key={m.id} className="flex items-center gap-3 rounded-xl border bg-card p-4 hover:shadow-soft-sm transition-shadow">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-muted text-sm font-bold">
                {(m.user_name || m.user_email || "?")[0].toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{m.user_name || m.user_email || "Unknown"}</p>
                <p className="text-2xs text-muted-foreground">{m.user_email || ""}</p>
              </div>
              <Badge variant="outline" className={cn("text-[10px] capitalize", ROLE_COLORS[m.role] || "")}>{m.role}</Badge>
              {m.role !== "owner" && (
                <div className="flex gap-1">
                  <Select value={m.role} onValueChange={(v) => changeRole(m.user_id, v)}>
                    <SelectTrigger className="h-7 w-24 text-2xs rounded-lg"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="admin">Admin</SelectItem>
                      <SelectItem value="recruiter">Recruiter</SelectItem>
                      <SelectItem value="member">Member</SelectItem>
                      <SelectItem value="viewer">Viewer</SelectItem>
                    </SelectContent>
                  </Select>
                  <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive" onClick={() => removeMember(m.user_id)}>
                    <UserX className="h-3 w-3" />
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
    </RoleGate>
  );
}
