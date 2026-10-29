from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

import api.routes.auth as auth_routes
from api.schemas.auth import FirebaseAuthRequest
from api.services.auth import firebase as firebase_service


def _google_payload() -> dict:
    return {
        "sub": "firebase-uid-1",
        "email": "person@example.com",
        "email_verified": True,
        "name": "Person",
        "firebase": {"sign_in_provider": "google.com"},
    }


def test_firebase_verifier_requires_project(monkeypatch):
    monkeypatch.setattr(firebase_service, "FIREBASE_PROJECT_ID", None)
    with pytest.raises(HTTPException) as exc:
        firebase_service.verify_firebase_id_token("token")
    assert exc.value.status_code == 503


def test_firebase_verifier_accepts_google(monkeypatch):
    monkeypatch.setattr(firebase_service, "FIREBASE_PROJECT_ID", "demo-project")
    monkeypatch.setattr(
        firebase_service.google_id_token,
        "verify_firebase_token",
        lambda token, request, audience=None: _google_payload(),
    )
    payload = firebase_service.verify_firebase_id_token("token")
    assert payload["email"] == "person@example.com"


def test_firebase_verifier_rejects_phone_without_number(monkeypatch):
    monkeypatch.setattr(firebase_service, "FIREBASE_PROJECT_ID", "demo-project")
    monkeypatch.setattr(
        firebase_service.google_id_token,
        "verify_firebase_token",
        lambda token, request, audience=None: {
            "sub": "phone-uid",
            "firebase": {"sign_in_provider": "phone"},
        },
    )
    with pytest.raises(HTTPException) as exc:
        firebase_service.verify_firebase_id_token("token")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_firebase_login_respects_signup_disabled(monkeypatch):
    monkeypatch.setattr(auth_routes, "ENABLE_SIGNUP", False)
    monkeypatch.setattr(
        auth_routes, "verify_firebase_id_token", lambda token: _google_payload()
    )
    monkeypatch.setattr(
        auth_routes.db_client,
        "get_user_by_provider_id",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        auth_routes.db_client, "get_user_by_email", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        auth_routes.db_client, "get_user_by_phone", AsyncMock(return_value=None)
    )

    with pytest.raises(HTTPException) as exc:
        await auth_routes.firebase_login(
            FirebaseAuthRequest(id_token="firebase-token")
        )
    assert exc.value.status_code == 403

@pytest.mark.asyncio
async def test_firebase_login_creates_organization(monkeypatch):
    user = SimpleNamespace(
        id=7,
        provider_id="firebase_firebase-uid-1",
        email="person@example.com",
        phone_number=None,
        selected_organization_id=None,
    )
    org = SimpleNamespace(id=42)
    monkeypatch.setattr(
        auth_routes, "verify_firebase_id_token", lambda token: _google_payload()
    )
    monkeypatch.setattr(
        auth_routes.db_client,
        "get_or_create_firebase_user",
        AsyncMock(return_value=(user, True)),
    )
    monkeypatch.setattr(
        auth_routes.db_client,
        "get_or_create_organization_by_provider_id",
        AsyncMock(return_value=(org, True)),
    )
    monkeypatch.setattr(
        auth_routes.db_client, "add_user_to_organization", AsyncMock()
    )
    monkeypatch.setattr(
        auth_routes.db_client, "update_user_selected_organization", AsyncMock()
    )
    monkeypatch.setattr(
        auth_routes, "ensure_organization_bootstrapped", AsyncMock()
    )
    monkeypatch.setattr(auth_routes, "capture_event", lambda **kwargs: None)
    monkeypatch.setattr(
        auth_routes, "tenant_properties", AsyncMock(return_value={})
    )

    response = await auth_routes.firebase_login(
        FirebaseAuthRequest(id_token="firebase-token")
    )

    assert response.user.organization_id == 42
    assert response.user.provider_id == "firebase_firebase-uid-1"
    assert response.token
