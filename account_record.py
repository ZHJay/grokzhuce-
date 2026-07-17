"""L0 公理层：定义 Grok 导入记录及其不可变校验契约。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


class RecordValidationError(ValueError):
    """输入文件不满足三字段、非空及唯一性契约。"""


@dataclass(frozen=True, slots=True)
class AccountRecord:
    line_number: int
    email: str
    password: str
    sso: str

    @property
    def account_name(self) -> str:
        """Return the exact account name requested by the operator."""
        return f"{self.email}|{self.password}"


def parse_account_records(lines: Iterable[str]) -> list[AccountRecord]:
    """Parse all records before any external write occurs.

    Contract: every nonblank line is ``email|password|sso``; email and SSO
    values are unique across the whole file. Error messages never include field
    values because all three fields are sensitive in this workflow.
    """
    records: list[AccountRecord] = []
    email_lines: dict[str, int] = {}
    sso_lines: dict[str, int] = {}

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue

        parts = [part.strip() for part in line.split("|", 2)]
        if len(parts) != 3 or any(not part for part in parts):
            raise RecordValidationError(
                f"line {line_number}: expected three non-empty fields"
            )

        email, password, sso = parts
        if "@" not in email or any(char.isspace() for char in email):
            raise RecordValidationError(f"line {line_number}: invalid email")
        # Sub2API v0.1.156 expands these inside one list item before starting
        # workers, which would violate the one-record/one-create invariant.
        if any(delimiter in sso for delimiter in (",", "\r", "\n")):
            raise RecordValidationError(
                f"line {line_number}: SSO contains a server-side delimiter"
            )

        email_key = email.casefold()
        if email_key in email_lines:
            raise RecordValidationError(
                f"line {line_number}: duplicate email from line {email_lines[email_key]}"
            )
        if sso in sso_lines:
            raise RecordValidationError(
                f"line {line_number}: duplicate SSO from line {sso_lines[sso]}"
            )

        email_lines[email_key] = line_number
        sso_lines[sso] = line_number
        records.append(AccountRecord(line_number, email, password, sso))

    if not records:
        raise RecordValidationError("input contains no account records")
    return records


def format_account_record(email: str, password: str, sso: str) -> str:
    """Serialize one registration result only if it round-trips losslessly."""
    line = f"{email}|{password}|{sso}"
    file_lines = line.splitlines()
    if len(file_lines) != 1:
        raise RecordValidationError("record fields cannot round-trip safely")
    parsed = parse_account_records(file_lines)[0]
    if (parsed.email, parsed.password, parsed.sso) != (email, password, sso):
        raise RecordValidationError("record fields cannot round-trip safely")
    return line
