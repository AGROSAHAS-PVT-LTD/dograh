"""Local-currency price quotes for the SaaS plan catalog.

Flutterwave does not expose a simple display-rate API. Its FX endpoint is an
asynchronous request-for-quote intended for merchant trades, so we use a
public daily rate feed and add an explicit buffer. ``FX_RATES_JSON`` lets an
operator pin rates when the feed is unavailable or a fixed rate is preferred.
"""

import asyncio
import json
import math
import time
from typing import Any

import httpx
from fastapi import HTTPException
from loguru import logger

from api.constants import (
    FX_API_URL,
    FX_BUFFER_PERCENT,
    FX_CACHE_TTL_SECONDS,
    FX_RATES_JSON,
)
from api.services.saas.plans import Plan

# Currencies Flutterwave can collect in through Standard checkout. Some
# markets are card-only; Flutterwave filters the methods shown at checkout.
CURRENCY_COUNTRIES: dict[str, str] = {
    "NGN": "Nigeria",
    "USD": "United States / international",
    "GHS": "Ghana",
    "KES": "Kenya",
    "ZAR": "South Africa",
    "UGX": "Uganda",
    "RWF": "Rwanda",
    "TZS": "Tanzania",
    "XAF": "Central Africa",
    "XOF": "West Africa",
    "EGP": "Egypt",
    "MWK": "Malawi",
    "ZMW": "Zambia",
    "GBP": "United Kingdom",
    "EUR": "Europe",
}
SUPPORTED_CURRENCIES = tuple(CURRENCY_COUNTRIES)

# ISO 4217 currencies with no minor unit.
ZERO_DECIMAL_CURRENCIES = {"UGX", "RWF", "TZS", "XAF", "XOF"}

# Prices are rounded up to a familiar local increment.
ROUNDING_STEPS: dict[str, int] = {
    "NGN": 500,
    "GHS": 10,
    "KES": 100,
    "ZAR": 50,
    "UGX": 5_000,
    "RWF": 5_000,
    "TZS": 10_000,
    "XAF": 5_000,
    "XOF": 5_000,
    "EGP": 50,
    "MWK": 5_000,
    "ZMW": 100,
    "USD": 1,
    "GBP": 1,
    "EUR": 1,
}

CURRENCY_SYMBOLS: dict[str, str] = {
    "NGN": "₦",
    "USD": "$",
    "GHS": "GH₵",
    "KES": "KSh ",
    "ZAR": "R",
    "UGX": "USh ",
    "RWF": "FRw ",
    "TZS": "TSh ",
    "XAF": "FCFA ",
    "XOF": "CFA ",
    "EGP": "E£",
    "MWK": "MK ",
    "ZMW": "ZK ",
    "GBP": "£",
    "EUR": "€",
}

# Last-resort rates if the public feed is unreachable at startup. These are
# intentionally approximate: the buffer protects margin, and operators can
# override them with FX_RATES_JSON.
FALLBACK_USD_RATES: dict[str, float] = {
    "NGN": 1600.0,
    "GHS": 15.0,
    "KES": 130.0,
    "ZAR": 18.0,
    "UGX": 3800.0,
    "RWF": 1400.0,
    "TZS": 2700.0,
    "XAF": 600.0,
    "XOF": 600.0,
    "EGP": 48.0,
    "MWK": 1750.0,
    "ZMW": 27.0,
    "GBP": 0.79,
    "EUR": 0.92,
    "USD": 1.0,
}

_cache_rates: dict[str, float] | None = None
_cache_at: float = 0.0
_cache_lock = asyncio.Lock()


def currency_decimals(currency: str) -> int:
    return 0 if currency in ZERO_DECIMAL_CURRENCIES else 2


def _round_up(value: float, step: int) -> int:
    if step <= 1:
        return math.ceil(value)
    return math.ceil(value / step) * step


def format_amount(currency: str, amount_minor: int) -> str:
    decimals = currency_decimals(currency)
    amount = amount_minor / (10**decimals)
    symbol = CURRENCY_SYMBOLS.get(currency, f"{currency} ")
    return f"{symbol}{amount:,.0f}"


def _override_rates() -> dict[str, float]:
    if not FX_RATES_JSON:
        return {}
    try:
        parsed = json.loads(FX_RATES_JSON)
    except ValueError:
        logger.warning("FX_RATES_JSON is not valid JSON; ignoring it")
        return {}
    if not isinstance(parsed, dict):
        logger.warning("FX_RATES_JSON must be an object; ignoring it")
        return {}
    try:
        return {
            str(currency).upper(): float(rate)
            for currency, rate in parsed.items()
            if str(currency).upper() in CURRENCY_COUNTRIES and float(rate) > 0
        }
    except (TypeError, ValueError):
        logger.warning("FX_RATES_JSON has a non-numeric rate; ignoring it")
        return {}


async def _fetch_rates() -> dict[str, float]:
    overrides = _override_rates()
    rates = dict(FALLBACK_USD_RATES)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(FX_API_URL)
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
        if payload.get("result") not in (None, "success"):
            raise ValueError(payload.get("error-type") or "FX provider error")
        raw_rates = payload.get("rates")
        if not isinstance(raw_rates, dict):
            raise ValueError("FX provider returned no rates")
        for currency in CURRENCY_COUNTRIES:
            value = raw_rates.get(currency)
            if value is not None and float(value) > 0:
                rates[currency] = float(value)
        logger.info("Loaded {} FX rates from {}", len(rates), FX_API_URL)
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        logger.warning("Could not refresh FX rates ({}); using fallback rates", exc)
    rates.update(overrides)
    rates["USD"] = 1.0
    return rates


async def get_usd_rates(force_refresh: bool = False) -> dict[str, float]:
    global _cache_rates, _cache_at
    if (
        not force_refresh
        and _cache_rates is not None
        and time.monotonic() - _cache_at < FX_CACHE_TTL_SECONDS
    ):
        return _cache_rates
    async with _cache_lock:
        if (
            not force_refresh
            and _cache_rates is not None
            and time.monotonic() - _cache_at < FX_CACHE_TTL_SECONDS
        ):
            return _cache_rates
        _cache_rates = await _fetch_rates()
        _cache_at = time.monotonic()
        return _cache_rates


async def quote(plan: Plan, currency: str, billing_interval: str) -> dict[str, Any]:
    currency = (currency or "USD").upper()
    if currency not in CURRENCY_COUNTRIES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported billing currency: {currency}",
        )
    if billing_interval not in ("monthly", "annual"):
        raise HTTPException(
            status_code=400,
            detail="billing_interval must be 'monthly' or 'annual'",
        )

    usd_cents = plan.usd_cents(billing_interval)
    if currency == "USD":
        rate = 1.0
        buffer_percent = 0.0
        amount_major = usd_cents / 100
    else:
        rates = await get_usd_rates()
        rate = rates[currency]
        buffer_percent = FX_BUFFER_PERCENT
        amount_major = (usd_cents / 100) * rate * (1 + buffer_percent / 100)

    rounded = _round_up(amount_major, ROUNDING_STEPS[currency])
    amount_minor = int(rounded * (10 ** currency_decimals(currency)))
    return {
        "currency": currency,
        "country": CURRENCY_COUNTRIES[currency],
        "billing_interval": billing_interval,
        "base_usd_cents": usd_cents,
        "fx_rate": rate,
        "fx_buffer_percent": buffer_percent,
        "amount_major": rounded,
        "amount_minor": amount_minor,
        "price_display": format_amount(currency, amount_minor),
    }
