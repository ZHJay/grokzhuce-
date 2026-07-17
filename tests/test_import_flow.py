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
            "expires_at": None,
            "auto_pause_on_expired": False,
        }


class ImportFlowTest(unittest.TestCase):
    def setUp(self):
        self.records = [
            AccountRecord(1, "one@example.com", "password-one", "sso-one"),
            AccountRecord(2, "two@example.com", "password-two", "sso-two"),
        ]

    def compliant_account(self, record, *, account_id=99, group_id=3):
        return {
            "id": account_id,
            "name": record.account_name,
            "platform": "grok",
            "type": "oauth",
            "group_ids": [group_id],
            "credentials": {},
            "expires_at": None,
            "auto_pause_on_expired": False,
        }

    def test_compliant_existing_account_is_skipped_with_account_id(self):
        client = SequentialProbeClient()
        existing = {
            self.records[0].account_name: [self.compliant_account(self.records[0])]
        }

        summary = run_import(
            [self.records[0]],
            client,
            group_id=3,
            existing_accounts=existing,
        )

        self.assertEqual(summary.skipped, 1)
        self.assertEqual(summary.items[0].account_id, 99)
        self.assertEqual(client.events, [])

    def test_noncompliant_or_duplicate_existing_account_is_failed_not_skipped(self):
        expired = self.compliant_account(self.records[0])
        expired["expires_at"] = 1_800_000_000
        restricted = self.compliant_account(self.records[0])
        restricted["credentials"] = {"model_mapping": {"grok-3": "grok-3"}}
        cases = [
            [expired],
            [restricted],
            [
                self.compliant_account(self.records[0], account_id=99),
                self.compliant_account(self.records[0], account_id=100),
            ],
        ]
        for accounts in cases:
            with self.subTest(count=len(accounts), expiry=accounts[0]["expires_at"]):
                client = SequentialProbeClient()
                summary = run_import(
                    [self.records[0]],
                    client,
                    group_id=3,
                    existing_accounts={self.records[0].account_name: accounts},
                )
                self.assertEqual(summary.failed, 1)
                self.assertEqual(summary.skipped, 0)
                self.assertEqual(client.events, [])

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

    def test_existing_exact_name_is_skipped(self):
        client = SequentialProbeClient()

        summary = run_import(
            self.records,
            client,
            group_id=3,
            existing_accounts={
                self.records[0].account_name: [
                    self.compliant_account(self.records[0])
                ]
            },
        )

        self.assertEqual(client.events, ["start:2", "end:2"])
        self.assertEqual(summary.skipped, 1)
        self.assertEqual(summary.created, 1)

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

    def test_created_noncompliant_account_remains_failed_on_rerun(self):
        class ExpiringClient(SequentialProbeClient):
            def create_grok_from_sso(self, record, *, group_id):
                account = {
                    "id": 501,
                    "name": record.account_name,
                    "platform": "grok",
                    "type": "oauth",
                    "group_ids": [group_id],
                    "credentials": {},
                    "expires_at": 1_800_000_000,
                    "auto_pause_on_expired": True,
                }
                return account

        existing = {}
        first = run_import(
            [self.records[0]],
            ExpiringClient(),
            group_id=3,
            existing_accounts=existing,
        )
        second_client = SequentialProbeClient()
        second = run_import(
            [self.records[0]],
            second_client,
            group_id=3,
            existing_accounts=existing,
        )

        self.assertEqual(first.failed, 1)
        self.assertEqual(first.items[0].account_id, 501)
        self.assertEqual(
            first.items[0].error,
            "created account does not satisfy requested settings",
        )
        self.assertEqual(second.failed, 1)
        self.assertEqual(second.skipped, 0)
        self.assertEqual(second_client.events, [])


if __name__ == "__main__":
    unittest.main()
