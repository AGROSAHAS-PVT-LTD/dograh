"use client";

import { CheckCircle2, CreditCard, Loader2, Sparkles } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
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
import {
  cancelSubscription,
  createCheckout,
  type CurrencyOption,
  type Entitlements,
  getPlans,
  getSubscription,
  type Plan,
  verifyCheckout,
} from "@/lib/saasApi";

type BillingInterval = "monthly" | "annual";

export default function PlanPage() {
  const auth = useAuth();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [entitlements, setEntitlements] = useState<Entitlements | null>(null);
  const [currencies, setCurrencies] = useState<CurrencyOption[]>([]);
  const [currency, setCurrency] = useState("USD");
  const [billingInterval, setBillingInterval] =
    useState<BillingInterval>("monthly");
  const [loading, setLoading] = useState(true);
  const [busyPlan, setBusyPlan] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const verifiedRef = useRef(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const planResponse = await getPlans(currency, billingInterval);
      setPlans(planResponse.plans);
      setCurrencies(planResponse.supported_currencies);
      if (auth.isAuthenticated) {
        const token = await auth.getAccessToken();
        const subscription = await getSubscription(token);
        setEntitlements(subscription.entitlements);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load plans");
    } finally {
      setLoading(false);
    }
  }, [auth.isAuthenticated, auth.getAccessToken, currency, billingInterval]);

  useEffect(() => {
    if (!auth.loading) void load();
  }, [auth.loading, load]);

  useEffect(() => {
    if (auth.loading || !auth.isAuthenticated || verifiedRef.current) return;
    const params = new URLSearchParams(window.location.search);
    const txRef = params.get("tx_ref");
    if (!txRef) return;
    verifiedRef.current = true;
    void (async () => {
      try {
        const token = await auth.getAccessToken();
        const result = await verifyCheckout(token, txRef);
        setEntitlements(result.entitlements);
        toast.success("Subscription activated");
        window.history.replaceState({}, "", "/plan");
        await load();
      } catch (err) {
        toast.error(
          err instanceof Error ? err.message : "Could not verify payment"
        );
      }
    })();
  }, [auth.loading, auth.isAuthenticated, auth.getAccessToken, load]);

  async function handleUpgrade(plan: Plan) {
    setBusyPlan(plan.code);
    try {
      const token = await auth.getAccessToken();
      const checkout = await createCheckout(
        token,
        plan.code,
        currency,
        billingInterval
      );
      window.location.href = checkout.checkout_url;
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not start checkout");
      setBusyPlan(null);
    }
  }

  async function handleCancel() {
    if (
      !window.confirm(
        "Cancel this subscription? Flutterwave will stop future charges immediately."
      )
    ) {
      return;
    }
    try {
      const token = await auth.getAccessToken();
      await cancelSubscription(token);
      toast.success("Subscription cancelled");
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not cancel");
    }
  }

  const currentCode = entitlements?.plan.code;

  return (
    <PageLayout
      title="Plan & Billing"
      description="Choose the plan that fits your workspace. Provider usage stays on your own keys."
      width="full"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <label htmlFor="currency" className="text-sm text-muted-foreground">
            Billing currency
          </label>
          <select
            id="currency"
            className="h-9 rounded-md border border-input bg-background px-3 text-sm"
            value={currency}
            onChange={(event) => setCurrency(event.target.value)}
          >
            {(currencies.length
              ? currencies
              : [{ code: "USD", country: "United States / international" }]
            ).map((option) => (
              <option key={option.code} value={option.code}>
                {option.code} — {option.country}
              </option>
            ))}
          </select>
          <div className="flex rounded-md border border-input p-0.5">
            {(["monthly", "annual"] as BillingInterval[]).map((interval) => (
              <button
                key={interval}
                type="button"
                className={`rounded px-3 py-1 text-sm capitalize ${
                  billingInterval === interval
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground"
                }`}
                onClick={() => setBillingInterval(interval)}
              >
                {interval}
              </button>
            ))}
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          Local prices include a 10% FX buffer. Annual plans are discounted.
        </p>
      </div>

      {entitlements && (
        <Card>
          <CardHeader className="flex-row items-start justify-between space-y-0">
            <div>
              <CardTitle className="flex items-center gap-2">
                <CreditCard className="h-5 w-5" /> Current plan
              </CardTitle>
              <CardDescription>
                {entitlements.plan.name} · {entitlements.subscription_status}
                {entitlements.current_period_end
                  ? ` · renews ${new Date(
                      entitlements.current_period_end
                    ).toLocaleDateString()}`
                  : ""}
              </CardDescription>
            </div>
            {entitlements.provider === "flutterwave" &&
              entitlements.subscription_status === "active" && (
                <Button variant="outline" onClick={handleCancel}>
                  Cancel subscription
                </Button>
              )}
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            {Object.entries(entitlements.plan.limits).map(([key, limit]) => {
              const used = entitlements.usage[key] ?? 0;
              const percent =
                limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
              return (
                <div key={key} className="space-y-1.5">
                  <div className="flex justify-between text-sm">
                    <span className="capitalize text-muted-foreground">
                      {key.replaceAll("_", " ")}
                    </span>
                    <span>
                      {used} / {limit}
                    </span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-primary"
                      style={{ width: `${percent}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="grid gap-4 md:grid-cols-3">
        {plans.map((plan) => {
          const current = currentCode === plan.code;
          return (
            <Card key={plan.code} className={current ? "border-primary" : undefined}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  {plan.name}
                  {plan.code === "growth" && (
                    <Sparkles className="h-4 w-4 text-primary" />
                  )}
                </CardTitle>
                <CardDescription>{plan.description}</CardDescription>
                <div className="pt-2 text-3xl font-semibold tracking-tight">
                  {plan.price_display}
                  <span className="text-sm font-normal text-muted-foreground">
                    {" "}
                    / {billingInterval === "annual" ? "year" : "month"}
                  </span>
                </div>
                {plan.currency !== "USD" && (
                  <p className="text-xs text-muted-foreground">
                    ${plan.price_usd.toFixed(0)} USD base · billed in{" "}
                    {plan.currency}
                  </p>
                )}
              </CardHeader>
              <CardContent className="space-y-4">
                <ul className="space-y-2 text-sm">
                  {plan.features.map((feature) => (
                    <li key={feature} className="flex items-start gap-2">
                      <CheckCircle2 className="mt-0.5 h-4 w-4 text-primary" />
                      <span>{feature}</span>
                    </li>
                  ))}
                </ul>
                <Button
                  className="w-full"
                  disabled={
                    current || busyPlan === plan.code || !plan.billing_configured
                  }
                  onClick={() => handleUpgrade(plan)}
                >
                  {busyPlan === plan.code ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : current ? (
                    "Current plan"
                  ) : plan.billing_configured ? (
                    "Choose plan"
                  ) : (
                    "Billing not configured"
                  )}
                </Button>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading plans
        </div>
      )}

      <p className="text-xs text-muted-foreground">
        Plans cover the Dograh platform only. Customers connect their own LLM, TTS,
        STT, and telephony credentials. Usage limits are enforced by the API.
        Payments are processed by Flutterwave.
      </p>
    </PageLayout>
  );
}

