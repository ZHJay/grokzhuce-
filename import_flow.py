"""L2 流程层：严格串行编排 Grok 账号导入。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable, Protocol, Sequence

from account_record import AccountRecord
from sub2api_client import Sub2APIError


class GrokAccountCreator(Protocol):
    def create_grok_from_sso(
        self, record: AccountRecord, *, group_id: int
    ) -> dict: ...


@dataclass(frozen=True, slots=True)
class ImportItem:
    line_number: int
    status: str
    account_id: int | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ImportSummary:
    items: tuple[ImportItem, ...]

    @property
    def created(self) -> int:
        return sum(item.status == "created" for item in self.items)

    @property
    def skipped(self) -> int:
        return sum(item.status == "skipped" for item in self.items)

    @property
    def failed(self) -> int:
        return sum(item.status == "failed" for item in self.items)

    def to_dict(self) -> dict:
        """Return a report contract containing no source credential fields."""
        return {
            "total": len(self.items),
            "created": self.created,
            "skipped": self.skipped,
            "failed": self.failed,
            "items": [asdict(item) for item in self.items],
        }


ProgressCallback = Callable[[ImportItem, int, int], None]


def _is_compliant_account(
    account: dict, *, group_id: int, account_name: str
) -> bool:
    group_ids = account.get("group_ids")
    credentials = account.get("credentials")
    model_mapping = (
        credentials.get("model_mapping") if isinstance(credentials, dict) else None
    )
    return (
        account.get("name") == account_name
        and account.get("platform") == "grok"
        and account.get("type") == "oauth"
        and isinstance(group_ids, list)
        and group_ids == [group_id]
        and isinstance(credentials, dict)
        and model_mapping in (None, {})
        and account.get("concurrency") == 10
        and account.get("priority") == 1
        and account.get("rate_multiplier") == 1
        and account.get("expires_at") is None
        and account.get("auto_pause_on_expired") is False
    )


def _account_id(account: dict) -> int | None:
    value = account.get("id")
    return value if isinstance(value, int) else None


def run_import(
    records: Sequence[AccountRecord],
    client: GrokAccountCreator,
    *,
    group_id: int,
    existing_accounts: dict[str, list[dict]],
    on_progress: ProgressCallback | None = None,
) -> ImportSummary:
    """Import serially and skip only a unique, fully compliant existing account.

    Timeout failures are intentionally not retried. A lost response could hide a
    successful upstream create, so a later full rerun must re-read server state.
    """
    items: list[ImportItem] = []
    total = len(records)
    for record in records:
        matches = existing_accounts.get(record.account_name, [])
        if len(matches) > 1:
            item = ImportItem(
                record.line_number,
                "failed",
                error="multiple existing accounts share requested name",
            )
        elif len(matches) == 1:
            account = matches[0]
            if _is_compliant_account(
                account,
                group_id=group_id,
                account_name=record.account_name,
            ):
                item = ImportItem(
                    record.line_number,
                    "skipped",
                    account_id=_account_id(account),
                )
            else:
                item = ImportItem(
                    record.line_number,
                    "failed",
                    account_id=_account_id(account),
                    error="existing account does not satisfy requested settings",
                )
        else:
            try:
                account = client.create_grok_from_sso(record, group_id=group_id)
                account_id = _account_id(account)
                if not _is_compliant_account(
                    account,
                    group_id=group_id,
                    account_name=record.account_name,
                ):
                    item = ImportItem(
                        record.line_number,
                        "failed",
                        account_id=account_id,
                        error="created account does not satisfy requested settings",
                    )
                else:
                    existing_accounts.setdefault(record.account_name, []).append(account)
                    item = ImportItem(
                        record.line_number, "created", account_id=account_id
                    )
            except Sub2APIError as exc:
                item = ImportItem(
                    record.line_number, "failed", error=str(exc)
                )
        items.append(item)
        if on_progress is not None:
            on_progress(item, len(items), total)
    return ImportSummary(tuple(items))
