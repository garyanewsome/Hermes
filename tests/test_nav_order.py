import os
import unittest

TEST_DB_URL = os.environ.get("PLANNER_TEST_DB_URL")
if TEST_DB_URL:
    os.environ["PLANNER_DB_URL"] = TEST_DB_URL


@unittest.skipUnless(TEST_DB_URL, "PLANNER_TEST_DB_URL not set")
class NavOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app import nav_order, planner_db

        assert planner_db.PLANNER_DB_URL == TEST_DB_URL
        planner_db.init_planner_db()
        cls.db = planner_db
        app = FastAPI()
        app.include_router(nav_order.router)
        cls.client = TestClient(app)

    def setUp(self):
        with self.db._connect() as conn:
            conn.execute("DELETE FROM app_settings WHERE key = 'nav_order'")

    tearDown = setUp

    def order(self):
        return self.client.get("/nav-order").json()["order"]

    def test_default_is_empty(self):
        self.assertEqual(self.order(), [])

    def test_saves_and_resets(self):
        self.client.put("/nav-order", json={"order": ["chores", "today", "chores", ""]})
        self.assertEqual(self.order(), ["chores", "today"])
        self.client.put("/nav-order", json={"order": []})
        self.assertEqual(self.order(), [])

    def test_refuses_nonsense(self):
        for body in ({"order": "chat"}, {"order": ["x"] * 51}, {}):
            self.assertEqual(self.client.put("/nav-order", json=body).status_code, 422)


if __name__ == "__main__":
    unittest.main()
