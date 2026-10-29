import calendar
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger

from api.db import db_client
from api.enums import OrganizationRole, SubscriptionStatus
from api.schemas.billing_saas import (
    CancelResponse,
    CheckoutRequest,
    CheckoutResponse,
    CheckoutVerifyRequest,
    SubscriptionResponse,
)
from api.services.saas.access import OrganizationAccess, require_organization_roles
from api.services.saas.entitlements import get_entitlements
from api.services.saas.fx import (
    CURRENCY_COUNTRIES,
    currency_decimals,
    quote as price_quote,
)
from api.services.saas.flutterwave_client import (
    cancel_subscription,
    create_checkout as create_flw_checkout,
    create_payment_plan,
    find_subscription_id,
    new_tx_ref,
    verify_by_reference,
    verify_transaction,
    verify_webhook,
)
from api.services.saas.plans import (
    BILLING_INTERVALS,
    PUBLIC_PLAN_CODES,
    TRIAL_PLAN,
    configured_plans,
    get_plan,
)

router = APIRouter(prefix="/saas", tags=["saas"])


def _timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=UTC)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _add_interval(start: datetime, billing_interval: str) -> datetime:
    months = 12 if billing_interval == "annual" else 1
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return start.replace(year=year, month=month, day=day)


def _expected_major(amount_minor: int, currency: str) -> float:
    return amount_minor / (10 ** currency_decimals(currency))


def _transaction_matches(
    tx: dict[str, Any],
    *,
    amount_minor: int,
    currency: str,
    tx_ref: str,
    require_ref: bool = True,
) -> bool:
    tx_status = str(tx.get("status") or "").lower()
    tx_currency = str(tx.get("currency") or "").upper()
    try:
        tx_amount = float(tx.get("amount") or 0)
    except (TypeError, ValueError):
        return False
    return (
        tx_status == "successful"
        and tx_currency == currency.upper()
        and tx_amount + 0.01 >= _expected_major(amount_minor, currency)
        and (not require_ref or str(tx.get("tx_ref") or "") == tx_ref)
    )


def _plan_id_from_payload(data: dict[str, Any]) -> str | None:
    value = data.get("payment_plan")
    if value is None:
        plan = data.get("plan")
        if isinstance(plan, dict):
            value = plan.get("id")
    return str(value) if value is not None else None


@router.get("/plans")
async def list_plans(
    currency: str = "USD", billing_interval: str = "monthly"
) -> dict:
    if billing_interval not in BILLING_INTERVALS:
        raise HTTPException(status_code=400, detail="Invalid billing interval")
    plans = []
    for plan in configured_plans():
        localized = await price_quote(plan, currency, billing_interval)
        plans.append(
            plan.as_dict(
                currency=localized["currency"],
                billing_interval=billing_interval,
                amount_minor=localized["amount_minor"],
                price_display=localized["price_display"],
                fx_rate=localized["fx_rate"],
                fx_buffer_percent=localized["fx_buffer_percent"],
            )
        )
    return {
        "plans": plans,
        "currency": currency.upper(),
        "billing_interval": billing_interval,
        "supported_currencies": [
            {"code": code, "country": country}
            for code, country in CURRENCY_COUNTRIES.items()
        ],
    }


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    access: OrganizationAccess = Depends(
        require_organization_roles(OrganizationRole.OWNER, OrganizationRole.ADMIN)
    ),
) -> SubscriptionResponse:
    return SubscriptionResponse(
        entitlements=await get_entitlements(access.organization_id)
    )


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    request: CheckoutRequest,
    access: OrganizationAccess = Depends(
        require_organization_roles(OrganizationRole.OWNER)
    ),
) -> CheckoutResponse:
    if request.plan_code not in PUBLIC_PLAN_CODES:
        raise HTTPException(status_code=400, detail="Choose a paid plan")
    if request.billing_interval not in BILLING_INTERVALS:
        raise HTTPException(status_code=400, detail="Invalid billing interval")

    plan = get_plan(request.plan_code)
    if not access.user.email:
        raise HTTPException(
            status_code=400,
            detail="Your account needs an email address for billing",
        )
    localized = await price_quote(
        plan, request.currency, request.billing_interval
    )
    subscription = await db_client.get_subscription(access.organization_id)

    provider_plan_id = None
    if (
        subscription
        and subscription.provider_plan_id
        and subscription.status
        in (SubscriptionStatus.TRIALING.value, SubscriptionStatus.ACTIVE.value)
    ):
        same_quote = (
            subscription.plan_code == plan.code
            and subscription.currency == localized["currency"]
            and subscription.billing_interval == request.billing_interval
            and subscription.amount_minor == localized["amount_minor"]
        )
        if same_quote:
            provider_plan_id = subscription.provider_plan_id

    if not provider_plan_id:
        flw_plan = await create_payment_plan(
            plan=plan,
            currency=localized["currency"],
            billing_interval=request.billing_interval,
            amount_major=localized["amount_major"],
        )
        provider_plan_id = str(flw_plan["id"])

    tx_ref = new_tx_ref(
        access.organization_id, plan.code, request.billing_interval
    )
    active_plan_code = subscription.plan_code if subscription else TRIAL_PLAN.code
    active_status = (
        subscription.status
        if subscription
        else SubscriptionStatus.TRIALING.value
    )
    await db_client.upsert_subscription(
        organization_id=access.organization_id,
        plan_code=active_plan_code,
        status=active_status,
        provider="flutterwave",
        provider_customer_id=(
            subscription.provider_customer_id if subscription else None
        ),
        provider_subscription_id=(
            subscription.provider_subscription_id if subscription else None
        ),
        provider_plan_id=(
            subscription.provider_plan_id if subscription else None
        ),
        currency=subscription.currency if subscription else "USD",
        billing_interval=(
            subscription.billing_interval if subscription else "monthly"
        ),
        amount_minor=subscription.amount_minor if subscription else 0,
        checkout_tx_ref=tx_ref,
        pending_plan_code=plan.code,
        pending_currency=localized["currency"],
        pending_billing_interval=request.billing_interval,
        pending_amount_minor=localized["amount_minor"],
        pending_provider_plan_id=provider_plan_id,
        current_period_start=(
            subscription.current_period_start if subscription else None
        ),
        current_period_end=(
            subscription.current_period_end if subscription else None
        ),
        cancel_at_period_end=(
            subscription.cancel_at_period_end if subscription else False
        ),
        trial_end=subscription.trial_end if subscription else None,
    )
    checkout = await create_flw_checkout(
        organization_id=access.organization_id,
        plan=plan,
        currency=localized["currency"],
        billing_interval=request.billing_interval,
        amount_major=localized["amount_major"],
        payment_plan_id=provider_plan_id,
        tx_ref=tx_ref,
        redirect_url=request.success_url,
        customer_email=access.user.email or "",
    )
    return CheckoutResponse(
        checkout_url=checkout["link"],
        tx_ref=tx_ref,
        amount_minor=localized["amount_minor"],
        currency=localized["currency"],
        price_display=localized["price_display"],
    )


async def _activate_subscription(
    subscription: Any, tx: dict[str, Any], *, require_ref: bool = True
) -> None:
    plan_code = subscription.pending_plan_code or subscription.plan_code
    currency = subscription.pending_currency or subscription.currency or "USD"
    billing_interval = (
        subscription.pending_billing_interval
        or subscription.billing_interval
        or "monthly"
    )
    amount_minor = (
        subscription.pending_amount_minor
        if subscription.pending_amount_minor is not None
        else subscription.amount_minor or 0
    )
    provider_plan_id = (
        subscription.pending_provider_plan_id or subscription.provider_plan_id
    )
    if not _transaction_matches(
        tx,
        amount_minor=amount_minor,
        currency=currency,
        tx_ref=subscription.checkout_tx_ref or "",
        require_ref=require_ref,
    ):
        raise HTTPException(
            status_code=400,
            detail="Flutterwave transaction does not match this subscription",
        )

    customer = tx.get("customer") or {}
    provider_customer_id = customer.get("id")
    plan_changed = bool(
        subscription.pending_provider_plan_id
        and subscription.pending_provider_plan_id != subscription.provider_plan_id
    )
    provider_subscription_id = (
        None if plan_changed else subscription.provider_subscription_id
    )
    if not provider_subscription_id and customer.get("email"):
        try:
            provider_subscription_id = await find_subscription_id(
                email=str(customer["email"]),
                plan_id=provider_plan_id,
            )
        except HTTPException as exc:
            logger.warning(
                "Could not resolve Flutterwave subscription id for org {}: {}",
                subscription.organization_id,
                exc.detail,
            )

    old_subscription_id = subscription.provider_subscription_id
    if (
        old_subscription_id
        and provider_subscription_id
        and old_subscription_id != provider_subscription_id
    ):
        try:
            await cancel_subscription(old_subscription_id)
        except HTTPException as exc:
            logger.warning(
                "Could not cancel old Flutterwave subscription {} for org {}: {}",
                old_subscription_id,
                subscription.organization_id,
                exc.detail,
            )

    now = datetime.now(UTC)
    await db_client.upsert_subscription(
        organization_id=subscription.organization_id,
        plan_code=plan_code,
        status=SubscriptionStatus.ACTIVE.value,
        provider="flutterwave",
        provider_customer_id=(
            str(provider_customer_id) if provider_customer_id else None
        ),
        provider_subscription_id=provider_subscription_id,
        provider_plan_id=provider_plan_id,
        currency=currency,
        billing_interval=billing_interval,
        amount_minor=amount_minor,
        checkout_tx_ref=subscription.checkout_tx_ref,
        clear_pending=True,
        current_period_start=now,
        current_period_end=_add_interval(now, billing_interval),
        cancel_at_period_end=False,
    )


async def _set_subscription_status(
    subscription: Any,
    status: SubscriptionStatus,
    *,
    cancel_at_period_end: bool = False,
) -> None:
    await db_client.upsert_subscription(
        organization_id=subscription.organization_id,
        plan_code=subscription.plan_code,
        status=status.value,
        provider="flutterwave",
        provider_customer_id=subscription.provider_customer_id,
        provider_subscription_id=subscription.provider_subscription_id,
        provider_plan_id=subscription.provider_plan_id,
        currency=subscription.currency,
        billing_interval=subscription.billing_interval,
        amount_minor=subscription.amount_minor,
        checkout_tx_ref=subscription.checkout_tx_ref,
        clear_pending=True,
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
        cancel_at_period_end=cancel_at_period_end,
    )


@router.post("/checkout/verify")
async def verify_checkout_payment(
    request: CheckoutVerifyRequest,
    access: OrganizationAccess = Depends(
        require_organization_roles(OrganizationRole.OWNER, OrganizationRole.ADMIN)
    ),
) -> dict:
    subscription = await db_client.get_subscription_by_tx_ref(request.tx_ref)
    if not subscription or subscription.organization_id != access.organization_id:
        raise HTTPException(status_code=404, detail="Checkout not found")
    tx = await verify_by_reference(request.tx_ref)
    await _activate_subscription(subscription, tx)
    return {
        "message": "Subscription active",
        "entitlements": await get_entitlements(access.organization_id),
    }


@router.post("/cancel", response_model=CancelResponse)
async def cancel_plan(
    access: OrganizationAccess = Depends(
        require_organization_roles(OrganizationRole.OWNER)
    ),
) -> CancelResponse:
    subscription = await db_client.get_subscription(access.organization_id)
    if not subscription:
        raise HTTPException(
            status_code=400, detail="No active Flutterwave subscription to cancel"
        )
    provider_subscription_id = subscription.provider_subscription_id
    if not provider_subscription_id and subscription.provider_plan_id:
        try:
            provider_subscription_id = await find_subscription_id(
                email=access.user.email or "",
                plan_id=subscription.provider_plan_id,
            )
        except HTTPException as exc:
            logger.warning("Could not resolve Flutterwave subscription: {}", exc.detail)
    if not provider_subscription_id:
        raise HTTPException(
            status_code=400, detail="No active Flutterwave subscription to cancel"
        )
    await cancel_subscription(provider_subscription_id)
    subscription.provider_subscription_id = provider_subscription_id
    await _set_subscription_status(
        subscription,
        SubscriptionStatus.CANCELED,
        cancel_at_period_end=False,
    )
    return CancelResponse(
        message="Subscription cancelled", cancel_at_period_end=False
    )


async def _subscription_for_event(data: dict[str, Any]):
    tx_ref = data.get("tx_ref")
    if tx_ref:
        subscription = await db_client.get_subscription_by_tx_ref(str(tx_ref))
        if subscription:
            return subscription

    meta = data.get("meta")
    if isinstance(meta, dict):
        organization_id = meta.get("organization_id")
        if organization_id is not None:
            try:
                subscription = await db_client.get_subscription(int(organization_id))
            except (TypeError, ValueError):
                subscription = None
            if subscription:
                return subscription

    plan_id = _plan_id_from_payload(data)
    if plan_id:
        return await db_client.get_subscription_by_provider_plan(plan_id)
    return None


@router.post("/webhook/flutterwave")
async def flutterwave_webhook(request: Request) -> dict:
    body = await request.body()
    event = verify_webhook(body, request.headers.get("verif-hash"))
    event_type = str(event.get("event") or "unknown")
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    event_key = (
        f"{event_type}:{data.get('id') or data.get('tx_ref') or 'unknown'}:"
        f"{data.get('status') or 'unknown'}"
    )
    if await db_client.billing_event_exists(event_key):
        return {"received": True, "duplicate": True}

    subscription = await _subscription_for_event(data)
    if subscription is None:
        logger.warning(
            "Flutterwave webhook {} could not be mapped to an organization", event_key
        )
        return {"received": True, "ignored": True}
    if event_type == "charge.completed":
        if str(data.get("status") or "").lower() == "successful":
            transaction_id = data.get("id")
            if transaction_id is None:
                raise HTTPException(
                    status_code=400, detail="Flutterwave event has no transaction id"
                )
            transaction = await verify_transaction(transaction_id)
            require_ref = bool(data.get("tx_ref")) and (
                str(data.get("tx_ref")) == subscription.checkout_tx_ref
            )
            await _activate_subscription(
                subscription, transaction, require_ref=require_ref
            )
        else:
            keep_active = (
                subscription.status == SubscriptionStatus.ACTIVE.value
                and subscription.plan_code != TRIAL_PLAN.code
            )
            status_to_set = SubscriptionStatus.PAST_DUE
            if keep_active:
                status_to_set = SubscriptionStatus.ACTIVE
            await _set_subscription_status(subscription, status_to_set)
    elif event_type == "subscription.cancelled":
        await _set_subscription_status(
            subscription,
            SubscriptionStatus.CANCELED,
            cancel_at_period_end=True,
        )

    is_new = await db_client.record_billing_event(
        event_key=event_key,
        event_type=event_type,
        payload=event,
    )
    return {"received": True, "duplicate": not is_new}

