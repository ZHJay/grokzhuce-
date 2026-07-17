import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from http_json import SecureJSONTransport, validate_base_url
from sub2api_client import Sub2APIError


class ServerFixture:
    def __init__(self, handler):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return f"http://127.0.0.1:{self.server.server_port}/api/v1"

    def __exit__(self, *_):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


class QuietHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass


class SecureJSONTransportTest(unittest.TestCase):
    def test_base_url_allows_loopback_http_or_https_only(self):
        accepted = [
            "http://127.0.0.1:8080/api/v1",
            "http://[::1]:8080/api/v1",
            "http://localhost:8080/api/v1",
            "https://sub2api.example.com/api/v1",
        ]
        rejected = [
            "http://example.com/api/v1",
            "http://127.0.0.1:8080/wrong",
            "http://user:pass@127.0.0.1:8080/api/v1",
            "http://127.0.0.1:8080/api/v1?next=evil",
            "file:///api/v1",
        ]

        for value in accepted:
            with self.subTest(value=value):
                self.assertEqual(validate_base_url(value), value)
        for value in rejected:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_base_url(value)

    def test_environment_proxy_never_receives_admin_jwt_or_sso(self):
        proxy_requests = []

        class ProxyHandler(QuietHandler):
            def do_POST(self):
                proxy_requests.append((self.headers, self.rfile.read()))
                self.send_response(502)
                self.end_headers()

        with ServerFixture(ProxyHandler) as proxy_base_url:
            proxy_origin = proxy_base_url.removesuffix("/api/v1")
            environment = {
                "HTTP_PROXY": proxy_origin,
                "http_proxy": proxy_origin,
                "NO_PROXY": "",
                "no_proxy": "",
            }
            with mock.patch.dict(os.environ, environment, clear=False):
                transport = SecureJSONTransport(
                    "http://127.0.0.2:9/api/v1", lambda: "admin-jwt"
                )
                with self.assertRaises(Sub2APIError):
                    transport(
                        "POST",
                        "/admin/grok/sso-to-oauth",
                        {"sso_tokens": ["sso-secret"]},
                        1,
                    )

        self.assertEqual(proxy_requests, [])

    def test_redirect_is_not_followed_with_admin_jwt_or_sso(self):
        target_requests = []

        class TargetHandler(QuietHandler):
            def do_POST(self):
                target_requests.append((self.headers, self.rfile.read()))
                self.send_response(200)
                self.end_headers()

        with ServerFixture(TargetHandler) as target_url:
            class RedirectHandler(QuietHandler):
                def do_POST(self):
                    self.send_response(302)
                    self.send_header("Location", f"{target_url}/steal")
                    self.end_headers()

            with ServerFixture(RedirectHandler) as source_url:
                transport = SecureJSONTransport(source_url, lambda: "admin-jwt")
                with self.assertRaisesRegex(Sub2APIError, "HTTP 302"):
                    transport(
                        "POST",
                        "/admin/grok/sso-to-oauth",
                        {"sso_tokens": ["sso-secret"]},
                        2,
                    )

        self.assertEqual(target_requests, [])

    def test_json_array_http_error_is_safely_normalized(self):
        class ArrayErrorHandler(QuietHandler):
            def do_GET(self):
                body = b"[]"
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        with ServerFixture(ArrayErrorHandler) as base_url:
            transport = SecureJSONTransport(base_url, lambda: "admin-jwt")
            with self.assertRaisesRegex(Sub2APIError, r"HTTP 400 \(UNKNOWN\)"):
                transport("GET", "/admin/groups/all", None, 2)

    def test_token_provider_is_evaluated_for_every_request(self):
        authorization_headers = []

        class SuccessHandler(QuietHandler):
            def do_GET(self):
                authorization_headers.append(self.headers.get("Authorization"))
                body = json.dumps({"code": 0, "data": []}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        tokens = iter(["token-one", "token-two"])
        with ServerFixture(SuccessHandler) as base_url:
            transport = SecureJSONTransport(base_url, lambda: next(tokens))
            transport("GET", "/admin/groups/all", None, 2)
            transport("GET", "/admin/groups/all", None, 2)

        self.assertEqual(
            authorization_headers, ["Bearer token-one", "Bearer token-two"]
        )


if __name__ == "__main__":
    unittest.main()
