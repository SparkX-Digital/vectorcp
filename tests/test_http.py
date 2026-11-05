import http.client
import base64
import hashlib
import json
from pathlib import Path
import secrets
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from vectorcp.agent import Server as AgentServer
from vectorcp.core import Engine
from vectorcp.web import Server as WebServer


class HttpBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="vectorcp-http-")
        root = Path(cls.tmp.name)
        cls.engine = Engine(root / "state", root / "sites", development=True)
        cls.password = secrets.token_urlsafe(24)
        cls.engine.bootstrap({"setup_token": cls.engine.setup_token(), "username": "administrator", "name": "Administrator", "password": cls.password})
        cls.agent = AgentServer(root / "a.sock", cls.engine, 0)
        threading.Thread(target=cls.agent.serve_forever, daemon=True).start()
        cls.web = WebServer(("127.0.0.1", 0), root / "a.sock", "http://127.0.0.1", True)
        cls.port = cls.web.server_address[1]
        cls.origin = "http://127.0.0.1:%d" % cls.port
        cls.web.origin = cls.origin
        threading.Thread(target=cls.web.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.web.shutdown()
        cls.web.server_close()
        cls.agent.shutdown()
        cls.agent.server_close()
        cls.tmp.cleanup()

    def request(self, method="GET", path="/", data=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        base = {"Host": "127.0.0.1:%d" % self.port}
        if method == "POST":
            base.update({"Origin": self.origin, "Content-Type": "application/json"})
        base.update(headers or {})
        connection.request(method, path, body=json.dumps(data) if data is not None else None, headers=base)
        response = connection.getresponse()
        result = (response.status, dict(response.getheaders()), response.read())
        connection.close()
        return result

    def login(self):
        status, headers, body = self.request("POST", "/api", {"method": "login", "data": {"username": "administrator", "password": self.password}})
        self.assertEqual(status, 200)
        return headers["Set-Cookie"].split(";")[0], json.loads(body)["csrf"], headers

    def test_role_entry_paths_serve_the_application(self):
        for path in ('/admin','/reseller','/customer'):
            status, headers, body = self.request(path=path)
            self.assertEqual(status,200)
            self.assertIn(b'/app.js',body)
            self.assertIn("frame-ancestors 'none'",headers['Content-Security-Policy'])

    def test_app_and_assets_have_csp_and_nosniff(self):
        for path in ("/", "/app.js", "/site-batch.js", "/style.css", "/favicon.svg", "/brand.svg", "/brand-light.svg"):
            with self.subTest(path=path):
                status, headers, body = self.request(path=path)
                self.assertEqual(status, 200)
                self.assertTrue(body)
                self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
                self.assertEqual(headers["X-Content-Type-Options"], "nosniff")

    def test_private_paths_are_not_static_files(self):
        self.assertEqual(self.request(path="/../core.py")[0], 404)
        self.assertEqual(self.request(path="/control.sqlite3")[0], 404)

    def test_cross_origin_requests_are_refused(self):
        status, _, _ = self.request("POST", "/api", {"method": "login"}, {"Origin": "https://unrelated.example"})
        self.assertEqual(status, 403)

    def test_dns_rebinding_host_header_is_refused(self):
        self.assertEqual(self.request(headers={"Host": "unrelated.example"})[0], 400)

    def test_body_token_cannot_substitute_for_an_http_only_session_cookie(self):
        cookie, csrf, _ = self.login()
        token = cookie.split("=", 1)[1]
        status, _, _ = self.request("POST", "/api", {"method": "overview", "token": token, "role": "admin", "csrf": csrf})
        self.assertEqual(status, 401)

    def test_mutations_require_csrf_even_with_a_valid_cookie(self):
        cookie, csrf, _ = self.login()
        payload = {"method": "sites.create", "data": {"domain": "http.example.com"}}
        self.assertEqual(self.request("POST", "/api", payload, {"Cookie": cookie})[0], 403)
        self.assertEqual(self.request("POST", "/api", payload, {"Cookie": cookie, "X-CSRF-Token": csrf})[0], 200)

    def test_binary_transfer_operations_use_cookie_csrf_and_exact_content(self):
        cookie, csrf, _ = self.login()
        headers = {'Cookie': cookie, 'X-CSRF-Token': csrf}
        def call(method, data):
            status, _, body = self.request('POST', '/api', {'method': method, 'data': data}, headers)
            self.assertEqual(status, 200, body)
            return json.loads(body)
        site = call('sites.create', {'domain': 'binary-http.example.com'})['id']
        content = bytes(range(256)) * 1100
        info = {'site_id': site, 'path': 'transfer.bin', 'bytes': len(content),
                'sha256': hashlib.sha256(content).hexdigest()}
        self.assertEqual(self.request('POST', '/api', {'method': 'files.upload.start',
            'data': info}, {'Cookie': cookie})[0], 403)
        ticket = call('files.upload.start', info)
        for offset in range(0, len(content), ticket['chunk_bytes']):
            call('files.upload.chunk', {'site_id': site, 'id': ticket['id'], 'offset': offset,
                'base64': base64.b64encode(content[offset:offset + ticket['chunk_bytes']]).decode()})
        call('files.upload.finish', {'site_id': site, 'id': ticket['id']})
        downloaded = call('files.describe', {'site_id': site, 'path': 'transfer.bin'})
        parts = []
        for offset in range(0, len(content), downloaded['chunk_bytes']):
            part = call('files.chunk', {'site_id': site, 'path': 'transfer.bin',
                'revision': downloaded['revision'], 'offset': offset})
            parts.append(base64.b64decode(part['base64']))
        self.assertEqual(b''.join(parts), content)

    def test_cookie_is_http_only_and_strict_and_logout_revokes_it(self):
        cookie, csrf, headers = self.login()
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", headers["Set-Cookie"])
        status, headers, _ = self.request("POST", "/api", {"method": "logout"}, {"Cookie": cookie, "X-CSRF-Token": csrf})
        self.assertEqual(status, 200)
        self.assertIn("Max-Age=0", headers["Set-Cookie"])
        self.assertEqual(self.request("POST", "/api", {"method": "overview"}, {"Cookie": cookie})[0], 401)

    def test_health_check_reaches_both_processes(self):
        status, _, body = self.request(path="/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["agent"], "ready")

    def test_https_origin_sets_a_secure_http_only_cookie(self):
        previous = self.web.origin
        self.web.origin = "https://198.51.100.7"
        try:
            status, headers, body = self.request("POST", "/api", {
                "method": "login", "data": {"username": "administrator", "password": self.password}
            }, {"Host": "198.51.100.7", "Origin": self.web.origin})
            self.assertEqual(status, 200)
            self.assertIn("; Secure", headers["Set-Cookie"])
            self.assertIn("HttpOnly", headers["Set-Cookie"])
            self.assertNotIn("token", json.loads(body))
        finally:
            self.web.origin = previous

    def test_public_https_origin_refuses_http_and_unrelated_origins(self):
        previous = self.web.origin
        self.web.origin = "https://198.51.100.7"
        try:
            for origin in ("http://198.51.100.7", "https://unrelated.example"):
                with self.subTest(origin=origin):
                    status, _, _ = self.request("POST", "/api", {"method": "login"}, {
                        "Host": "198.51.100.7", "Origin": origin})
                    self.assertEqual(status, 403)
        finally:
            self.web.origin = previous

    def test_forwarded_headers_cannot_replace_the_expected_public_host(self):
        previous = self.web.origin
        self.web.origin = "https://198.51.100.7"
        try:
            status, _, _ = self.request(headers={"Host": "unrelated.example",
                "X-Forwarded-Host": "198.51.100.7", "X-Forwarded-Proto": "https"})
            self.assertEqual(status, 400)
            self.assertEqual(self.request(headers={"Host": "198.51.100.7"})[0], 200)
        finally:
            self.web.origin = previous

    def test_mfa_http_flow_sets_cookie_only_after_second_factor_and_keeps_it_private(self):
        from vectorcp.security import totp
        cookie, csrf, _ = self.login()
        password = secrets.token_urlsafe(24)
        headers = {'Cookie': cookie, 'X-CSRF-Token': csrf}
        status, _, body = self.request('POST', '/api', {'method': 'accounts.create', 'data': {
            'username': 'mfa_http', 'name': 'MFA HTTP', 'password': password}}, headers)
        self.assertEqual(status, 200, body)
        status, login_headers, body = self.request('POST', '/api', {'method': 'login', 'data': {
            'username': 'mfa_http', 'password': password}}, {'User-Agent': 'Verified browser'})
        session_cookie = login_headers['Set-Cookie'].split(';')[0]
        session_headers = {'Cookie': session_cookie, 'X-CSRF-Token': json.loads(body)['csrf']}
        status, _, body = self.request('POST', '/api', {'method': 'security.enroll', 'data': {'password': password}}, session_headers)
        self.assertEqual(status, 200, body)
        secret = json.loads(body)['secret']
        step = int(time.time())//30
        with patch('time.time', return_value=step*30+3):
            status, _, body = self.request('POST', '/api', {'method': 'security.confirm', 'data': {
                'password': password, 'verification_code': totp(secret, step)}}, session_headers)
            self.assertEqual(status, 200, body)
            recovery = json.loads(body)['recovery_codes'][0]
            status, pending_headers, body = self.request('POST', '/api', {'method': 'login', 'data': {
                'username': 'mfa_http', 'password': password}})
            self.assertEqual(status, 200, body)
            self.assertEqual(json.loads(body), {'mfa_required': True})
            self.assertNotIn('Set-Cookie', pending_headers)
            self.assertEqual(self.request('POST', '/api', {'method': 'overview'})[0], 401)
            status, final_headers, body = self.request('POST', '/api', {'method': 'login', 'data': {
                'username': 'mfa_http', 'password': password, 'code': recovery}}, {'User-Agent': 'Final browser'})
            self.assertEqual(status, 200, body)
            self.assertIn('HttpOnly', final_headers['Set-Cookie'])
            self.assertNotIn('token', json.loads(body))
            final_cookie = final_headers['Set-Cookie'].split(';')[0]
            status, _, body = self.request('POST', '/api', {'method': 'security.sessions'}, {'Cookie': final_cookie})
            self.assertEqual(status, 200, body)
            self.assertIn('Final browser', body.decode())
            self.assertNotIn(final_cookie.split('=', 1)[1], body.decode())

    def test_password_change_clears_cookie_and_revokes_old_http_session(self):
        cookie, csrf, _ = self.login()
        password, new_password = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        self.assertEqual(self.request('POST', '/api', {'method': 'accounts.create', 'data': {
            'username': 'password_http', 'name': 'Password HTTP', 'password': password}},
            {'Cookie': cookie, 'X-CSRF-Token': csrf})[0], 200)
        status, response_headers, body = self.request('POST', '/api', {'method': 'login', 'data': {
            'username': 'password_http', 'password': password}})
        headers = {'Cookie': response_headers['Set-Cookie'].split(';')[0], 'X-CSRF-Token': json.loads(body)['csrf']}
        status, changed_headers, body = self.request('POST', '/api', {'method': 'security.password', 'data': {
            'password': password, 'new_password': new_password}}, headers)
        self.assertEqual(status, 200, body)
        self.assertIn('Max-Age=0', changed_headers['Set-Cookie'])
        self.assertEqual(self.request('POST', '/api', {'method': 'overview'}, headers)[0], 401)


if __name__ == "__main__":
    unittest.main()
