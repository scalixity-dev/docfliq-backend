"""
Media service — auth dependencies.

Re-exports the shared auth guards. All protected endpoints use these.
JWT tokens are issued by the Identity service (MS-1) and validated here
using the same shared secret.
"""
from shared.auth import get_current_user_required, get_current_user_optional

__all__ = ["get_current_user_required", "get_current_user_optional"]
