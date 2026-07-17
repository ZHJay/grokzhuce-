import unittest

from account_record import (
    RecordValidationError,
    format_account_record,
    parse_account_records,
)


class ParseAccountRecordsTest(unittest.TestCase):
    def test_formats_registration_output_for_importer(self):
        line = format_account_record(
            "user@example.com", "password123", "sso-token"
        )

        self.assertEqual(
            line, "user@example.com|password123|sso-token"
        )

    def test_rejects_ambiguous_registration_output(self):
        for password in ("pass|word", "pass\nword", "pass\rword"):
            with self.subTest(password=repr(password)):
                with self.assertRaisesRegex(
                    RecordValidationError, "round-trip safely"
                ):
                    format_account_record(
                        "user@example.com", password, "sso-token"
                    )

    def test_parses_three_fields_and_preserves_requested_name(self):
        records = parse_account_records(["a@example.com|secret|sso-token"])

        self.assertEqual(records[0].line_number, 1)
        self.assertEqual(records[0].account_name, "a@example.com|secret")
        self.assertEqual(records[0].sso, "sso-token")

    def test_ignores_blank_lines_and_keeps_source_line_number(self):
        records = parse_account_records(["", "a@example.com|secret|sso-token"])

        self.assertEqual(records[0].line_number, 2)

    def test_rejects_missing_or_empty_fields(self):
        invalid_inputs = [
            ["a@example.com|secret"],
            ["|secret|sso-token"],
            ["a@example.com||sso-token"],
            ["a@example.com|secret|"],
        ]

        for lines in invalid_inputs:
            with self.subTest(lines=lines):
                with self.assertRaises(RecordValidationError):
                    parse_account_records(lines)

    def test_rejects_sso_delimiters_expanded_by_server(self):
        for sso in ("sso,second", "sso\rsecond", "sso\nsecond"):
            with self.subTest(sso=repr(sso)):
                with self.assertRaisesRegex(
                    RecordValidationError, "server-side delimiter"
                ):
                    parse_account_records([f"a@example.com|secret|{sso}"])

    def test_rejects_duplicate_email_case_insensitively(self):
        with self.assertRaisesRegex(RecordValidationError, "duplicate email"):
            parse_account_records([
                "a@example.com|one|sso-1",
                "A@example.com|two|sso-2",
            ])

    def test_rejects_duplicate_sso(self):
        with self.assertRaisesRegex(RecordValidationError, "duplicate SSO"):
            parse_account_records([
                "a@example.com|one|sso-1",
                "b@example.com|two|sso-1",
            ])


if __name__ == "__main__":
    unittest.main()
