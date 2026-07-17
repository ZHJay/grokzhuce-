import unittest

from account_record import AccountRecord
from sub2api_client import Sub2APIClient, Sub2APIError


class RecordingTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, path, payload, timeout):
        self.calls.append((method, path, payload, timeout))
        return self.responses.pop(0)


class Sub2APIClientTest(unittest.TestCase):
    def test_resolves_unique_active_grok_group_by_name_and_platform(self):
        transport = RecordingTransport([[{
            "id": 3,
            "name": "Grok",
            "platform": "grok",
            "status": "active",
        }]])
        client = Sub2APIClient("http://localhost/api/v1", "token", transport=transport)

        group_id = client.get_grok_group_id()

        self.assertEqual(group_id, 3)
        self.assertEqual(transport.calls[0][0:2], ("GET", "/admin/groups/all?platform=grok"))

    def test_rejects_missing_or_ambiguous_grok_group(self):
        response_sets = [[], [
            {"id": 3, "name": "Grok", "platform": "grok", "status": "active"},
            {"id": 4, "name": "Grok", "platform": "grok", "status": "active"},
        ]]
        for response in response_sets:
            with self.subTest(response=response):
                client = Sub2APIClient(
                    "http://localhost/api/v1",
                    "token",
                    transport=RecordingTransport([response]),
                )
                with self.assertRaises(Sub2APIError):
                    client.get_grok_group_id()

    def test_lists_existing_grok_names_across_all_pages(self):
        transport = RecordingTransport([
            {"items": [{"name": "one"}], "page": 1, "pages": 2},
            {"items": [{"name": "two"}], "page": 2, "pages": 2},
        ])
        client = Sub2APIClient("http://localhost/api/v1", "token", transport=transport)

        names = client.list_existing_grok_names()

        self.assertEqual(names, {"one", "two"})
        self.assertIn("page=1", transport.calls[0][1])
        self.assertIn("page=2", transport.calls[1][1])

    def test_create_payload_contains_exactly_one_sso_and_requested_settings(self):
        transport = RecordingTransport([{
            "created": [{"account": {"id": 501, "expires_at": None}}],
            "failed": [],
        }])
        client = Sub2APIClient("http://localhost/api/v1", "token", transport=transport)
        record = AccountRecord(1, "a@example.com", "secret", "sso-token")

        account = client.create_grok_from_sso(record, group_id=3)

        _, path, payload, _ = transport.calls[0]
        self.assertEqual(path, "/admin/grok/sso-to-oauth")
        self.assertEqual(payload["sso_tokens"], ["sso-token"])
        self.assertEqual(payload["name"], "a@example.com|secret")
        self.assertEqual(payload["group_ids"], [3])
        self.assertEqual(payload["credentials"], {})
        self.assertEqual(payload["concurrency"], 10)
        self.assertEqual(payload["priority"], 1)
        self.assertEqual(payload["rate_multiplier"], 1)
        self.assertIsNone(payload["expires_at"])
        self.assertFalse(payload["auto_pause_on_expired"])
        self.assertEqual(account["id"], 501)

    def test_create_failure_keeps_only_safe_reason_code(self):
        transport = RecordingTransport([{
            "created": [],
            "failed": [{
                "error": "GROK_SSO_EXCHANGE_FAILED: upstream secret-value@example.com"
            }],
        }])
        client = Sub2APIClient("http://localhost/api/v1", "token", transport=transport)
        record = AccountRecord(1, "a@example.com", "secret", "sso-token")

        with self.assertRaisesRegex(
            Sub2APIError, r"Grok SSO conversion failed \(GROK_SSO_EXCHANGE_FAILED\)"
        ) as raised:
            client.create_grok_from_sso(record, group_id=3)

        self.assertNotIn("upstream", str(raised.exception))
        self.assertNotIn("secret-value", str(raised.exception))

    def test_create_failure_does_not_expose_upstream_error_body(self):
        transport = RecordingTransport([{
            "created": [],
            "failed": [{"error": "invalid token secret-value@example.com"}],
        }])
        client = Sub2APIClient("http://localhost/api/v1", "token", transport=transport)
        record = AccountRecord(1, "a@example.com", "secret", "sso-token")

        with self.assertRaisesRegex(Sub2APIError, "Grok SSO conversion failed") as raised:
            client.create_grok_from_sso(record, group_id=3)

        self.assertNotIn("secret-value", str(raised.exception))
        self.assertNotIn("a@example.com", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
