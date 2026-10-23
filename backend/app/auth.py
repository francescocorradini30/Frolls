"""Accounts: sessions, Discord and Google sign-in, and the development sign-in.

A session is an opaque random token. The browser keeps it in an httpOnly cookie (OAuth
sign-in) or, with the development sign-in, in the tab's sessionStorage, sent as a Bearer
header and in the WebSocket hello: so every tab can be a different test user. Only the
token's sha256 is stored.
"""

import hashlib
import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx2
from fastapi import HTTPException, Request, WebSocket
from sqlalchemy import delete, select

from app.config import settings
from app.db import session_scope
from app.models import AuthIdentity, AuthSession, User

COOKIE = "frolls_session"
STATE_COOKIE = "frolls_oauth"


@dataclass(frozen=True)
class Provider:
    name: str
    authorize_url: str
    token_url: str
    profile_url: str
    scope: str

    @property
    def client_id(self) -> str:
        return getattr(settings, f"{self.name}_client_id")

    @property
    def client_secret(self) -> str:
        return getattr(settings, f"{self.name}_client_secret")

    @property
    def enabled(self) -> bool:
        return bool(self.client_id and self.client_secret)

    @property
    def redirect_uri(self) -> str:
        return f"{settings.public_url.rstrip('/')}/api/auth/{self.name}/callback"


PROVIDERS = {
    "discord": Provider(
        "discord",
        "https://discord.com/oauth2/authorize",
        "https://discord.com/api/oauth2/token",
        "https://discord.com/api/users/@me",
        "identify email",
    ),
    "google": Provider(
        "google",
        "https://accounts.google.com/o/oauth2/v2/auth",
        "https://oauth2.googleapis.com/token",
        "https://openidconnect.googleapis.com/v1/userinfo",
        "openid email profile",
    ),
}


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_session(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(UTC) + timedelta(days=settings.session_days)
    async with session_scope() as s:
        s.add(AuthSession(token_hash=_hash(token), user_id=user_id, expires_at=expires))
    return token


async def end_session(token: str) -> None:
    async with session_scope() as s:
        await s.execute(delete(AuthSession).where(AuthSession.token_hash == _hash(token)))


async def user_for_token(token: str | None) -> User | None:
    if not token:
        return None
    async with session_scope() as s:
        row = await s.get(AuthSession, _hash(token))
        if row is None or row.expires_at < datetime.now(UTC):
            return None
        return await s.get(User, row.user_id)


def token_of(request: Request | WebSocket) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return request.cookies.get(COOKIE)


async def current_user(request: Request) -> User:
    """FastAPI dependency: the signed-in user, or 401."""
    user = await user_for_token(token_of(request))
    if user is None:
        raise HTTPException(401, "sign in first")
    return user


async def user_for_identity(
    provider: str, subject: str, name: str, email: str | None, avatar: str | None
) -> User:
    """The user behind a sign-in, created on the first one."""
    async with session_scope() as s:
        identity = await s.get(AuthIdentity, (provider, subject))
        if identity is not None:
            user = await s.get(User, identity.user_id)
            assert user is not None
            if avatar and not user.avatar_url:
                user.avatar_url = avatar
            return user
        user = User(id=str(uuid.uuid4()), name=name[:60] or "Adventurer", email=email)
        user.avatar_url = avatar
        s.add(user)
        await s.flush()
        s.add(AuthIdentity(provider=provider, subject=subject, user_id=user.id))
        return user


# --- OAuth -----------------------------------------------------------------------


def authorize_url(provider: Provider, state: str) -> str:
    params = {
        "client_id": provider.client_id,
        "redirect_uri": provider.redirect_uri,
        "response_type": "code",
        "scope": provider.scope,
        "state": state,
    }
    if provider.name == "google":
        params["prompt"] = "select_account"
    return f"{provider.authorize_url}?{urlencode(params)}"


def new_state(next_path: str) -> tuple[str, str]:
    """(state for the provider, value of the state cookie)."""
    state = secrets.token_urlsafe(24)
    safe_next = next_path if next_path.startswith("/") and not next_path.startswith("//") else "/"
    return state, json.dumps({"state": state, "next": safe_next})


def check_state(cookie: str | None, state: str) -> str:
    """The path to go back to, if the state matches the cookie set at the start."""
    try:
        data = json.loads(cookie or "")
    except ValueError:
        data = {}
    if not state or not secrets.compare_digest(str(data.get("state", "")), state):
        raise HTTPException(400, "sign-in expired, please try again")
    return str(data.get("next") or "/")


async def oauth_profile(provider: Provider, code: str) -> tuple[str, str, str | None, str | None]:
    """Exchange the code for the user's (subject, name, email, avatar URL)."""
    async with httpx2.AsyncClient(timeout=10) as client:
        token = await client.post(
            provider.token_url,
            data={
                "client_id": provider.client_id,
                "client_secret": provider.client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": provider.redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        if token.status_code != 200:
            raise HTTPException(400, "sign-in failed")
        access = token.json()["access_token"]
        profile = await client.get(
            provider.profile_url, headers={"Authorization": f"Bearer {access}"}
        )
        if profile.status_code != 200:
            raise HTTPException(400, "sign-in failed")
        data = profile.json()
    if provider.name == "discord":
        avatar = (
            f"https://cdn.discordapp.com/avatars/{data['id']}/{data['avatar']}.png"
            if data.get("avatar")
            else None
        )
        name = data.get("global_name") or data.get("username") or "Adventurer"
        return str(data["id"]), name, data.get("email"), avatar
    return (
        str(data["sub"]),
        data.get("name") or "Adventurer",
        data.get("email"),
        data.get("picture"),
    )


async def delete_user(user_id: str) -> None:
    """Right to erasure: the account, its sign-ins and sessions. Game data is handled by
    the caller (players are anonymised there)."""
    async with session_scope() as s:
        user = await s.get(User, user_id)
        if user is not None:
            await s.delete(user)


async def sessions_of(user_id: str) -> int:
    async with session_scope() as s:
        rows = await s.scalars(select(AuthSession).where(AuthSession.user_id == user_id))
        return len(list(rows))
