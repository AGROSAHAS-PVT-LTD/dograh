from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from api.constants import ENABLE_SIGNUP
from api.db import db_client
from api.db.models import UserModel
from api.enums import OrganizationRole, PostHogEvent
from api.schemas.auth import (
    AuthResponse,
    FirebaseAuthRequest,
    LoginRequest,
    SignupRequest,
    UserResponse,
)
from api.services.auth.depends import get_user, require_local_auth
from api.services.auth.firebase import verify_firebase_id_token
from api.services.organization_bootstrap import ensure_organization_bootstrapped
from api.services.posthog_client import capture_event
from api.services.posthog_tenant import tenant_properties
from api.utils.auth import create_jwt_token, hash_password, verify_password

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


@router.post(
    "/signup",
    response_model=AuthResponse,
    dependencies=[Depends(require_local_auth)],
)
async def signup(request: SignupRequest):
    if not ENABLE_SIGNUP:
        raise HTTPException(status_code=403, detail="Signup is disabled")

    # Check if email is already taken
    existing_user = await db_client.get_user_by_email(request.email)
    if existing_user:
        raise HTTPException(status_code=409, detail="Email already registered")

    # Hash password and create user
    hashed = hash_password(request.password)
    user = await db_client.create_user_with_email(
        email=request.email,
        password_hash=hashed,
        name=request.name,
    )

    # Create organization for the user
    org_provider_id = f"org_{user.provider_id}"
    organization, _ = await db_client.get_or_create_organization_by_provider_id(
        org_provider_id=org_provider_id, user_id=user.id
    )

    # Link user to organization
    await db_client.add_user_to_organization(
        user.id, organization.id, role=OrganizationRole.OWNER
    )
    await db_client.update_user_selected_organization(user.id, organization.id)

    # Create default service configuration. This never raises, so signup still
    # succeeds if MPS is down; `_handle_oss_auth` re-enters bootstrap on the
    # user's subsequent authenticated requests, so a failure here is recovered
    # rather than permanent. Doing it here anyway means the common case has a
    # model configuration and SIP connectivity by the time the UI first loads.
    await ensure_organization_bootstrapped(
        organization.id,
        created_by=user.provider_id,
    )

    # Create JWT token
    token = create_jwt_token(user.id, request.email)

    capture_event(
        distinct_id=str(user.provider_id),
        event=PostHogEvent.SIGNED_UP,
        properties={
            **await tenant_properties(organization.id),
            "auth_provider": "local",
        },
    )

    return AuthResponse(
        token=token,
        user=UserResponse(
            id=user.id,
            email=user.email,
            name=request.name,
            organization_id=organization.id,
            provider_id=user.provider_id,
        ),
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    dependencies=[Depends(require_local_auth)],
)
async def login(request: LoginRequest):
    # Look up user by email
    user = await db_client.get_user_by_email(request.email)
    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Verify password
    if not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Create JWT token
    token = create_jwt_token(user.id, user.email)

    capture_event(
        distinct_id=str(user.provider_id),
        event=PostHogEvent.SIGNED_IN,
        properties={
            **await tenant_properties(user.selected_organization_id),
            "auth_provider": "local",
        },
    )

    return AuthResponse(
        token=token,
        user=UserResponse(
            id=user.id,
            email=user.email,
            organization_id=user.selected_organization_id,
            provider_id=user.provider_id,
        ),
    )


@router.post(
    "/firebase",
    response_model=AuthResponse,
    dependencies=[Depends(require_local_auth)],
)
async def firebase_login(request: FirebaseAuthRequest):
    """Exchange a verified Firebase ID token for a Dograh session.

    Firebase performs Google OAuth and phone/SMS OTP verification in the
    browser. We still verify the ID token here, then create/link the local user
    and issue the same JWT used by email/password sign-in.
    """
    payload = await run_in_threadpool(verify_firebase_id_token, request.id_token)
    firebase = payload.get("firebase") or {}
    sign_in_provider = firebase.get("sign_in_provider")
    email = payload.get("email")
    phone_number = payload.get("phone_number")
    provider_id = f"firebase_{payload['sub']}"
    display_name = payload.get("name")

    if not ENABLE_SIGNUP:
        existing = await db_client.get_user_by_provider_id(provider_id)
        if existing is None and email:
            existing = await db_client.get_user_by_email(email)
        if existing is None and phone_number:
            existing = await db_client.get_user_by_phone(phone_number)
        if existing is None:
            raise HTTPException(status_code=403, detail="Signup is disabled")

    user, created = await db_client.get_or_create_firebase_user(
        provider_id=provider_id,
        email=email,
        phone_number=phone_number,
    )

    organization_id = user.selected_organization_id
    if organization_id is None:
        organization = await db_client.get_or_create_organization_by_provider_id(
            org_provider_id=f"org_{user.provider_id}",
            user_id=user.id,
        )
        organization = organization[0]
        await db_client.add_user_to_organization(
            user.id, organization.id, role=OrganizationRole.OWNER
        )
        await db_client.update_user_selected_organization(user.id, organization.id)
        organization_id = organization.id
        await ensure_organization_bootstrapped(
            organization.id,
            created_by=user.provider_id,
        )

    token = create_jwt_token(
        user.id,
        user.email or user.phone_number or user.provider_id,
    )

    auth_provider = (
        "firebase_google" if sign_in_provider == "google.com" else "firebase_phone"
    )
    capture_event(
        distinct_id=str(user.provider_id),
        event=PostHogEvent.SIGNED_UP if created else PostHogEvent.SIGNED_IN,
        properties={
            **await tenant_properties(organization_id),
            "auth_provider": auth_provider,
        },
    )

    return AuthResponse(
        token=token,
        user=UserResponse(
            id=user.id,
            email=user.email,
            name=display_name,
            organization_id=organization_id,
            provider_id=user.provider_id,
        ),
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user(user: UserModel = Depends(get_user)):
    return UserResponse(
        id=user.id,
        email=user.email,
        organization_id=user.selected_organization_id,
        provider_id=user.provider_id,
    )
