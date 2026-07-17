"""L1 积木层：受限 origin、禁重定向的 credential-bearing JSON HTTP。"""

from __future__ import annotations

import http.client
import ipaddress
import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any


MAX_RESPONSE_BYTES = 1024 * 1024
SAFE_REASON_CODES = {
    "EMPTY_TOKEN",
    "FORBIDDEN",
    "INVALID_ADMIN_KEY",
    "INVALID_AUTH_HEADER",
    "INVALID_TOKEN",
    "TOKEN_EXPIRED",
    "TOKEN_REVOKED",
    "UNAUTHORIZED",
    "USER_INACTIVE",
    "USER_NOT_FOUND",
}


class Sub2APIError(RuntimeError):
    """A sanitized operational failure safe for logs and reports."""


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        """Credential-bearing requests never follow redirects."""
        return None


def _is_loopback(hostname: str) -> bool:
    if hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def validate_base_url(value: str) -> str:
    """Allow HTTPS origins or HTTP loopback, fixed at the Sub2API API root."""
    parsed = urllib.parse.urlsplit(value)
    try:
        hostname = parsed.hostname or ""
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid Sub2API base URL") from exc
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Sub2API base URL cannot contain credentials/query/fragment")
    if parsed.path.rstrip("/") != "/api/v1":
        raise ValueError("Sub2API base URL must end with /api/v1")
    if parsed.scheme not in {"http", "https"} or not hostname:
        raise ValueError("Sub2API base URL must use HTTP(S)")
    if parsed.scheme == "http" and not _is_loopback(hostname):
        raise ValueError("plain HTTP is restricted to loopback")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("invalid Sub2API port")
    return value.rstrip("/")


class SecureJSONTransport:
    def __init__(
        self,
        base_url: str,
        token_provider: Callable[[], str],
        *,
        opener: urllib.request.OpenerDirector | None = None,
    ) -> None:
        self.base_url = validate_base_url(base_url)
        self._token_provider = token_provider
        self._opener = opener or urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _NoRedirectHandler(),
        )

    @staticmethod
    def _read_bounded(stream) -> bytes:
        raw = stream.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise Sub2APIError("Sub2API response exceeded size limit")
        return raw

    @classmethod
    def _safe_http_reason(cls, exc: urllib.error.HTTPError) -> str:
        try:
            envelope = json.loads(cls._read_bounded(exc).decode("utf-8"))
        except (
            Sub2APIError,
            json.JSONDecodeError,
            OSError,
            UnicodeError,
            http.client.HTTPException,
        ):
            return "UNKNOWN"
        if not isinstance(envelope, dict):
            return "UNKNOWN"
        candidate = str(
            envelope.get("reason") or envelope.get("code") or ""
        ).strip().upper()
        return candidate if candidate in SAFE_REASON_CODES else "UNKNOWN"

    def __call__(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
        timeout: int,
    ) -> Any:
        token = self._token_provider()
        if not token:
            raise Sub2APIError("Admin token provider returned an empty token")
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "sub2api-grok-importer/1.1",
        }
        body = None
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":")).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=body, headers=headers, method=method
        )
        try:
            with self._opener.open(request, timeout=timeout) as response:
                raw = self._read_bounded(response)
        except urllib.error.HTTPError as exc:
            reason = self._safe_http_reason(exc)
            raise Sub2APIError(f"HTTP {exc.code} ({reason})") from None
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            http.client.HTTPException,
        ):
            raise Sub2APIError("Sub2API request transport failed") from None
        try:
            envelope = json.loads(raw)
        except (json.JSONDecodeError, UnicodeError):
            raise Sub2APIError("Sub2API returned invalid JSON") from None
        if not isinstance(envelope, dict) or envelope.get("code") != 0:
            raise Sub2APIError("Sub2API returned an unsuccessful envelope")
        return envelope.get("data")
