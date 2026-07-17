"""L1 积木层：Sub2API Admin HTTP 的单次操作封装。"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from account_record import AccountRecord


class Sub2APIError(RuntimeError):
    """A sanitized operational failure safe for logs and reports."""


Transport = Callable[[str, str, dict[str, Any] | None, int], Any]


class Sub2APIClient:
    def __init__(
        self,
        base_url: str,
        admin_jwt: str,
        *,
        timeout: int = 180,
        transport: Transport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._admin_jwt = admin_jwt
        self.timeout = timeout
        self._transport = transport or self._http_transport

    def _http_transport(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
        timeout: int,
    ) -> Any:
        body = None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._admin_jwt}",
            "User-Agent": "sub2api-grok-importer/1.0",
        }
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":")).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=body, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                envelope = json.load(response)
        except urllib.error.HTTPError as exc:
            reason = self._safe_http_reason(exc)
            raise Sub2APIError(f"HTTP {exc.code} ({reason})") from None
        except (urllib.error.URLError, TimeoutError):
            raise Sub2APIError("Sub2API request transport failed") from None
        except (json.JSONDecodeError, ValueError):
            raise Sub2APIError("Sub2API returned invalid JSON") from None

        if not isinstance(envelope, dict) or envelope.get("code") != 0:
            raise Sub2APIError("Sub2API returned an unsuccessful envelope")
        return envelope.get("data")

    @staticmethod
    def _safe_http_reason(exc: urllib.error.HTTPError) -> str:
        try:
            envelope = json.loads(exc.read().decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError, UnicodeError):
            return "UNKNOWN"
        candidate = str(envelope.get("reason", "")).strip().upper()
        return candidate if re.fullmatch(r"[A-Z0-9_]{1,80}", candidate) else "UNKNOWN"

    def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> Any:
        return self._transport(method, path, payload, self.timeout)

    def get_grok_group_id(self) -> int:
        groups = self._request("GET", "/admin/groups/all?platform=grok")
        if not isinstance(groups, list):
            raise Sub2APIError("Grok group response is invalid")
        matches = [
            group
            for group in groups
            if isinstance(group, dict)
            and group.get("name") == "Grok"
            and group.get("platform") == "grok"
            and group.get("status", "active") == "active"
        ]
        if len(matches) != 1 or not isinstance(matches[0].get("id"), int):
            raise Sub2APIError("expected exactly one active Grok group")
        return matches[0]["id"]

    def list_existing_grok_names(self) -> set[str]:
        names: set[str] = set()
        page = 1
        while True:
            data = self._request(
                "GET", f"/admin/accounts?page={page}&page_size=100&platform=grok"
            )
            if not isinstance(data, dict) or not isinstance(data.get("items"), list):
                raise Sub2APIError("Grok account list response is invalid")
            for account in data["items"]:
                if isinstance(account, dict) and isinstance(account.get("name"), str):
                    names.add(account["name"])
            pages = data.get("pages", 1)
            if not isinstance(pages, int) or page >= pages:
                return names
            page += 1

    def create_grok_from_sso(
        self, record: AccountRecord, *, group_id: int
    ) -> dict[str, Any]:
        """Create exactly one account; one-element input preserves seriality."""
        payload = {
            "sso_tokens": [record.sso],
            "name": record.account_name,
            "group_ids": [group_id],
            "credentials": {},
            "concurrency": 10,
            "priority": 1,
            "rate_multiplier": 1,
            "expires_at": None,
            "auto_pause_on_expired": False,
        }
        result = self._request("POST", "/admin/grok/sso-to-oauth", payload)
        if not isinstance(result, dict):
            raise Sub2APIError("Grok SSO conversion returned invalid data")
        created = result.get("created")
        failed = result.get("failed")
        if not isinstance(created, list) or not isinstance(failed, list):
            raise Sub2APIError("Grok SSO conversion returned invalid data")
        if len(created) != 1 or failed:
            raise Sub2APIError("Grok SSO conversion failed")
        account = created[0].get("account") if isinstance(created[0], dict) else None
        if not isinstance(account, dict) or not isinstance(account.get("id"), int):
            raise Sub2APIError("Grok SSO conversion omitted the created account")
        return account
