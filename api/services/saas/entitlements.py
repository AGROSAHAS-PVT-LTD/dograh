"""Resolve an organization's plan and enforce plan limits."""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException

from api.constants import SAAS_TRIAL_DAYS
from api.db import db_client
from api.enums import SubscriptionStatus
from api.services.saas.fx import format_amount
from api.services.saas.plans import PLANS, TRIAL_PLAN, Plan, get_plan

ACTIVE_STATUSES = {
    SubscriptionStatus.TRIALING.value,
    SubscriptionStatus.ACTIVE.value,
}


def _as_utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _subscription_is_active(subscription) -> bool:
    if subscription is None:
        return False
    if subscription.status not in ACTIVE_STATUSES:
        return False
    if subscription.status == SubscriptionStatus.TRIALING.value:
        trial_end = _as_utc(subscription.trial_end)
        return trial_end is None or trial_end > datetime.now(UTC)
    period_end = _as_utc(subscription.current_period_end)
    if subscription.status == SubscriptionStatus.ACTIVE.value and period_end:
        return period_end > datetime.now(UTC)
    return True


async def _ensure_trial_subscription(organization_id: int):
    subscription = await db_client.get_subscription(organization_id)
    if subscription is not None:
        return subscription
    now = datetime.now(UTC)
    await db_client.upsert_subscription(
        organization_id=organization_id,
        plan_code=TRIAL_PLAN.code,
        status=SubscriptionStatus.TRIALING.value,
        provider="flutterwave",
        currency="USD",
        billing_interval="monthly",
        amount_minor=0,
        trial_end=now + timedelta(days=SAAS_TRIAL_DAYS),
    )
    return await db_client.get_subscription(organization_id)


async def get_entitlements(organization_id: int) -> dict[str, Any]:
    subscription = await _ensure_trial_subscription(organization_id)
    plan: Plan = TRIAL_PLAN
    if (
        subscription
        and subscription.plan_code in PLANS
        and subscription.status in ACTIVE_STATUSES
    ):
        plan = get_plan(subscription.plan_code)

    use_subscription_billing = bool(
        subscription
        and subscription.status in ACTIVE_STATUSES
        and subscription.plan_code in PLANS
    )
    currency = (
        subscription.currency
        if use_subscription_billing and subscription.currency
        else "USD"
    )
    billing_interval = (
        subscription.billing_interval
        if use_subscription_billing and subscription.billing_interval
        else "monthly"
    )
    amount_minor = (
        subscription.amount_minor
        if use_subscription_billing and subscription.amount_minor is not None
        else plan.usd_cents(billing_interval)
    )
    price_display = (
        format_amount(currency, amount_minor) if amount_minor is not None else None
    )

    members = await db_client.get_organization_members_with_roles(organization_id)
    agents = await db_client.count_active_workflows(organization_id)
    seats_used = len(members)
    return {
        "organization_id": organization_id,
        "plan": plan.as_dict(
            currency=currency,
            billing_interval=billing_interval,
            amount_minor=amount_minor,
            price_display=price_display,
        ),
        "subscription_status": (
            subscription.status if subscription else SubscriptionStatus.TRIALING.value
        ),
        "is_active": _subscription_is_active(subscription),
        "provider": subscription.provider if subscription else None,
        "billing_interval": billing_interval,
        "currency": currency,
        "amount_minor": amount_minor,
        "cancel_at_period_end": bool(
            subscription.cancel_at_period_end if subscription else False
        ),
        "current_period_end": (
            subscription.current_period_end.isoformat()
            if subscription and subscription.current_period_end
            else None
        ),
        "usage": {
            "agents": agents,
            "seats": seats_used,
            "concurrent_calls": 0,
            "monthly_call_minutes": 0,
        },
        "remaining": {
            "agents": max(0, plan.limits["agents"] - agents),
            "seats": max(0, plan.limits["seats"] - seats_used),
        },
    }


async def assert_agent_capacity(organization_id: int) -> None:
    entitlements = await get_entitlements(organization_id)
    if entitlements["usage"]["agents"] >= entitlements["plan"]["limits"]["agents"]:
        raise HTTPException(
            status_code=402,
            detail=(
                "Your plan's agent limit has been reached. "
                "Upgrade your plan to create another voice agent."
            ),
        )


async def assert_seat_capacity(organization_id: int) -> None:
    entitlements = await get_entitlements(organization_id)
    if entitlements["usage"]["seats"] >= entitlements["plan"]["limits"]["seats"]:
        raise HTTPException(
            status_code=402,
            detail="Your plan's seat limit has been reached. Upgrade to invite more teammates.",
        )
