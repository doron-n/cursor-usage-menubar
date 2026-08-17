from __future__ import annotations

import base64
import inspect
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from cursor_usage_menubar.auth import jwt_sub, read_session, session_cookie
from cursor_usage_menubar.models import Session


def _jwt(sub: str) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    payload = (
        base64.urlsafe_b64encode(json.dumps({"sub": sub}).encode())
        .rstrip(b"=")
        .decode()
    )
    return f"{header}.{payload}.sig"


def _write_db(values: dict[str, str]) -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix=".vscdb", delete=False)
    tmp.close()
    path = Path(tmp.name)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)")
    conn.executemany(
        "INSERT INTO ItemTable (key, value) VALUES (?, ?)",
        list(values.items()),
    )
    conn.commit()
    conn.close()
    return path


class AuthTest(unittest.TestCase):
    def test_cookie_encodes_double_colon(self):
        token = "abc.def.ghi"
        cookie = session_cookie("user_1", token)
        self.assertTrue(cookie.startswith("WorkosCursorSessionToken="))
        self.assertIn("%3A%3A", cookie)
        self.assertNotIn("::", cookie.split("=", 1)[1])

    def test_jwt_sub(self):
        self.assertEqual(jwt_sub(_jwt("user_99")), "user_99")
        self.assertIsNone(jwt_sub("not-a-jwt"))

    def test_read_session_from_sqlite(self):
        token = _jwt("auth0|abc")
        path = _write_db(
            {
                "cursorAuth/accessToken": token,
                "cursorAuth/cachedEmail": "ada@example.com",
                "cursorAuth/stripeMembershipType": "enterprise",
                "cursorAuth/cachedTeam": json.dumps(
                    {"teamId": 42, "name": "Acme"}
                ),
                "cursorAuth/refreshToken": "SHOULD_NEVER_BE_READ",
            }
        )
        try:
            sess = read_session(path)
            self.assertIsNotNone(sess)
            assert sess is not None
            self.assertEqual(sess.email, "ada@example.com")
            self.assertEqual(sess.team_id, 42)
            self.assertEqual(sess.team_name, "Acme")
            self.assertEqual(sess.plan_hint, "enterprise")
            self.assertEqual(sess.sub, "auth0|abc")
            self.assertEqual(sess.access_token, token)
            self.assertFalse(hasattr(sess, "refresh_token"))
        finally:
            path.unlink(missing_ok=True)

    def test_missing_db_returns_none(self):
        self.assertIsNone(read_session(Path("/tmp/does-not-exist-cursor.vscdb")))

    def test_session_dataclass_has_no_refresh_field(self):
        self.assertNotIn("refresh_token", Session.__dataclass_fields__)

    def test_read_session_sql_ignores_refresh_token(self):
        source = inspect.getsource(read_session)
        self.assertNotIn("refreshToken", source)
        self.assertNotIn("refresh_token", source)


if __name__ == "__main__":
    unittest.main()
