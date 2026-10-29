"""Minimal Flutterwave client for subscriptions and Standard checkout.

We use Flutterwave's payment plans for recurring billing. A payment plan is
currency- and amount-specific, so the checkout flow creates (or reuses) one
plan per organization/currency/interval combination.
"""

import hmac
import json
import uuid
from typing import Any

import httpx
from fastapi import HTTPException
from loguru import logger

from api.constants import FLW_API_BASE, FLW_SECRET_KEY, FLW_WEBHOOK_SECRET
from api.services.saas.plans import Plan


def billing_configured() -> bool:
    return bool(FLW_SECRET_KEY)


def _require_secret() -> str:
    if not FLW_SECRET_KEY:
        raise HTTPException(
            status_code=503,
            detail="Billing is not configured. Set FLW_SECRET_KEY.",
        )
    return FLW_SECRET_KEY


async def _request(
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    secret = _require_secret()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(
                method,
                f"{FLW_API_BASE}{path}",
                json=body,
                params=params,
                headers={
                    "Authorization": f"Bearer {secret}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
    except httpx.RequestError as exc:
        logger.warning("Flutterwave request failed: {}", exc)
        raise HTTPException(
            status_code=502, detail="Could not reach Flutterwave"
        ) from exc

    try:
        payload = response.json()
    except ValueError:
        payload = {}

    if response.status_code >= 400 or payload.get("status") == "error":
        message = payload.get("message") or response.text[:300]
        logger.warning(
            "Flutterwave {} {} returned {}: {}",
            method,
            path,
            response.status_code,
            message,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Flutterwave rejected the request: {message}",
        )
    return payload.get("data")


def new_tx_ref(organization_id: int, plan_code: str, billing_interval: str) -> str:
    suffix = uuid.uuid4().hex[:16]
    return f"dograh-{organization_id}-{plan_code}-{billing_interval}-{suffix}"


async def create_payment_plan(
    *, plan: Plan, currency: str, billing_interval: str, amount_major: int
) -> dict[str, Any]:
    duration = 120 if billing_interval == "monthly" else 10
    interval = "monthly" if billing_interval == "monthly" else "yearly"
    data = await _request(
        "POST",
        "/payment-plans",
        body={
            "amount": int(amount_major),
            "name": f"Dograh {plan.name} ({billing_interval}, {currency})",
            "interval": interval,
            "currency": currency,
            "duration": duration,
        },
    )
    if not isinstance(data, dict) or data.get("id") is None:
        raise HTTPException(
            status_code=502, detail="Flutterwave did not return a payment plan id"
        )
    return data


async def create_checkout(
    *,
    organization_id: int,
    plan: Plan,
    currency: str,
    billing_interval: str,
    amount_major: int,
    payment_plan_id: str | int,
    tx_ref: str,
    redirect_url: str,
    customer_email: str,
    customer_name: str | None = None,
) -> dict[str, Any]:
    customer: dict[str, Any] = {"email": customer_email}
    if customer_name:
        customer["name"] = customer_name
    data = await _request(
        "POST",
        "/payments",
        body={
            "tx_ref": tx_ref,
            "amount": int(amount_major),
            "currency": currency,
            "redirect_url": redirect_url,
            "payment_plan": int(payment_plan_id),
            "customer": customer,
            "customizations": {
                "title": f"Dograh {plan.name}",
                "description": f"{billing_interval.title()} subscription in {currency}",
            },
            "meta": {
                "organization_id": organization_id,
                "plan_code": plan.code,
                "billing_interval": billing_interval,
            },
            # Recurring payment plans require a card. Flutterwave filters
            # unsupported methods based on the selected currency.
            "payment_options": "card",
        },
    )
    if not isinstance(data, dict) or not data.get("link"):
        raise HTTPException(
            status_code=502, detail="Flutterwave did not return a checkout link"
        )
    return data


async def verify_transaction(transaction_id: str | int) -> dict[str, Any]:
    data = await _request("GET", f"/transactions/{transaction_id}/verify")
    if not isinstance(data, dict):
        raise HTTPException(
            status_code=502, detail="Flutterwave returned an invalid transaction"
        )
    return data


async def verify_by_reference(tx_ref: str) -> dict[str, Any]:
    data = await _request(
        "GET",
        "/transactions/verify_by_reference",
        params={"tx_ref": tx_ref},
    )
    if not isinstance(data, dict):
        raise HTTPException(
            status_code=502, detail="Flutterwave returned an invalid transaction"
        )
    return data


async def cancel_subscription(subscription_id: str | int) -> dict[str, Any]:
    data = await _request("PUT", f"/subscriptions/{subscription_id}/cancel")
    return data if isinstance(data, dict) else {}


async def find_subscription_id(
    *, email: str, plan_id: str | int | None = None
) -> str | None:
    params: dict[str, Any] = {"email": email, "status": "active"}
    if plan_id:
        params["plan"] = plan_id
    data = await _request("GET", "/subscriptions", params=params)
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict) and first.get("id") is not None:
            return str(first["id"])
    return None


def verify_webhook(payload: bytes, verif_hash: str | None) -> dict[str, Any]:
    if not FLW_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=503, detail="Flutterwave webhook is not configured"
        )
    if not verif_hash:
        raise HTTPException(status_code=400, detail="Missing verif-hash header")
    if not hmac.compare_digest(FLW_WEBHOOK_SECRET, verif_hash):
        raise HTTPException(status_code=400, detail="Invalid Flutterwave webhook hash")
    try:
        event = json.loads(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Invalid Flutterwave webhook payload"
        ) from exc
    if not isinstance(event, dict):
        raise HTTPException(
            status_code=400, detail="Invalid Flutterwave webhook payload"
        )
    return event

