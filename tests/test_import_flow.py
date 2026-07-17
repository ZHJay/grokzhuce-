import json
import unittest

from account_record import AccountRecord
from import_flow import run_import
from sub2api_client import Sub2APIError


class SequentialProbeClient:
    def __init__(self, *, fail_lines=None):
        self.fail_lines = set(fail_lines or [])
        self.events = []

    def create_grok_from_sso(self, record, *, group_id):
        self.events.append(f"start:{record.line_number}")
        if record.line_number in self.fail_lines:
            self.events.append(f"end:{record.line_number}")
            raise Sub2APIError("Grok SSO conversion failed")
        self.events.append(f"end:{record.line_number}")
        return {"id": 500 + record.line_number, "expires_at": None}


class ImportFlowTest(unittest.TestCase):
    def setUp(self):
        self.records = [
            AccountRecord(1, "one@example.com", "password-one", "sso-one"),
            AccountRecord(2, "two@example.com", "password-two", "sso-two"),
        ]

    def test_flow_waits_for_each_create_before_starting_the_next(self):
        client = SequentialProbeClient()

        summary = run_import(
            self.records, client, group_id=3, existing_names=set()
        )

        self.assertEqual(
            client.events, ["start:1", "end:1", "start:2", "end:2"]
        )
        self.assertEqual(summary.created, 2)
        self.assertEqual(summary.failed, 0)

    def test_existing_exact_name_is_skipped(self):
        client = SequentialProbeClient()

        summary = run_import(
            self.records,
            client,
            group_id=3,
            existing_names={self.records[0].account_name},
        )

        self.assertEqual(client.events, ["start:2", "end:2"])
        self.assertEqual(summary.skipped, 1)
        self.assertEqual(summary.created, 1)

    def test_failure_is_recorded_and_next_record_still_runs(self):
        client = SequentialProbeClient(fail_lines={1})

        summary = run_import(
            self.records, client, group_id=3, existing_names=set()
        )

        self.assertEqual(
            client.events, ["start:1", "end:1", "start:2", "end:2"]
        )
        self.assertEqual(summary.failed, 1)
        self.assertEqual(summary.created, 1)

    def test_report_contains_no_account_secrets(self):
        client = SequentialProbeClient(fail_lines={1})
        summary = run_import(
            self.records, client, group_id=3, existing_names=set()
        )

        report = json.dumps(summary.to_dict())

        for sensitive in (
            "@",
            "password-one",
            "password-two",
            "sso-one",
            "sso-two",
            "one@example.com",
        ):
            self.assertNotIn(sensitive, report)

    def test_created_account_with_expiry_is_reported_as_postcondition_failure(self):
        class ExpiringClient(SequentialProbeClient):
            def create_grok_from_sso(self, record, *, group_id):
                return {"id": 501, "expires_at": 1_800_000_000}

        summary = run_import(
            [self.records[0]], ExpiringClient(), group_id=3, existing_names=set()
        )

        self.assertEqual(summary.created, 0)
        self.assertEqual(summary.failed, 1)
        self.assertEqual(summary.items[0].account_id, 501)
        self.assertEqual(summary.items[0].error, "created account has an expiry")


if __name__ == "__main__":
    unittest.main()
