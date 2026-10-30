"use client";

import { CheckCircle2, Loader2, Mail } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
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
import { useAuth } from "@/lib/auth";
import { acceptInvitation } from "@/lib/saasApi";

export default function InvitePage() {
  const auth = useAuth();
  const [token, setToken] = useState<string | null>(null);
  const [state, setState] = useState<"idle" | "working" | "done" | "error">("idle");
  const [message, setMessage] = useState("");

  useEffect(() => {
    setToken(new URLSearchParams(window.location.search).get("token"));
  }, []);

  async function handleAccept() {
    if (!token) return;
    setState("working");
    try {
      const accessToken = await auth.getAccessToken();
      await acceptInvitation(accessToken, token);
      setState("done");
      toast.success("Invitation accepted");
    } catch (err) {
      setState("error");
      setMessage(err instanceof Error ? err.message : "Could not accept invitation");
    }
  }

  return (
    <PageLayout
      title="Join your team"
      description="Accept your invitation to the workspace."
      width="narrow"
    >
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Mail className="h-5 w-5" /> Workspace invitation
          </CardTitle>
          <CardDescription>
            Sign in with the email address that was invited, then accept.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {!token ? (
            <p className="text-sm text-destructive">This invite link is missing a token.</p>
          ) : state === "done" ? (
            <div className="space-y-3">
              <p className="flex items-center gap-2 text-sm">
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                You are now a member of this workspace.
              </p>
              <Button asChild>
                <Link href="/team">Open Team</Link>
              </Button>
            </div>
          ) : auth.loading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Checking session
            </div>
          ) : !auth.isAuthenticated ? (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Sign in first. After signing in, return to this page to accept the invite.
              </p>
              <Button asChild>
                <Link href="/auth/login">Sign in</Link>
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Signed in as{" "}
                {(auth.user as { email?: string; primaryEmail?: string } | null)?.email ??
                  (auth.user as { primaryEmail?: string } | null)?.primaryEmail ??
                  "your account"}
                .
              </p>
              <Button onClick={handleAccept} disabled={state === "working"}>
                {state === "working" ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <CheckCircle2 className="h-4 w-4" />
                )}
                Accept invitation
              </Button>
              {state === "error" && <p className="text-sm text-destructive">{message}</p>}
            </div>
          )}
        </CardContent>
      </Card>
    </PageLayout>
  );
}
