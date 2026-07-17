"""L1 积木层：安全读取包含账号凭据的 importer 输入文件。"""

from __future__ import annotations

import os
import stat


def read_private_account_lines(
    path: str | os.PathLike[str],
) -> list[str]:
    """Read a regular non-symlink file with owner-only Unix permissions."""
    path_info = os.lstat(path)
    if not stat.S_ISREG(path_info.st_mode):
        raise ValueError("account input must be a regular file")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        file_info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(file_info.st_mode)
            or (file_info.st_dev, file_info.st_ino)
            != (path_info.st_dev, path_info.st_ino)
        ):
            raise ValueError("account input must be a regular file")
        if os.name != "nt" and stat.S_IMODE(file_info.st_mode) != 0o600:
            raise ValueError("account input must use mode 0600")
        source = os.fdopen(descriptor, "r", encoding="utf-8")
        descriptor = -1
        with source:
            return source.read().splitlines()
    finally:
        if descriptor >= 0:
            os.close(descriptor)
