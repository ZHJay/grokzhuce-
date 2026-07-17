"""L1 积木层：持久化 importer 可读取的私密注册记录。"""

from __future__ import annotations

import os

from account_record import format_account_record


def append_account_record(
    path: str | os.PathLike[str],
    email: str,
    password: str,
    sso: str,
) -> None:
    """Append one record and enforce owner-only permissions where supported."""
    record_line = format_account_record(email, password, sso)
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)

    descriptor = os.open(path, flags, 0o600)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        output = os.fdopen(descriptor, "a", encoding="utf-8")
        descriptor = -1
        with output:
            output.write(record_line + "\n")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
