from typing import Any

from pydantic import BaseModel, Field


class CheckoutRequest(BaseModel):
    plan_code: str
    currency: str = "USD"
    billing_interval: str = "monthly"
    success_url: str = Field(min_length=1)
    cancel_url: str = Field(min_length=1)


class CheckoutResponse(BaseModel):
    checkout_url: str
    tx_ref: str
    amount_minor: int
    currency: str
    price_display: str


class CheckoutVerifyRequest(BaseModel):
    tx_ref: str = Field(min_length=1)


class PortalRequest(BaseModel):
    return_url: str = Field(min_length=1)


class PortalResponse(BaseModel):
    url: str


class CancelResponse(BaseModel):
    message: str
    cancel_at_period_end: bool


class SubscriptionResponse(BaseModel):
    entitlements: dict[str, Any]
