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
        return {
            "id": 500 + record.line_number,
            "name": record.account_name,
            "platform": "grok",
            "type": "oauth",
            "group_ids": [group_id],
            "credentials": {},
            "concurrency": 10,
            "priority": 1,
            "rate_multiplier": 1,
            "expires_at": None,
            "auto_pause_on_expired": False,
        }


class ImportFlowTest(unittest.TestCase):
    def setUp(self):
        self.records = [
            AccountRecord(1, "one@example.com", "password-one", "sso-one"),
            AccountRecord(2, "two@example.com", "password-two", "sso-two"),
        ]


    def test_flow_waits_for_each_create_before_starting_the_next(self):
        client = SequentialProbeClient()

        summary = run_import(
            self.records, client, group_id=3, existing_accounts={}
        )

        self.assertEqual(
            client.events, ["start:1", "end:1", "start:2", "end:2"]
        )
        self.assertEqual(summary.created, 2)
        self.assertEqual(summary.failed, 0)


    def test_failure_is_recorded_and_next_record_still_runs(self):
        client = SequentialProbeClient(fail_lines={1})

        summary = run_import(
            self.records, client, group_id=3, existing_accounts={}
        )

        self.assertEqual(
            client.events, ["start:1", "end:1", "start:2", "end:2"]
        )
        self.assertEqual(summary.failed, 1)
        self.assertEqual(summary.created, 1)

    def test_report_contains_no_account_secrets(self):
        client = SequentialProbeClient(fail_lines={1})
        summary = run_import(
            self.records, client, group_id=3, existing_accounts={}
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

if __name__ == "__main__":
    unittest.main()
