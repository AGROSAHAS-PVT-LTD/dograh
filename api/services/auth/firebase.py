"""Verify Firebase Authentication ID tokens on the API.

The browser performs Google popup sign-in and phone OTP verification with the
Firebase JS SDK. The resulting ID token is exchanged here for a Dograh JWT, so
all existing API authorization continues to use the local token model.
"""

from typing import Any

from fastapi import HTTPException
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from loguru import logger

from api.constants import FIREBASE_PROJECT_ID


def verify_firebase_id_token(token: str) -> dict[str, Any]:
    if not FIREBASE_PROJECT_ID:
        raise HTTPException(
            status_code=503,
            detail="Firebase authentication is not configured. Set FIREBASE_PROJECT_ID.",
        )
    try:
        payload = google_id_token.verify_firebase_token(
            token,
            google_requests.Request(),
            audience=FIREBASE_PROJECT_ID,
        )
    except Exception as exc:
        logger.warning("Firebase ID token verification failed: {}", exc)
        raise HTTPException(
            status_code=401, detail="Invalid or expired Firebase token"
        ) from exc

    if not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Firebase token has no subject")
    firebase = payload.get("firebase")
    provider = firebase.get("sign_in_provider") if isinstance(firebase, dict) else None
    if provider not in ("google.com", "phone"):
        raise HTTPException(
            status_code=401, detail="Unsupported Firebase sign-in provider"
        )
    if provider == "google.com" and not payload.get("email_verified"):
        raise HTTPException(status_code=401, detail="Google email is not verified")
    if provider == "phone" and not payload.get("phone_number"):
        raise HTTPException(
            status_code=401, detail="Firebase token has no phone number"
        )
    return dict(payload)
