"""CloudFront signed URL / signed cookie generation.

Pure utility — no FastAPI imports. Requires the ``cryptography`` package.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

_cached_key: object | None = None


def _load_private_key(pem_path: str) -> object:
    pem_data = Path(pem_path).read_bytes()
    return serialization.load_pem_private_key(pem_data, password=None)


def _get_key(pem_path: str) -> object:
    global _cached_key
    if _cached_key is None:
        _cached_key = _load_private_key(pem_path)
    return _cached_key


def _rsa_sign(message: bytes, private_key: object) -> bytes:
    return private_key.sign(message, padding.PKCS1v15(), hashes.SHA1())  # type: ignore[union-attr]


def _make_policy(url: str, expires: datetime) -> str:
    epoch = int(expires.timestamp())
    policy = {
        "Statement": [{
            "Resource": url,
            "Condition": {"DateLessThan": {"AWS:EpochTime": epoch}},
        }],
    }
    return json.dumps(policy, separators=(",", ":"))


def _b64_cf(data: bytes) -> str:
    """CloudFront-safe base64: replace ``+``, ``=``, ``/``."""
    return (
        base64.b64encode(data)
        .decode()
        .replace("+", "-")
        .replace("=", "_")
        .replace("/", "~")
    )


def generate_signed_url(
    resource_url: str,
    key_pair_id: str,
    private_key_path: str,
    expiry_secs: int = 14400,
) -> str:
    """Generate a CloudFront signed URL with a canned policy."""
    if not key_pair_id or not private_key_path:
        return resource_url  # graceful fallback — unsigned URL in dev

    expires = datetime.now(timezone.utc) + timedelta(seconds=expiry_secs)
    policy = _make_policy(resource_url, expires)
    key = _get_key(private_key_path)
    signature = _rsa_sign(policy.encode(), key)
    epoch = int(expires.timestamp())
    sep = "&" if "?" in resource_url else "?"
    return (
        f"{resource_url}{sep}"
        f"Expires={epoch}&"
        f"Signature={_b64_cf(signature)}&"
        f"Key-Pair-Id={key_pair_id}"
    )


def generate_signed_cookies(
    resource_pattern: str,
    key_pair_id: str,
    private_key_path: str,
    expiry_secs: int = 14400,
) -> dict[str, str]:
    """Generate CloudFront signed cookies for HLS streaming.

    Returns cookie name → value dict:
    ``CloudFront-Policy``, ``CloudFront-Signature``, ``CloudFront-Key-Pair-Id``
    """
    if not key_pair_id or not private_key_path:
        return {}

    expires = datetime.now(timezone.utc) + timedelta(seconds=expiry_secs)
    policy = _make_policy(resource_pattern, expires)
    key = _get_key(private_key_path)
    signature = _rsa_sign(policy.encode(), key)

    return {
        "CloudFront-Policy": _b64_cf(policy.encode()),
        "CloudFront-Signature": _b64_cf(signature),
        "CloudFront-Key-Pair-Id": key_pair_id,
    }
