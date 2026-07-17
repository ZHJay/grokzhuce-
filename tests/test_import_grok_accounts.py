import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from import_flow import ImportItem, ImportSummary
from import_grok_accounts import build_parser, print_progress, write_report


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
