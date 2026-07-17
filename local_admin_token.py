"""L1 积木层：在长串行批次中按安全余量刷新本地 Admin JWT。"""

from __future__ import annotations

import time
from collections.abc import Callable

from local_admin_auth import (
    AdminIdentity,
    build_admin_jwt,
    load_local_admin_material,
)


MaterialLoader = Callable[[], tuple[AdminIdentity, str]]


class LocalAdminTokenProvider:
    """Cache one JWT while reloading current admin state before each refresh."""

    def __init__(
        self,
        *,
        material_loader: MaterialLoader = load_local_admin_material,
        clock: Callable[[], float] = time.time,
        lifetime_seconds: int = 900,
        refresh_margin_seconds: int = 300,
    ) -> None:
        if not 0 < refresh_margin_seconds < lifetime_seconds:
            raise ValueError("JWT refresh margin must precede expiry")
        self._material_loader = material_loader
        self._clock = clock
        self._lifetime_seconds = lifetime_seconds
        self._refresh_after_seconds = lifetime_seconds - refresh_margin_seconds
        self._token: str | None = None
        self._refresh_at = 0

    def __call__(self) -> str:
        now = int(self._clock())
        if self._token is None or now >= self._refresh_at:
            identity, jwt_secret = self._material_loader()
            self._token = build_admin_jwt(
                identity,
                jwt_secret,
                now=now,
                lifetime_seconds=self._lifetime_seconds,
            )
            self._refresh_at = now + self._refresh_after_seconds
        return self._token
