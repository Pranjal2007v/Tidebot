"""Verify incoming GitHub webhook deliveries.

GitHub signs each delivery with HMAC-SHA256 over the raw request body and
sends the result in the ``X-Hub-Signature-256`` header as ``sha256=<hex>``.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Optional

SIGNATURE_PREFIX = "sha256="


def sign(secret: str, body: bytes) -> str:
    """Return the ``X-Hub-Signature-256`` value GitHub would send for ``body``."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return SIGNATURE_PREFIX + digest


def verify_signature(secret: str, body: bytes, header: Optional[str]) -> bool:
    """Check ``header`` against ``body`` in constant time.

    Returns False for a missing secret, a missing header or a header that
    doesn't use the sha256 scheme.
    """
    if not secret or not header or not header.startswith(SIGNATURE_PREFIX):
        return False
    return hmac.compare_digest(sign(secret, body), header)
