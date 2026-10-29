"use client";

import { Copy, Loader2, Mail, Trash2, UserPlus, Users } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { PageLayout } from "@/components/layout/PageLayout";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/lib/auth";
import {
  getTeam,
  inviteMember,
  removeMember,
  revokeInvitation,
  type OrganizationRole,
  type TeamResponse,
  updateMemberRole,
} from "@/lib/saasApi";

const roleLabels: Record<OrganizationRole, string> = {
  owner: "Owner",
  admin: "Admin",
  member: "Member",
};

export default function TeamPage() {
  const auth = useAuth();
  const [team, setTeam] = useState<TeamResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"admin" | "member">("member");
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadTeam = useCallback(async () => {
    if (!auth.isAuthenticated) return;
    setError(null);
    try {
      const token = await auth.getAccessToken();
      setTeam(await getTeam(token));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load team");
    } finally {
      setLoading(false);
    }
  }, [auth.isAuthenticated, auth.getAccessToken]);

  useEffect(() => {
    if (!auth.loading) void loadTeam();
  }, [auth.loading, loadTeam]);

  const userEmail = useMemo(() => {
    const user = auth.user as
      | { email?: string; primaryEmail?: string }
      | null
      | undefined;
    return user?.email ?? user?.primaryEmail ?? null;
  }, [auth.user]);

  const myRole = useMemo(() => {
    const mine = team?.members.find(
      (member) =>
        member.email &&
        userEmail &&
        member.email.toLowerCase() === userEmail.toLowerCase()
    );
    return mine?.role ?? null;
  }, [team, userEmail]);

  const canManage = myRole === "owner" || myRole === "admin";

  async function handleInvite(event: React.FormEvent) {
    event.preventDefault();
    if (!email.trim()) return;
    setBusy(true);
    try {
      const token = await auth.getAccessToken();
      const invitation = await inviteMember(token, email.trim(), inviteRole);
      setInviteUrl(invitation.invite_url ?? null);
      setEmail("");
      toast.success("Invitation created");
      await loadTeam();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not create invitation");
    } finally {
      setBusy(false);
    }
  }

  async function handleRoleChange(userId: number, role: OrganizationRole) {
    try {
      const token = await auth.getAccessToken();
      await updateMemberRole(token, userId, role);
      toast.success("Role updated");
      await loadTeam();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not update role");
    }
  }

  async function handleRemove(userId: number) {
    try {
      const token = await auth.getAccessToken();
      await removeMember(token, userId);
      toast.success("Member removed");
      await loadTeam();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not remove member");
    }
  }

  async function handleRevoke(invitationId: number) {
    try {
      const token = await auth.getAccessToken();
      await revokeInvitation(token, invitationId);
      toast.success("Invitation revoked");
      await loadTeam();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not revoke invitation");
    }
  }

  return (
    <PageLayout
      title="Team"
      description="Invite teammates and manage organization access."
      width="narrow"
    >
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Users className="h-5 w-5" /> Members
          </CardTitle>
          <CardDescription>
            {team
              ? `${team.seats_used} of ${team.seats_limit} seats used`
              : "Loading team…"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading team
            </div>
          ) : error ? (
            <p className="text-sm text-destructive">{error}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="py-2 pr-4">Member</th>
                    <th className="py-2 pr-4">Role</th>
                    <th className="py-2 text-right">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {team?.members.map((member) => (
                    <tr key={member.user_id} className="border-b last:border-0">
                      <td className="py-3 pr-4">
                        <div className="font-medium">{member.email ?? "Unknown"}</div>
                        <div className="text-xs text-muted-foreground">
                          User #{member.user_id}
                        </div>
                      </td>
                      <td className="py-3 pr-4">
                        {canManage && member.role !== "owner" ? (
                          <select
                            className="rounded-md border bg-background px-2 py-1 text-sm"
                            value={member.role}
                            onChange={(event) =>
                              handleRoleChange(
                                member.user_id,
                                event.target.value as OrganizationRole
                              )
                            }
                          >
                            <option value="member">Member</option>
                            <option value="admin">Admin</option>
                          </select>
                        ) : (
                          <span className="rounded-full border px-2 py-0.5 text-xs">
                            {roleLabels[member.role]}
                          </span>
                        )}
                      </td>
                      <td className="py-3 text-right">
                        {canManage && member.role !== "owner" && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleRemove(member.user_id)}
                          >
                            <Trash2 className="h-4 w-4" /> Remove
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {canManage && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <UserPlus className="h-5 w-5" /> Invite a teammate
            </CardTitle>
            <CardDescription>
              We generate a secure invite link. Email delivery can be connected later.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form
              onSubmit={handleInvite}
              className="flex flex-col gap-3 sm:flex-row sm:items-end"
            >
              <div className="flex-1 space-y-1.5">
                <Label htmlFor="invite-email">Email</Label>
                <Input
                  id="invite-email"
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="teammate@company.com"
                  required
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="invite-role">Role</Label>
                <select
                  id="invite-role"
                  className="h-9 rounded-md border bg-background px-3 text-sm"
                  value={inviteRole}
                  onChange={(event) =>
                    setInviteRole(event.target.value as "admin" | "member")
                  }
                >
                  <option value="member">Member</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
              <Button type="submit" disabled={busy}>
                {busy ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Mail className="h-4 w-4" />
                )}
                Create invite
              </Button>
            </form>
            {inviteUrl && (
              <div className="mt-4 rounded-lg border bg-muted/40 p-3">
                <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Invite link
                </div>
                <div className="flex items-center gap-2">
                  <code className="min-w-0 flex-1 truncate text-xs">{inviteUrl}</code>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      void navigator.clipboard.writeText(inviteUrl);
                      toast.success("Invite link copied");
                    }}
                  >
                    <Copy className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {canManage && (
        <Card>
          <CardHeader>
            <CardTitle>Pending invitations</CardTitle>
            <CardDescription>Invitations expire after seven days.</CardDescription>
          </CardHeader>
          <CardContent>
            {!team?.invitations.length ? (
              <p className="text-sm text-muted-foreground">No pending invitations.</p>
            ) : (
              <div className="space-y-2">
                {team.invitations.map((invitation) => (
                  <div
                    key={invitation.id}
                    className="flex items-center justify-between gap-3 rounded-lg border p-3"
                  >
                    <div>
                      <div className="text-sm font-medium">{invitation.email}</div>
                      <div className="text-xs text-muted-foreground">
                        {roleLabels[invitation.role]} · expires{" "}
                        {new Date(invitation.expires_at).toLocaleDateString()}
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRevoke(invitation.id)}
                    >
                      Revoke
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </PageLayout>
  );
}
