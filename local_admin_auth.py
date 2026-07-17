"""L1 积木层：为服务器本地维护任务签发短期 Sub2API Admin JWT。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import subprocess
import time
from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True, slots=True)
class AdminIdentity:
    user_id: int
    email: str
    password_hash: str = field(repr=False)
    role: str = "admin"
    status: str = "active"


def resolve_token_version(
    email: str, password_hash: str, base_version: int = 0
) -> int:
    """Mirror Sub2API v0.1.156's password-fingerprint revocation contract."""
    material = f"{email.strip().lower()}\n{password_hash}"
    digest = hashlib.sha256(material.encode()).digest()
    fingerprint = int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF
    return base_version ^ fingerprint


def parse_container_env(raw_json: str) -> dict[str, str]:
    """Convert Docker's JSON env list without dropping '=' inside secrets."""
    items = json.loads(raw_json)
    if not isinstance(items, list):
        raise ValueError("container environment is not a JSON list")
    result: dict[str, str] = {}
    for item in items:
        if not isinstance(item, str) or "=" not in item:
            continue
        key, value = item.split("=", 1)
        result[key] = value
    return result


CommandRunner = Callable[[list[str]], str]


def _run_command(command: list[str]) -> str:
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return completed.stdout


def _container_env(container: str, run: CommandRunner) -> dict[str, str]:
    raw = run(
        ["sudo", "docker", "inspect", container, "--format", "{{json .Config.Env}}"]
    )
    return parse_container_env(raw)


def load_local_admin_material(
    *, run: CommandRunner = _run_command
) -> tuple[AdminIdentity, str]:
    """Read signing material locally without persisting or printing secrets."""
    app_env = _container_env("sub2api", run)
    db_env = _container_env("sub2api-postgres", run)
    jwt_secret = app_env.get("JWT_SECRET", "")
    db_user = db_env.get("POSTGRES_USER", "")
    db_name = db_env.get("POSTGRES_DB", "")
    if not db_user or not db_name:
        raise RuntimeError("required Sub2API container environment is missing")

    psql_prefix = [
        "sudo",
        "docker",
        "exec",
        "sub2api-postgres",
        "psql",
        "-U",
        db_user,
        "-d",
        db_name,
        "--tuples-only",
        "--no-align",
    ]
    # Runtime bootstrap deliberately lets the persisted secret override a stale
    # container value so every replica signs with the same key.
    persisted_secret = run(
        psql_prefix
        + [
            "-c",
            "SELECT value FROM security_secrets "
            "WHERE key='jwt_secret' LIMIT 1",
        ]
    ).strip()
    if persisted_secret and "\t" not in persisted_secret:
        jwt_secret = persisted_secret
    if not jwt_secret:
        raise RuntimeError("Sub2API runtime JWT secret is missing")

    query = (
        "SELECT id,email,password_hash,role,status FROM users "
        "WHERE role='admin' AND status='active' AND deleted_at IS NULL "
        "ORDER BY id LIMIT 1"
    )
    row = run(
        [
            "sudo",
            "docker",
            "exec",
            "sub2api-postgres",
            "psql",
            "-U",
            db_user,
            "-d",
            db_name,
            "--tuples-only",
            "--no-align",
            "--field-separator",
            "\t",
            "-c",
            query,
        ]
    ).strip()
    fields = row.split("\t")
    if len(fields) != 5:
        raise RuntimeError("expected one active admin database row")
    identity = AdminIdentity(int(fields[0]), fields[1], fields[2], fields[3], fields[4])
    return identity, jwt_secret


def _base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def build_admin_jwt(
    identity: AdminIdentity,
    jwt_secret: str,
    *,
    now: int | None = None,
    lifetime_seconds: int = 900,
) -> str:
    """Build an ephemeral JWT; callers must keep the result in memory only."""
    if identity.role != "admin" or identity.status != "active":
        raise ValueError("active admin identity is required")
    if not jwt_secret:
        raise ValueError("JWT_SECRET is empty")
    issued_at = int(time.time()) if now is None else now
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "user_id": identity.user_id,
        "email": identity.email,
        "role": identity.role,
        "token_version": resolve_token_version(
            identity.email, identity.password_hash
        ),
        "iat": issued_at,
        "nbf": issued_at,
        "exp": issued_at + lifetime_seconds,
    }
    header_segment = _base64url(
        json.dumps(header, separators=(",", ":")).encode()
    )
    payload_segment = _base64url(
        json.dumps(payload, separators=(",", ":")).encode()
    )
    signing_input = f"{header_segment}.{payload_segment}"
    signature = hmac.new(
        jwt_secret.encode(), signing_input.encode(), hashlib.sha256
    ).digest()
    return f"{signing_input}.{_base64url(signature)}"
