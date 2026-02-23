"""
Global slowapi rate limiter.

Storage: Redis (same instance as cache). Falls back to in-memory if
REDIS_URL is not set (useful in local dev without Redis).
"""
import os

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    enabled=os.getenv("ENV_NAME") != "development",
)
