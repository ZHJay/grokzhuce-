"""L1 积木层：Sub2API Admin HTTP 的单次操作封装。"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from account_record import AccountRecord
from http_json import SecureJSONTransport, Sub2APIError


Transport = Callable[[str, str, dict[str, Any] | None, int], Any]


class Sub2APIClient:
    def __init__(
        self,
        base_url: str,
        admin_jwt: str | Callable[[], str],
        *,
        timeout: int = 180,
        transport: Transport | None = None,
    ) -> None:
        self.timeout = timeout
        if transport is not None:
            self._transport = transport
        else:
            token_provider = (
                admin_jwt if callable(admin_jwt) else lambda: admin_jwt
            )
            self._transport = SecureJSONTransport(base_url, token_provider)

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
            reason = ""
            if failed and isinstance(failed[0], dict):
                error_text = str(failed[0].get("error", ""))
                match = re.match(r"^([A-Z][A-Z0-9_]{1,79}):", error_text)
                if match:
                    reason = f" ({match.group(1)})"
            raise Sub2APIError(f"Grok SSO conversion failed{reason}")
        account = created[0].get("account") if isinstance(created[0], dict) else None
        if not isinstance(account, dict) or not isinstance(account.get("id"), int):
            raise Sub2APIError("Grok SSO conversion omitted the created account")
        return account
