"""SaaS plan catalog.

The catalog is code-owned so limits are reviewable and cannot drift between
the API, UI, and billing metadata. Prices are authored in USD; localized
amounts are derived at request time by ``api.services.saas.fx``.
"""

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from api.constants import ANNUAL_DISCOUNT_PERCENT, FLW_SECRET_KEY


@dataclass(frozen=True)
class Plan:
    code: str
    name: str
    description: str
    base_price_usd_cents: int
    limits: dict[str, int]
    features: tuple[str, ...]

    def usd_cents(self, billing_interval: str = "monthly") -> int:
        if billing_interval == "annual":
            discount = 1 - (ANNUAL_DISCOUNT_PERCENT / 100)
            return round(self.base_price_usd_cents * 12 * discount)
        return self.base_price_usd_cents

    def as_dict(
        self,
        *,
        currency: str = "USD",
        billing_interval: str = "monthly",
        amount_minor: int | None = None,
        price_display: str | None = None,
        fx_rate: float | None = None,
        fx_buffer_percent: float | None = None,
    ) -> dict[str, Any]:
        usd_cents = self.usd_cents(billing_interval)
        localized_minor = usd_cents if amount_minor is None else amount_minor
        return {
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "base_price_usd_cents": self.base_price_usd_cents,
            "price_usd": self.base_price_usd_cents / 100,
            "price_cents": localized_minor,
            "price_display": price_display or f"${localized_minor / 100:,.0f}",
            "currency": currency,
            "billing_interval": billing_interval,
            "fx_rate": fx_rate,
            "fx_buffer_percent": fx_buffer_percent,
            "billing_configured": bool(FLW_SECRET_KEY),
            "limits": self.limits,
            "features": list(self.features),
        }


TRIAL_PLAN = Plan(
    code="trial",
    name="Trial",
    description="Explore Dograh with a small workspace.",
    base_price_usd_cents=0,
    limits={
        "agents": 1,
        "seats": 2,
        "concurrent_calls": 1,
        "monthly_call_minutes": 60,
    },
    features=("1 voice agent", "60 call minutes", "2 seats"),
)

STARTER_PLAN = Plan(
    code="starter",
    name="Starter",
    description="For solo builders shipping their first voice agent.",
    base_price_usd_cents=4900,
    limits={
        "agents": 3,
        "seats": 3,
        "concurrent_calls": 2,
        "monthly_call_minutes": 300,
    },
    features=("3 voice agents", "300 call minutes / month", "3 seats"),
)

GROWTH_PLAN = Plan(
    code="growth",
    name="Growth",
    description="For teams running production voice workflows.",
    base_price_usd_cents=14900,
    limits={
        "agents": 15,
        "seats": 10,
        "concurrent_calls": 5,
        "monthly_call_minutes": 2000,
    },
    features=("15 voice agents", "2,000 call minutes / month", "10 seats"),
)

SCALE_PLAN = Plan(
    code="scale",
    name="Scale",
    description="For high-volume teams that need more concurrency.",
    base_price_usd_cents=39900,
    limits={
        "agents": 100,
        "seats": 50,
        "concurrent_calls": 20,
        "monthly_call_minutes": 10000,
    },
    features=("100 voice agents", "10,000 call minutes / month", "50 seats"),
)

PLANS: dict[str, Plan] = {
    plan.code: plan for plan in (TRIAL_PLAN, STARTER_PLAN, GROWTH_PLAN, SCALE_PLAN)
}

PUBLIC_PLAN_CODES = ("starter", "growth", "scale")
BILLING_INTERVALS = ("monthly", "annual")


def get_plan(plan_code: str) -> Plan:
    plan = PLANS.get(plan_code)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Unknown plan: {plan_code}")
    return plan


def configured_plans() -> list[Plan]:
    """Return public plans. Billing configuration only gates checkout."""
    return [PLANS[code] for code in PUBLIC_PLAN_CODES]
