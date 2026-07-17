import unittest

from account_record import AccountRecord
from sub2api_client import Sub2APIClient, Sub2APIError


class OneResponseTransport:
    def __init__(self, response):
        self.response = response

    def __call__(self, _method, _path, _payload, _timeout):
        return self.response


class Sub2APIContractTypesTest(unittest.TestCase):
    def test_rejects_boolean_group_id(self):
        client = Sub2APIClient(
            "http://localhost/api/v1",
            "token",
            transport=OneResponseTransport([{
                "id": True,
                "name": "Grok",
                "platform": "grok",
                "status": "active",
            }]),
        )

        with self.assertRaisesRegex(Sub2APIError, "exactly one"):
            client.get_grok_group_id()

    def test_rejects_boolean_account_list_id(self):
        client = Sub2APIClient(
            "http://localhost/api/v1",
            "token",
            transport=OneResponseTransport({
                "items": [{"id": True, "name": "same"}],
                "page": 1,
                "pages": 1,
            }),
        )

        with self.assertRaisesRegex(Sub2APIError, "list item is invalid"):
            client.list_existing_accounts()

    def test_rejects_boolean_created_account_id(self):
        client = Sub2APIClient(
            "http://localhost/api/v1",
            "token",
            transport=OneResponseTransport({
                "created": [{"account": {"id": True}}],
                "failed": [],
            }),
        )
        record = AccountRecord(1, "user@example.com", "password", "sso")

        with self.assertRaisesRegex(Sub2APIError, "omitted the created account"):
            client.create_grok_from_sso(record, group_id=3)


if __name__ == "__main__":
    unittest.main()
