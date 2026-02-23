"""
Identity service — OAuth 2.0 provider integration (Google + Microsoft).

Handles the server-side authorization code exchange and user-info retrieval
for the OAuth Authorization Code flow. Uses httpx (already a project dep)
rather than authlib to avoid adding another dependency.

Flow:
  1. Frontend constructs OAuth authorize URL and redirects the user.
  2. Provider redirects back to the frontend callback page with ?code=...
  3. Frontend POSTs { code, redirect_uri } to our /auth/oauth/<provider> endpoint.
  4. This module exchanges the code for tokens, fetches user profile info,
     and returns a normalized OAuthUserInfo dataclass.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.exceptions import InvalidCredentials


# ── Normalized user info returned by both providers ─────────────────────────

@dataclass(frozen=True, slots=True)
class OAuthUserInfo:
    provider: str           # "google" | "microsoft"
    provider_id: str        # Unique ID from the provider (sub / oid)
    email: str
    full_name: str
    picture_url: str | None
    email_verified: bool


# ── Google ──────────────────────────────────────────────────────────────────

_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


async def exchange_google_code(
    *,
    code: str,
    redirect_uri: str,
    client_id: str,
    client_secret: str,
) -> OAuthUserInfo:
    """
    Exchange a Google authorization code for user info.

    Raises InvalidCredentials on any failure (bad code, network error, etc.)
    so the caller doesn't need provider-specific error handling.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. Exchange code → tokens
        token_resp = await client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            raise InvalidCredentials()

        tokens = token_resp.json()
        access_token = tokens.get("access_token")
        if not access_token:
            raise InvalidCredentials()

        # 2. Fetch user profile
        info_resp = await client.get(
            _GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if info_resp.status_code != 200:
            raise InvalidCredentials()

        info = info_resp.json()
        email = info.get("email")
        sub = info.get("sub")
        if not email or not sub:
            raise InvalidCredentials()

        return OAuthUserInfo(
            provider="google",
            provider_id=sub,
            email=email,
            full_name=info.get("name") or email.split("@")[0],
            picture_url=info.get("picture"),
            email_verified=info.get("email_verified", False),
        )


# ── Microsoft ───────────────────────────────────────────────────────────────

_MICROSOFT_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
_MICROSOFT_GRAPH_ME_URL = "https://graph.microsoft.com/v1.0/me"


async def exchange_microsoft_code(
    *,
    code: str,
    redirect_uri: str,
    client_id: str,
    client_secret: str,
) -> OAuthUserInfo:
    """
    Exchange a Microsoft authorization code for user info.

    Uses the /common tenant so both personal Microsoft accounts and
    Azure AD work/school accounts are accepted.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. Exchange code → tokens
        token_resp = await client.post(
            _MICROSOFT_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "scope": "openid email profile User.Read",
            },
        )
        if token_resp.status_code != 200:
            raise InvalidCredentials()

        tokens = token_resp.json()
        access_token = tokens.get("access_token")
        if not access_token:
            raise InvalidCredentials()

        # 2. Fetch user profile from MS Graph
        info_resp = await client.get(
            _MICROSOFT_GRAPH_ME_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if info_resp.status_code != 200:
            raise InvalidCredentials()

        info = info_resp.json()
        # Microsoft Graph returns mail or userPrincipalName
        email = info.get("mail") or info.get("userPrincipalName")
        ms_id = info.get("id")
        if not email or not ms_id:
            raise InvalidCredentials()

        return OAuthUserInfo(
            provider="microsoft",
            provider_id=ms_id,
            email=email,
            full_name=info.get("displayName") or email.split("@")[0],
            picture_url=None,  # MS Graph photo requires a separate call
            email_verified=True,  # Microsoft accounts always have verified emails
        )
