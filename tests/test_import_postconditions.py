import copy
import unittest

from account_record import AccountRecord
from import_flow import run_import


class ProbeClient:
    def __init__(self, account=None):
        self.account = account
        self.calls = 0

    def create_grok_from_sso(self, record, *, group_id):
        self.calls += 1
        if self.account is not None:
            return copy.deepcopy(self.account)
        return compliant_account(record, group_id=group_id, account_id=501)


def compliant_account(record, *, group_id=3, account_id=99):
    return {
        "id": account_id,
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


class ImportPostconditionsTest(unittest.TestCase):
    def setUp(self):
        self.record = AccountRecord(
            1, "one@example.com", "password-one", "sso-one"
        )

    def test_unique_compliant_existing_account_is_skipped(self):
        client = ProbeClient()
        account = compliant_account(self.record)

        summary = run_import(
            [self.record],
            client,
            group_id=3,
            existing_accounts={self.record.account_name: [account]},
        )

        self.assertEqual(summary.skipped, 1)
        self.assertEqual(summary.items[0].account_id, 99)
        self.assertEqual(client.calls, 0)

    def test_every_existing_postcondition_and_uniqueness_is_required(self):
        mutations = {
            "name": lambda item: item.update(name="wrong-name"),
            "platform": lambda item: item.update(platform="other"),
            "type": lambda item: item.update(type="apikey"),
            "group": lambda item: item.update(group_ids=[4]),
            "model_mapping": lambda item: item.update(
                credentials={"model_mapping": {"grok-3": "grok-3"}}
            ),
            "concurrency": lambda item: item.update(concurrency=9),
            "priority": lambda item: item.update(priority=2),
            "rate_multiplier": lambda item: item.update(rate_multiplier=1.5),
            "expiry": lambda item: item.update(expires_at=1_800_000_000),
            "auto_pause": lambda item: item.update(auto_pause_on_expired=True),
        }
        cases = []
        for label, mutate in mutations.items():
            account = compliant_account(self.record)
            mutate(account)
            cases.append((label, [account]))
        cases.append(("duplicate", [
            compliant_account(self.record, account_id=99),
            compliant_account(self.record, account_id=100),
        ]))

        for label, accounts in cases:
            with self.subTest(label=label):
                client = ProbeClient()
                summary = run_import(
                    [self.record],
                    client,
                    group_id=3,
                    existing_accounts={self.record.account_name: accounts},
                )
                self.assertEqual(summary.failed, 1)
                self.assertEqual(summary.skipped, 0)
                self.assertEqual(client.calls, 0)

    def test_noncompliant_create_response_requires_manual_recovery(self):
        wrong = compliant_account(self.record, account_id=501)
        wrong["name"] = "wrong-name"
        existing = {}

        summary = run_import(
            [self.record],
            ProbeClient(wrong),
            group_id=3,
            existing_accounts=existing,
        )

        self.assertEqual(summary.failed, 1)
        self.assertEqual(summary.items[0].account_id, 501)
        self.assertEqual(existing, {})


if __name__ == "__main__":
    unittest.main()
