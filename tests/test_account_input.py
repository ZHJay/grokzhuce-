import tempfile
import unittest
from pathlib import Path

from account_input import read_private_account_lines


class AccountInputTest(unittest.TestCase):
    def test_reads_private_regular_file(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "accounts.txt"
            source.write_text(
                "user@example.com|password|sso-token\n", encoding="utf-8"
            )
            source.chmod(0o600)

            lines = read_private_account_lines(source)

            self.assertEqual(
                lines, ["user@example.com|password|sso-token"]
            )

    def test_rejects_group_or_world_accessible_file(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "accounts.txt"
            source.write_text("sensitive\n", encoding="utf-8")
            source.chmod(0o644)

            with self.assertRaisesRegex(ValueError, "mode 0600"):
                read_private_account_lines(source)

    def test_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target.txt"
            target.write_text("sensitive\n", encoding="utf-8")
            target.chmod(0o600)
            source = Path(directory) / "accounts.txt"
            source.symlink_to(target)

            with self.assertRaisesRegex(ValueError, "regular file"):
                read_private_account_lines(source)


if __name__ == "__main__":
    unittest.main()
