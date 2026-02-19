"""
Identity service — auth-specific FastAPI dependencies.

These wrap the shared auth dependencies and add identity-service context
(e.g. role guards, verification gates).
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from shared.auth.dependencies import (
    get_current_user_optional,
    get_current_user_required,
)
from shared.models.user import CurrentUser


# ── Base user dependencies ────────────────────────────────────────────────────

# Alias the shared dependencies so routes import from here, not from shared
# directly.  If we ever need to augment them (e.g. DB lookup), only this
# file changes.
get_current_user = get_current_user_required
get_optional_user = get_current_user_optional


# ── Role guards ───────────────────────────────────────────────────────────────

from shared.constants import Role
from app.exceptions import UserInactive


def require_admin(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Raise 403 unless the authenticated user holds the ADMIN or SUPER_ADMIN role."""
    allowed = {Role.ADMIN.value, Role.SUPER_ADMIN.value}
    if not any(r in allowed for r in current_user.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required.",
        )
    return current_user


def require_super_admin(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Raise 403 unless the user holds SUPER_ADMIN."""
    if Role.SUPER_ADMIN.value not in current_user.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super-administrator access required.",
        )
    return current_user
