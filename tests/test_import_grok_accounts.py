import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from import_flow import ImportItem, ImportSummary
from import_grok_accounts import build_parser, main, print_progress, write_report
from local_admin_auth import AdminIdentity


class ImporterCLITest(unittest.TestCase):
    def test_parser_requires_exactly_one_execution_mode(self):
        parser = build_parser()

        with self.assertRaises(SystemExit):
            parser.parse_args(["accounts.txt"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["accounts.txt", "--dry-run", "--apply"])
        self.assertTrue(parser.parse_args(["accounts.txt", "--dry-run"]).dry_run)
        self.assertTrue(parser.parse_args(["accounts.txt", "--apply"]).apply)

    def test_progress_prints_only_index_status_and_account_id(self):
        output = io.StringIO()
        item = ImportItem(7, "created", account_id=501)

        with contextlib.redirect_stdout(output):
            print_progress(item, 1, 100)

        self.assertEqual(output.getvalue(), "[001/100] line=7 created account_id=501\n")

    def test_main_normalizes_inactive_admin_value_error_without_traceback(self):
        identity = AdminIdentity(
            1, "admin@example.com", "hash", role="admin", status="inactive"
        )
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "accounts.txt"
            source.write_text("a@example.com|secret|sso-token\n")
            stderr = io.StringIO()
            with mock.patch(
                "import_grok_accounts.load_local_admin_material",
                return_value=(identity, "jwt-secret"),
            ), contextlib.redirect_stderr(stderr):
                exit_code = main([str(source), "--dry-run"])

        self.assertEqual(exit_code, 1)
        self.assertIn("fatal: active admin identity is required", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_report_is_private_json_without_source_fields(self):
        summary = ImportSummary((ImportItem(1, "created", account_id=501),))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reports" / "result.json"

            write_report(path, summary)

            data = json.loads(path.read_text())
            self.assertEqual(data["created"], 1)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            report = path.read_text()
            for field in ("email", "password", "sso", "jwt"):
                self.assertNotIn(field, report.lower())


if __name__ == "__main__":
    unittest.main()
