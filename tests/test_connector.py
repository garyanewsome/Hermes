"""The Claude desktop connector: its token-only routes and the local server."""

import io
import json
import os
import sys
import tempfile
import unittest
from datetime import date
from unittest import mock

TEST_DB_URL = os.environ.get("PLANNER_TEST_DB_URL")
if TEST_DB_URL:
    os.environ["PLANNER_DB_URL"] = TEST_DB_URL

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "connector"))

import naradi_connector

from app import connector

TODAY = date(2026, 11, 27)
TOKEN = "t" * 64


def send(*messages):
    replies = io.StringIO()
    lines = io.StringIO("".join(m if isinstance(m, str) else json.dumps(m) + "\n" for m in messages))
    with mock.patch.object(sys, "stdin", lines), mock.patch.object(sys, "stdout", replies):
        naradi_connector.main()
    return [json.loads(line) for line in replies.getvalue().splitlines()]


def rpc(method, ident=1, **params):
    return {"jsonrpc": "2.0", "id": ident, "method": method, "params": params}


class ProtocolTests(unittest.TestCase):
    def test_handshake_and_tools(self):
        replies = send(
            rpc("initialize", protocolVersion="2025-03-26", capabilities={}),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            rpc("tools/list", 2),
            rpc("ping", 3),
            rpc("resources/list", 4),
            "not json\n",
        )
        self.assertEqual(replies[0]["result"]["protocolVersion"], "2025-03-26")
        self.assertEqual(
            [t["name"] for t in replies[1]["result"]["tools"]], ["lift_session", "exercise_history", "personal_bests"]
        )
        self.assertTrue(all(t["annotations"]["readOnlyHint"] for t in replies[1]["result"]["tools"]))
        self.assertEqual([replies[2]["result"], replies[3]["error"]["code"], replies[4]["error"]["code"]], [{}, -32601, -32700])
        self.assertEqual(len(replies), 5)

    def test_problems_come_back_as_tool_errors(self):
        with mock.patch.dict(os.environ, {"NARADI_URL": ""}):
            [reply] = send(rpc("tools/call", name="personal_bests", arguments={}))
        self.assertTrue(reply["result"]["isError"])
        self.assertIn("NARADI_URL", reply["result"]["content"][0]["text"])
        [reply] = send(rpc("tools/call", name="delete_everything", arguments={}))
        self.assertTrue(reply["result"]["isError"])
        with mock.patch.dict(os.environ, {"NARADI_URL": "file:///etc/passwd"}):
            [reply] = send(rpc("tools/call", name="personal_bests"))
        self.assertTrue(reply["result"]["isError"])


class AccessTests(unittest.TestCase):
    """Through the real app, so the auth middleware is what's tested."""

    @classmethod
    def setUpClass(cls):
        """Imports app.main, standing in for heavy libraries that aren't
        installed and for the built frontend it serves."""
        from fastapi.testclient import TestClient

        folder = tempfile.mkdtemp()
        os.mkdir(os.path.join(folder, "static"))
        here, stubbed = os.getcwd(), []
        os.chdir(folder)
        try:
            for _ in range(30):
                try:
                    from app.main import app
                    break
                except ModuleNotFoundError as missing:
                    sys.modules[missing.name] = mock.MagicMock()
                    stubbed.append(missing.name)
        finally:
            os.chdir(here)
            # So other tests still see these as missing.
            for name in stubbed:
                sys.modules.pop(name, None)
        cls.client = TestClient(app)

    def get(self, path, token=TOKEN, configured=TOKEN, method="get"):
        raw = token if isinstance(token, bytes) else (token or "").encode()
        headers = {"Authorization": b"Bearer " + raw} if token else {}
        with mock.patch.object(connector, "CONNECTOR_TOKEN", configured), mock.patch.object(
            connector, "session", return_value="ok"
        ):
            return getattr(self.client, method)(path, headers=headers).status_code

    def test_token_opens_only_the_connector(self):
        self.assertEqual(self.get("/connector/session"), 200)
        for path in ("/workouts", "/daily", "/conversations", "/habits", "/chat", "/connector/../daily"):
            self.assertEqual(self.get(path), 401, path)

    def test_refusals(self):
        self.assertEqual(self.get("/connector/session", token=None), 401)
        self.assertEqual(self.get("/connector/session", token="x" * 64), 401)
        self.assertEqual(self.get("/connector/session", token=b"\xc3\xa9" * 32), 401)  # not ASCII
        self.assertEqual(self.get("/connector/session", configured=""), 404)
        self.assertEqual(self.get("/connector/session", token="short", configured="short"), 404)
        self.assertEqual(self.get("/connector/session", method="post"), 405)
        self.assertEqual(self.get("/connector/session?on=today"), 422)

    def test_a_login_cookie_is_not_needed_and_not_enough(self):
        from app import auth

        self.client.cookies.set(auth.COOKIE_NAME, auth.create_session_token())
        self.addCleanup(self.client.cookies.clear)
        self.assertEqual(self.get("/connector/session", token=None), 401)


@unittest.skipUnless(TEST_DB_URL, "PLANNER_TEST_DB_URL not set")
class SessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import planner_db

        assert planner_db.PLANNER_DB_URL == TEST_DB_URL
        planner_db.init_planner_db()
        cls.db = planner_db

    def setUp(self):
        self.wipe()
        patcher = mock.patch.object(self.db, "_today", return_value=TODAY)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.wipe()

    def wipe(self):
        with self.db._connect() as conn:
            conn.execute("DELETE FROM lift_sets")

    def seed(self):
        with self.db._connect() as conn:
            for position, (on, name, weight, reps) in enumerate(
                [("2026-11-25", "Flat Bench", 230, 7), ("2026-11-25", "Flat Bench", 200, 6), ("2026-11-25", "Dead Hang", None, 40)]
            ):
                conn.execute(
                    "INSERT INTO lift_sets (workout_date, position, exercise, weight, weight_unit, reps) "
                    "VALUES (%s, %s, %s, %s, 'lb', %s)",
                    (on, position, name, weight, reps),
                )

    def test_empty(self):
        self.assertIn("No lifting is logged", connector.session())

    def test_today_missing_says_so(self):
        self.seed()
        text = connector.session()
        self.assertTrue(text.startswith("Nothing is logged for today (2026-11-27)."))
        self.assertIn("Wednesday November 25, 2026", text)

    def test_a_day(self):
        self.seed()
        text = connector.session(date(2026, 11, 25))
        self.assertIn("3 sets, total volume 2,810 lb.", text)
        self.assertIn("Flat Bench:\n  230 lb x 7\n  200 lb x 6\nDead Hang:\n  40 reps (no weight recorded)", text)
        self.assertNotIn("Nothing is logged", text)


if __name__ == "__main__":
    unittest.main()
