import base64
import json
import unittest

from local_admin_auth import AdminIdentity
from local_admin_token import LocalAdminTokenProvider


def decode_payload(token):
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


class LocalAdminTokenProviderTest(unittest.TestCase):
    def test_refreshes_before_expiry_and_reloads_current_admin_material(self):
        now = [1_700_000_000]
        loads = []

        def load():
            loads.append(now[0])
            identity = AdminIdentity(
                1, "admin@example.com", "password-hash", "admin", "active"
            )
            return identity, "runtime-secret"

        provider = LocalAdminTokenProvider(material_loader=load, clock=lambda: now[0])

        first = provider()
        now[0] += 599
        cached = provider()
        now[0] += 1
        refreshed = provider()

        self.assertEqual(first, cached)
        self.assertNotEqual(first, refreshed)
        self.assertEqual(loads, [1_700_000_000, 1_700_000_600])
        self.assertEqual(decode_payload(first)["exp"], 1_700_000_900)
        self.assertEqual(decode_payload(refreshed)["iat"], 1_700_000_600)

    def test_rejects_refresh_margin_that_cannot_precede_expiry(self):
        for margin in (0, 900, 901):
            with self.subTest(margin=margin):
                with self.assertRaises(ValueError):
                    LocalAdminTokenProvider(refresh_margin_seconds=margin)


if __name__ == "__main__":
    unittest.main()
