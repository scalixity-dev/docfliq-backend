"""
Global slowapi rate limiter.

Imported by auth/router.py for per-endpoint limits.  Mounted onto app.state in
main.py so slowapi middleware can find it.

Storage: Redis (same instance as session/cache).  Falls back to in-memory if
REDIS_URL is not set (useful in local dev without Redis).
"""
import os

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
)
