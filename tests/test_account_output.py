import stat
import tempfile
import unittest
from pathlib import Path

from account_output import append_account_record


class AccountOutputTest(unittest.TestCase):
    def test_appends_importer_record_with_private_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "accounts.txt"
            output_path.touch(mode=0o644)
            output_path.chmod(0o644)

            append_account_record(
                output_path,
                "user@example.com",
                "password123",
                "sso-token",
            )

            self.assertEqual(
                output_path.read_text(encoding="utf-8"),
                "user@example.com|password123|sso-token\n",
            )
            self.assertEqual(stat.S_IMODE(output_path.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
