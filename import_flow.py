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


def run_import(
    records: Sequence[AccountRecord],
    client: GrokAccountCreator,
    *,
    group_id: int,
    existing_names: set[str],
    on_progress: ProgressCallback | None = None,
) -> ImportSummary:
    """Import with a synchronous loop; no next request starts before return.

    Timeout failures are intentionally not retried. A lost response could hide a
    successful upstream create, so a later full rerun must re-check server names.
    """
    items: list[ImportItem] = []
    total = len(records)
    for record in records:
        if record.account_name in existing_names:
            item = ImportItem(record.line_number, "skipped")
        else:
            try:
                account = client.create_grok_from_sso(record, group_id=group_id)
                account_id = account.get("id")
                existing_names.add(record.account_name)
                if account.get("expires_at") is not None:
                    item = ImportItem(
                        record.line_number,
                        "failed",
                        account_id=account_id,
                        error="created account has an expiry",
                    )
                else:
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
