#!/usr/bin/env python3
"""CLI boundary for the serial Grok SSO import flow."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from account_record import RecordValidationError, parse_account_records
from import_flow import ImportItem, ImportSummary, run_import
from local_admin_token import LocalAdminTokenProvider
from sub2api_client import Sub2APIClient, Sub2APIError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import Grok SSO accounts into local Sub2API serially."
    )
    parser.add_argument("input_file", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--base-url", default="http://127.0.0.1:8080/api/v1"
    )
    parser.add_argument("--report", type=Path)
    return parser


def print_progress(item: ImportItem, current: int, total: int) -> None:
    """Print progress without account names or source credential fields."""
    suffix = ""
    if item.account_id is not None:
        suffix += f" account_id={item.account_id}"
    if item.error:
        suffix += f" error={item.error}"
    print(
        f"[{current:03d}/{total:03d}] line={item.line_number} "
        f"{item.status}{suffix}",
        flush=True,
    )


def write_report(path: Path, summary: ImportSummary) -> None:
    """Atomically replace a private, credential-free JSON report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(summary.to_dict(), output, indent=2, sort_keys=True)
            output.write("\n")
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        records = parse_account_records(
            args.input_file.read_text(encoding="utf-8").splitlines()
        )
        token_provider = LocalAdminTokenProvider()
        client = Sub2APIClient(args.base_url, token_provider)
        group_id = client.get_grok_group_id()
        existing_accounts = client.list_existing_grok_accounts()
        existing_count = sum(len(items) for items in existing_accounts.values())
        mode = "dry-run" if args.dry_run else "apply"
        print(
            f"validated={len(records)} group_id={group_id} "
            f"existing_grok={existing_count} mode={mode}"
        )
        if args.dry_run:
            print("dry-run complete: create_calls=0")
            return 0

        summary = run_import(
            records,
            client,
            group_id=group_id,
            existing_accounts=existing_accounts,
            on_progress=print_progress,
        )
        if args.report is not None:
            write_report(args.report, summary)
        print(
            f"summary total={len(summary.items)} created={summary.created} "
            f"skipped={summary.skipped} failed={summary.failed}"
        )
        return 2 if summary.failed else 0
    except (
        OSError,
        ValueError,
        RecordValidationError,
        RuntimeError,
        Sub2APIError,
        subprocess.SubprocessError,
    ) as exc:
        # Boundary contract: imported values never appear in these exception types.
        print(f"fatal: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
