from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordBearer
from jose import JWTError, jwt

from shared.auth.config import AuthSettings
from shared.constants import Role
from shared.models.user import CurrentUser

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="", auto_error=False)
http_bearer = HTTPBearer(auto_error=False)


def _decode_token(token: str, settings: AuthSettings) -> dict:
    payload = jwt.decode(
        token,
        settings.secret,
        algorithms=[settings.algorithm],
        issuer=settings.issuer,
        audience=settings.audience,
    )
    return payload


def _payload_to_user(payload: dict) -> CurrentUser:
    user_id = payload.get("sub")
    if not user_id:
        raise ValueError("Missing sub in token")
    email = payload.get("email") or ""
    roles_raw = payload.get("roles") or []
    roles = [Role(r) if isinstance(r, str) else r for r in roles_raw]
    return CurrentUser(id=UUID(user_id), email=email, roles=roles)


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
    settings: AuthSettings = Depends(lambda: AuthSettings()),
) -> CurrentUser | None:
    if not credentials or not credentials.credentials:
        return None
    token = credentials.credentials
    try:
        payload = _decode_token(token, settings)
        return _payload_to_user(payload)
    except (JWTError, ValueError, KeyError):
        return None


async def get_current_user_required(
    user: CurrentUser | None = Depends(get_current_user_optional),
) -> CurrentUser:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
