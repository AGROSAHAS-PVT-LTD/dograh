"use client";

import { Loader2, Phone } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { toast } from "sonner";

import { client } from "@/client/client.gen";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Auth, ConfirmationResult, RecaptchaVerifier } from "firebase/auth";

interface FirebaseBrowserConfig {
  apiKey: string;
  authDomain: string;
  projectId: string;
  appId: string;
  messagingSenderId?: string;
}

let firebaseAuthPromise: Promise<Auth> | null = null;

async function getFirebaseAuth(config: FirebaseBrowserConfig): Promise<Auth> {
  if (!firebaseAuthPromise) {
    firebaseAuthPromise = (async () => {
      const { getApp, getApps, initializeApp } = await import("firebase/app");
      const { getAuth } = await import("firebase/auth");
      const app = getApps().length
        ? getApp()
        : initializeApp({
            apiKey: config.apiKey,
            authDomain: config.authDomain,
            projectId: config.projectId,
            appId: config.appId,
            messagingSenderId: config.messagingSenderId,
          });
      return getAuth(app);
    })();
  }
  return firebaseAuthPromise;
}

function backendUrl(): string {
  return (client.getConfig().baseUrl || window.location.origin).replace(/\/$/, "");
}

async function exchangeFirebaseToken(idToken: string): Promise<void> {
  const response = await fetch(`${backendUrl()}/api/v1/auth/firebase`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id_token: idToken }),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(payload?.detail || "Firebase sign-in failed");
  }
  await fetch("/api/auth/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token: payload.token, user: payload.user }),
  });
  window.location.href = "/after-sign-in";
}

function normalizePhone(value: string): string {
  return value.replace(/[\s()-]/g, "");
}

function firebaseErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "Sign-in failed. Please try again.";
}

function GoogleMark() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4">
      <path
        fill="#4285F4"
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1Z"
      />
      <path
        fill="#34A853"
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.99.66-2.25 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23Z"
      />
      <path
        fill="#FBBC05"
        d="M5.84 14.1a6.6 6.6 0 0 1 0-4.2V7.06H2.18a11 11 0 0 0 0 9.88l3.66-2.84Z"
      />
      <path
        fill="#EA4335"
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.16-3.16A10.96 10.96 0 0 0 2.18 7.06L5.84 9.9C6.71 7.31 9.14 5.38 12 5.38Z"
      />
    </svg>
  );
}

export function FirebaseAuthButtons() {
  const [config, setConfig] = useState<FirebaseBrowserConfig | null>(null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState<"google" | "sms" | null>(null);
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [codeSent, setCodeSent] = useState(false);
  const confirmationRef = useRef<ConfirmationResult | null>(null);
  const recaptchaRef = useRef<RecaptchaVerifier | null>(null);
  const recaptchaId = useId().replaceAll(":", "");
  const recaptchaContainerId = `recaptcha-${recaptchaId}`;

  useEffect(() => {
    fetch("/api/config/auth")
      .then((response) => response.json())
      .then((data) => {
        if (data.provider === "local" && data.firebaseConfig?.apiKey) {
          setConfig(data.firebaseConfig as FirebaseBrowserConfig);
        }
      })
      .catch(() => {
        // Firebase is optional; leave the local email/password form usable.
      })
      .finally(() => setReady(true));
  }, []);

  useEffect(() => {
    return () => {
      recaptchaRef.current?.clear();
    };
  }, []);

  if (!ready || !config) return null;
  const activeConfig = config as FirebaseBrowserConfig;

  async function handleGoogle() {
    setBusy("google");
    try {
      const auth = await getFirebaseAuth(activeConfig);
      const { GoogleAuthProvider, signInWithPopup, signOut } = await import(
        "firebase/auth"
      );
      const result = await signInWithPopup(auth, new GoogleAuthProvider());
      const idToken = await result.user.getIdToken();
      await exchangeFirebaseToken(idToken);
      await signOut(auth);
    } catch (error) {
      toast.error(firebaseErrorMessage(error));
      setBusy(null);
    }
  }

  async function handleSendCode(event_: React.FormEvent) {
    event_.preventDefault();
    const normalized = normalizePhone(phone);
    if (!/^\+[1-9]\d{7,14}$/.test(normalized)) {
      toast.error(
        "Enter a phone number in international format, e.g. +2348012345678"
      );
      return;
    }
    setBusy("sms");
    try {
      const auth = await getFirebaseAuth(activeConfig);
      const { RecaptchaVerifier, signInWithPhoneNumber } = await import(
        "firebase/auth"
      );
      recaptchaRef.current?.clear();
      recaptchaRef.current = new RecaptchaVerifier(auth, recaptchaContainerId, {
        size: "invisible",
      });
      confirmationRef.current = await signInWithPhoneNumber(
        auth,
        normalized,
        recaptchaRef.current
      );
      setPhone(normalized);
      setCodeSent(true);
      toast.success("Verification code sent");
    } catch (error) {
      toast.error(firebaseErrorMessage(error));
      recaptchaRef.current?.clear();
      recaptchaRef.current = null;
    } finally {
      setBusy(null);
    }
  }

  async function handleVerifyCode(event_: React.FormEvent) {
    event_.preventDefault();
    if (!confirmationRef.current) {
      toast.error("Request a new verification code first");
      return;
    }
    setBusy("sms");
    try {
      const credential = await confirmationRef.current.confirm(code.trim());
      const idToken = await credential.user.getIdToken();
      await exchangeFirebaseToken(idToken);
    } catch (error) {
      toast.error(firebaseErrorMessage(error));
      setBusy(null);
    }
  }


  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        <span className="h-px flex-1 bg-border" />
        or continue with
        <span className="h-px flex-1 bg-border" />
      </div>

      <Button
        type="button"
        variant="outline"
        className="w-full"
        disabled={busy !== null}
        onClick={handleGoogle}
      >
        {busy === "google" ? (
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        ) : (
          <span className="mr-2">
            <GoogleMark />
          </span>
        )}
        Continue with Google
      </Button>

      <div className="rounded-lg border p-3">
        <div className="mb-2 flex items-center gap-2 text-sm font-medium">
          <Phone className="h-4 w-4" />
          Sign in with phone
        </div>
        {!codeSent ? (
          <form onSubmit={handleSendCode} className="space-y-2">
            <Label htmlFor="firebase-phone" className="sr-only">
              Phone number
            </Label>
            <div className="flex gap-2">
              <Input
                id="firebase-phone"
                type="tel"
                inputMode="tel"
                autoComplete="tel"
                placeholder="+2348012345678"
                value={phone}
                onChange={(event) => setPhone(event.target.value)}
                required
              />
              <Button type="submit" disabled={busy !== null}>
                {busy === "sms" ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  "Send code"
                )}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Use international format. Firebase sends the SMS.
            </p>
          </form>
        ) : (
          <form onSubmit={handleVerifyCode} className="space-y-2">
            <p className="text-xs text-muted-foreground">
              Code sent to {phone}.{" "}
              <button
                type="button"
                className="underline"
                onClick={() => {
                  setCodeSent(false);
                  setCode("");
                  confirmationRef.current = null;
                }}
              >
                Change number
              </button>
            </p>
            <div className="flex gap-2">
              <Input
                aria-label="Verification code"
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder="123456"
                value={code}
                onChange={(event) => setCode(event.target.value)}
                required
              />
              <Button type="submit" disabled={busy !== null}>
                {busy === "sms" ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  "Verify"
                )}
              </Button>
            </div>
          </form>
        )}
      </div>
      <div id={recaptchaContainerId} />
    </div>
  );
}

