import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from import_flow import ImportItem, ImportSummary
from import_grok_accounts import build_parser, main, print_progress, write_report


class ImporterCLITest(unittest.TestCase):
    def test_parser_requires_exactly_one_execution_mode(self):
        parser = build_parser()

        error_output = io.StringIO()
        with contextlib.redirect_stderr(error_output):
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

    def test_main_passes_refreshing_token_provider_to_client(self):
        fake_client = mock.Mock()
        fake_client.get_grok_group_id.return_value = 3
        fake_client.list_existing_grok_accounts.return_value = {}
        token_provider = object()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "accounts.txt"
            source.write_text("a@example.com|secret|sso-token\n")
            output = io.StringIO()
            with mock.patch(
                "import_grok_accounts.LocalAdminTokenProvider",
                return_value=token_provider,
            ), mock.patch(
                "import_grok_accounts.Sub2APIClient", return_value=fake_client
            ) as client_class, contextlib.redirect_stdout(output):
                exit_code = main([str(source), "--dry-run"])

        self.assertEqual(exit_code, 0)
        self.assertIs(client_class.call_args.args[1], token_provider)

    def test_main_normalizes_token_provider_value_error_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "accounts.txt"
            source.write_text("a@example.com|secret|sso-token\n")
            stderr = io.StringIO()
            with mock.patch(
                "import_grok_accounts.LocalAdminTokenProvider",
                side_effect=ValueError("active admin identity is required"),
            ), contextlib.redirect_stderr(stderr):
                exit_code = main([str(source), "--dry-run"])

        self.assertEqual(exit_code, 1)
        self.assertIn("fatal: active admin identity is required", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_report_does_not_follow_fixed_temporary_symlink(self):
        summary = ImportSummary((ImportItem(1, "created", account_id=501),))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            victim = root / "victim.txt"
            victim.write_text("do-not-overwrite")
            report = root / "report.json"
            (root / ".report.json.tmp").symlink_to(victim)

            write_report(report, summary)

            self.assertEqual(victim.read_text(), "do-not-overwrite")
            self.assertFalse(report.is_symlink())
            self.assertEqual(json.loads(report.read_text())["created"], 1)

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
