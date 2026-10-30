from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

import api.routes.auth as auth_routes
from api.schemas.auth import PasswordResetConfirm, PasswordResetRequest
from api.utils.auth import verify_password


@pytest.mark.asyncio
async def test_password_reset_request_is_generic_for_unknown_email(monkeypatch):
    monkeypatch.setattr(
        auth_routes.db_client, "get_user_by_email", AsyncMock(return_value=None)
    )
    response = await auth_routes.request_password_reset(
        PasswordResetRequest(email="missing@example.com")
    )
    assert "If an account exists" in response["message"]


@pytest.mark.asyncio
async def test_password_reset_rejects_expired_token(monkeypatch):
    record = SimpleNamespace(
        id=1,
        user_id=7,
        used_at=None,
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    monkeypatch.setattr(
        auth_routes.db_client,
        "get_password_reset_token",
        AsyncMock(return_value=record),
    )
    with pytest.raises(HTTPException) as exc:
        await auth_routes.reset_password(
            PasswordResetConfirm(token="x" * 32, password="newpassword")
        )
    assert exc.value.status_code == 410


@pytest.mark.asyncio
async def test_password_reset_updates_hash_and_consumes_token(monkeypatch):
    record = SimpleNamespace(
        id=1,
        user_id=7,
        used_at=None,
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    consume = AsyncMock(return_value=True)
    update = AsyncMock()
    monkeypatch.setattr(
        auth_routes.db_client,
        "get_password_reset_token",
        AsyncMock(return_value=record),
    )
    monkeypatch.setattr(auth_routes.db_client, "consume_password_reset_token", consume)
    monkeypatch.setattr(auth_routes.db_client, "update_user_password", update)

    response = await auth_routes.reset_password(
        PasswordResetConfirm(token="x" * 32, password="newpassword")
    )

    assert response["message"].startswith("Password updated")
    consume.assert_awaited_once_with(1)
    user_id, password_hash = update.await_args.args
    assert user_id == 7
    assert verify_password("newpassword", password_hash)
