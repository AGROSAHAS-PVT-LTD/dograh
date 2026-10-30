import json

import pytest
from fastapi import HTTPException

from api.services.saas import flutterwave_client, fx
from api.services.saas.plans import PLANS, configured_plans, get_plan


def test_public_plans_are_ordered_and_limited():
    plans = configured_plans()
    assert [plan.code for plan in plans] == ["starter", "growth", "scale"]
    assert plans[0].limits["agents"] < plans[1].limits["agents"]
    assert plans[1].limits["seats"] < plans[2].limits["seats"]


def test_unknown_plan_returns_404():
    with pytest.raises(HTTPException) as exc:
        get_plan("does-not-exist")
    assert exc.value.status_code == 404


def test_annual_prices_include_discount():
    plan = PLANS["starter"]
    assert plan.usd_cents("monthly") == 4900
    assert plan.usd_cents("annual") < plan.usd_cents("monthly") * 12


def test_flutterwave_webhook_accepts_matching_secret_hash(monkeypatch):
    monkeypatch.setattr(flutterwave_client, "FLW_WEBHOOK_SECRET", "flw_secret")
    payload = json.dumps(
        {"event": "charge.completed", "data": {"id": 123, "status": "successful"}}
    ).encode()

    event = flutterwave_client.verify_webhook(payload, "flw_secret")
    assert event["data"]["id"] == 123


def test_flutterwave_webhook_rejects_bad_hash(monkeypatch):
    monkeypatch.setattr(flutterwave_client, "FLW_WEBHOOK_SECRET", "flw_secret")
    with pytest.raises(HTTPException) as exc:
        flutterwave_client.verify_webhook(b'{"event":"charge.completed"}', "wrong")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_local_quote_adds_buffer_and_rounds(monkeypatch):
    async def fake_rates():
        return {"USD": 1.0, "NGN": 1000.0}

    monkeypatch.setattr(fx, "get_usd_rates", fake_rates)
    monkeypatch.setattr(fx, "FX_BUFFER_PERCENT", 10.0)
    quote = await fx.quote(PLANS["starter"], "NGN", "monthly")
    # $49 * 1000 * 1.10 = 53,900 NGN, rounded up to the next 500.
    assert quote["amount_major"] == 54_000
    assert quote["amount_minor"] == 5_400_000
    assert quote["currency"] == "NGN"
    assert "₦" in quote["price_display"]


def test_plan_lookup_uses_catalog():
    for code, plan in PLANS.items():
        assert plan.code == code
        assert plan.limits["agents"] >= 1
