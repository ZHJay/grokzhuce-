import base64
import hashlib
import hmac
import json
import unittest

from local_admin_auth import (
    AdminIdentity,
    build_admin_jwt,
    load_local_admin_material,
    parse_container_env,
    resolve_token_version,
)


def decode_segment(segment: str) -> dict:
    padding = "=" * (-len(segment) % 4)
    return json.loads(base64.urlsafe_b64decode(segment + padding))


class LocalAdminAuthTest(unittest.TestCase):
    def test_resolve_token_version_matches_sub2api_fingerprint_rule(self):
        material = "admin@example.com\n$2a$10$hash"
        expected = (
            int.from_bytes(hashlib.sha256(material.encode()).digest()[:8], "big")
            & 0x7FFFFFFFFFFFFFFF
        )

        actual = resolve_token_version(" Admin@Example.com ", "$2a$10$hash")

        self.assertEqual(actual, expected)

    def test_base_token_version_is_xored_with_fingerprint(self):
        fingerprint = resolve_token_version("admin@example.com", "hash")

        self.assertEqual(
            resolve_token_version("admin@example.com", "hash", base_version=17),
            fingerprint ^ 17,
        )

    def test_build_admin_jwt_has_expected_payload_and_hs256_signature(self):
        identity = AdminIdentity(
            user_id=1,
            email="admin@example.com",
            password_hash="hash",
            role="admin",
            status="active",
        )

        token = build_admin_jwt(identity, "test-secret", now=1_700_000_000)

        header_segment, payload_segment, signature_segment = token.split(".")
        self.assertEqual(decode_segment(header_segment), {"alg": "HS256", "typ": "JWT"})
        payload = decode_segment(payload_segment)
        self.assertEqual(payload["user_id"], 1)
        self.assertEqual(payload["email"], "admin@example.com")
        self.assertEqual(payload["role"], "admin")
        self.assertEqual(payload["iat"], 1_700_000_000)
        self.assertEqual(payload["nbf"], 1_700_000_000)
        self.assertEqual(payload["exp"], 1_700_000_900)
        expected_signature = base64.urlsafe_b64encode(
            hmac.new(
                b"test-secret",
                f"{header_segment}.{payload_segment}".encode(),
                hashlib.sha256,
            ).digest()
        ).rstrip(b"=").decode()
        self.assertEqual(signature_segment, expected_signature)

    def test_parse_container_env_preserves_equals_in_values(self):
        env = parse_container_env('["JWT_SECRET=a=b=c","EMPTY=","NAME=value"]')

        self.assertEqual(env["JWT_SECRET"], "a=b=c")
        self.assertEqual(env["EMPTY"], "")

    def test_load_local_admin_material_uses_argv_commands_and_fixed_query(self):
        commands = []

        def run(command):
            commands.append(command)
            if command[2] == "inspect" and command[3] == "sub2api":
                return '["JWT_SECRET=jwt-secret"]'
            if command[2] == "inspect" and command[3] == "sub2api-postgres":
                return '["POSTGRES_USER=dbuser","POSTGRES_DB=dbname"]'
            return "1\tadmin@example.com\thash\tadmin\tactive\n"

        identity, secret = load_local_admin_material(run=run)

        self.assertEqual(identity.user_id, 1)
        self.assertEqual(identity.email, "admin@example.com")
        self.assertEqual(secret, "jwt-secret")
        self.assertTrue(all(isinstance(command, list) for command in commands))
        self.assertIn("psql", commands[-1])
        self.assertIn("WHERE role='admin'", commands[-1][-1])
        self.assertIn("status='active'", commands[-1][-1])

    def test_load_local_admin_material_prefers_persisted_runtime_jwt_secret(self):
        def run(command):
            if command[2] == "inspect" and command[3] == "sub2api":
                return '["JWT_SECRET=stale-container-secret"]'
            if command[2] == "inspect" and command[3] == "sub2api-postgres":
                return '["POSTGRES_USER=dbuser","POSTGRES_DB=dbname"]'
            if "security_secrets" in command[-1]:
                return "persisted-runtime-secret\n"
            return "1\tadmin@example.com\thash\tadmin\tactive\n"

        _, secret = load_local_admin_material(run=run)

        self.assertEqual(secret, "persisted-runtime-secret")

    def test_build_admin_jwt_rejects_inactive_or_non_admin_identity(self):
        identities = [
            AdminIdentity(1, "a@example.com", "hash", "user", "active"),
            AdminIdentity(1, "a@example.com", "hash", "admin", "inactive"),
        ]

        for identity in identities:
            with self.subTest(identity=identity):
                with self.assertRaises(ValueError):
                    build_admin_jwt(identity, "secret", now=1)


if __name__ == "__main__":
    unittest.main()
