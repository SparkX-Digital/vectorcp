import base64
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from vectorcp.core import Engine, Fault


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vectorcp-test-")
        self.root = Path(self.tmp.name)
        self.engine = Engine(self.root / "state", self.root / "sites", development=True)
        self.password = secrets.token_urlsafe(24)
        self.admin = self.engine.bootstrap({"setup_token": self.engine.setup_token(), "username": "administrator", "name": "Administrator", "password": self.password})
        self.call(self.admin, "accounts.create", {"username": "alice", "name": "Alice", "password": self.password, "storage_mb": 10})
        self.call(self.admin, "accounts.create", {"username": "bob", "name": "Bob", "password": self.password})
        self.alice = self.engine.login({"username": "alice", "password": self.password})
        self.bob = self.engine.login({"username": "bob", "password": self.password})
        self.a_site = self.call(self.alice, "sites.create", {"domain": "alice.example.com"})["id"]
        self.b_site = self.call(self.bob, "sites.create", {"domain": "bob.example.com"})["id"]

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, session, method, data=None, **overrides):
        request = {"method": method, "data": data or {}, "token": session["token"], "csrf": session["csrf"]}
        request.update(overrides)
        return self.engine.dispatch(request)

    def refused(self, status, fn):
        with self.assertRaises(Fault) as caught:
            fn()
        self.assertEqual(caught.exception.status, status)

    def test_bootstrap_cannot_be_claimed_twice(self):
        self.refused(409, self.engine.setup_token)
        self.refused(403, lambda: self.engine.bootstrap({"setup_token": "forged", "username": "intruder", "name": "Intruder", "password": self.password}))

    def test_agent_does_not_trust_frontend_role_claims(self):
        self.refused(403, lambda: self.call(self.alice, "accounts.create", {"username": "eve", "name": "Eve", "password": self.password}, role="admin", user_id=self.admin["user"]["id"]))

    def test_customer_cannot_assign_a_site_to_another_customer(self):
        self.call(self.alice, "sites.create", {"domain": "second.example.com", "user_id": self.bob["user"]["id"]})
        alice = self.call(self.alice, "sites.list")["sites"]
        bob = self.call(self.bob, "sites.list")["sites"]
        self.assertEqual({s["domain"] for s in alice}, {"alice.example.com", "second.example.com"})
        self.assertEqual({s["domain"] for s in bob}, {"bob.example.com"})

    def test_cross_account_read_write_suspend_and_export_are_denied(self):
        for method, data in [("files.list", {}), ("files.read", {"path": "index.html"}), ("files.write", {"path": "index.html", "content": "owned", "revision": "new"}), ("sites.active", {"active": False}), ("backups.create", {})]:
            with self.subTest(method=method):
                self.refused(404, lambda: self.call(self.alice, method, dict(data, site_id=self.b_site)))
        self.assertIn("Your website is ready", (self.root / "sites" / str(self.b_site) / "public/index.html").read_text())

    def test_missing_or_forged_csrf_is_rejected_before_write(self):
        for csrf in ("", "forged"):
            self.refused(403, lambda: self.call(self.alice, "sites.active", {"site_id": self.a_site, "active": False}, csrf=csrf))
        self.assertEqual(self.call(self.alice, "sites.list")["sites"][0]["status"], "active")

    def test_path_traversal_and_hidden_paths_are_refused(self):
        for path in ("/etc/passwd", "../secret", "assets/../../secret", ".ssh/authorized_keys", "foo/../index.html", "a\\b"):
            with self.subTest(path=path):
                self.refused(400, lambda: self.call(self.alice, "files.read", {"site_id": self.a_site, "path": path}))

    def test_symlink_file_and_directory_cannot_escape_the_site(self):
        root = self.root / "sites" / str(self.a_site) / "public"
        secret = self.root / "secret.txt"
        secret.write_text("unrelated private material")
        (root / "leak.txt").symlink_to(secret)
        (root / "escape").symlink_to(self.root, target_is_directory=True)
        self.refused(400, lambda: self.call(self.alice, "files.read", {"site_id": self.a_site, "path": "leak.txt"}))
        self.refused(403, lambda: self.call(self.alice, "files.write", {"site_id": self.a_site, "path": "leak.txt", "content": "changed", "revision": "new"}))
        self.refused(404, lambda: self.call(self.alice, "files.list", {"site_id": self.a_site, "path": "escape"}))
        self.assertEqual(secret.read_text(), "unrelated private material")

    def test_stale_file_save_preserves_the_newer_content(self):
        data = {"site_id": self.a_site, "path": "index.html"}
        original = self.call(self.alice, "files.read", data)
        self.call(self.alice, "files.write", dict(data, content="Newer content", revision=original["revision"]))
        self.refused(409, lambda: self.call(self.alice, "files.write", dict(data, content="Stale content", revision=original["revision"])))
        self.assertEqual(self.call(self.alice, "files.read", data)["content"], "Newer content")

    def test_new_file_and_folder_are_real_and_readable(self):
        self.call(self.alice, "files.mkdir", {"site_id": self.a_site, "path": "assets"})
        self.call(self.alice, "files.write", {"site_id": self.a_site, "path": "assets/style.css", "content": "body { color: green; }", "revision": "new"})
        path = self.root / "sites" / str(self.a_site) / "public/assets/style.css"
        self.assertEqual(path.read_text(), "body { color: green; }")
        self.assertEqual(path.stat().st_mode & 0o777, 0o644)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o755)

    def test_exports_contain_only_the_owned_site_files(self):
        root = self.root / "sites" / str(self.a_site) / "public"
        (root / "symlink.txt").symlink_to(self.root / "state/control.sqlite3")
        (root / ".secret").write_text("excluded")
        backup_id = self.call(self.alice, "backups.create", {"site_id": self.a_site})["id"]
        self.refused(404, lambda: self.call(self.bob, "backups.download", {"id": backup_id}))
        export = self.call(self.alice, "backups.download", {"id": backup_id})
        with tarfile.open(fileobj=io.BytesIO(base64.b64decode(export["base64"])), mode="r:gz") as archive:
            self.assertEqual(archive.getnames(), ["public/index.html"])
            self.assertIn(b"Your website is ready", archive.extractfile("public/index.html").read())

    def test_file_allowance_blocks_writes_without_truncating_existing_files(self):
        root = self.root / "sites" / str(self.a_site) / "public"
        (root / "large.bin").write_bytes(b"x" * (10 * 1024 * 1024))
        data = {"site_id": self.a_site, "path": "index.html"}
        before = self.call(self.alice, "files.read", data)
        self.refused(409, lambda: self.call(self.alice, "files.write", dict(data, content="changed", revision=before["revision"])))
        self.assertEqual(self.call(self.alice, "files.read", data), before)

    def test_domain_config_injection_and_duplicates_are_refused(self):
        for domain in ("bad.com;root /;", "site.com\n}", "-example.com", "example..com", "localhost", "127.0.0.1"):
            self.refused(400, lambda: self.call(self.alice, "sites.create", {"domain": domain}))
        self.refused(409, lambda: self.call(self.bob, "sites.create", {"domain": "alice.example.com"}))

    def test_locking_panel_access_revokes_existing_sessions(self):
        self.call(self.admin, "accounts.active", {"id": self.alice["user"]["id"], "active": False})
        self.refused(401, lambda: self.call(self.alice, "overview"))
        self.refused(401, lambda: self.engine.login({"username": "alice", "password": self.password}))
        self.assertEqual(self.call(self.admin, "sites.list")["sites"][0]["status"], "active")

    def test_customer_cannot_reverse_an_administrator_site_suspension(self):
        self.call(self.admin, "sites.active", {"site_id": self.a_site, "active": False})
        self.refused(403, lambda: self.call(self.alice, "sites.active", {"site_id": self.a_site, "active": True}))
        self.assertEqual(self.call(self.alice, "sites.list")["sites"][0]["status"], "suspended")

    def test_rate_limit_is_durable_and_applies_even_to_a_correct_password(self):
        for _ in range(5):
            self.refused(401, lambda: self.engine.login({"username": "bob", "password": "wrong"}))
        self.refused(429, lambda: self.engine.login({"username": "bob", "password": self.password}))

    def test_audit_history_is_scoped_to_the_customer(self):
        events = self.call(self.alice, "audit")["events"]
        self.assertTrue(events)
        self.assertEqual({r["actor"] for r in events}, {"alice"})
        self.assertFalse(any("bob.example.com" in r["target"] for r in events))

    def test_no_arbitrary_command_operation_exists(self):
        self.refused(404, lambda: self.call(self.admin, "shell", {"command": "id"}))

    def test_file_entry_limit_prevents_unbounded_empty_file_and_folder_creation(self):
        root = self.root / "sites" / str(self.a_site) / "public"
        for i in range(999):
            (root / ("item-%d.txt" % i)).touch()
        self.refused(409, lambda: self.call(self.alice, "files.mkdir", {"site_id": self.a_site, "path": "more"}))
        self.refused(409, lambda: self.call(self.alice, "files.write", {"site_id": self.a_site, "path": "more.txt", "content": "", "revision": "new"}))
        data = {"site_id": self.a_site, "path": "index.html"}
        before = self.call(self.alice, "files.read", data)
        self.call(self.alice, "files.write", dict(data, content="Existing files remain editable", revision=before["revision"]))

    def test_failed_nginx_validation_rolls_back_files_database_and_config(self):
        nginx = self.root / "nginx"
        nginx.mkdir()
        self.engine.nginx = nginx
        self.engine.development = False
        with patch("vectorcp.core.run_fixed", side_effect=[Fault("Rejected configuration", 503), "", ""]) as command:
            self.refused(503, lambda: self.call(self.alice, "sites.create", {"domain": "failed.example.com"}))
        self.assertEqual(command.call_count, 3)
        self.assertEqual(command.call_args_list[0].args[0], ["/usr/sbin/nginx", "-t"])
        self.engine.development = True
        self.assertFalse(list(nginx.iterdir()))
        self.assertEqual(len(list((self.root / "sites").iterdir())), 2)
        self.assertEqual(len(self.call(self.alice, "sites.list")["sites"]), 1)


if __name__ == "__main__":
    unittest.main()
