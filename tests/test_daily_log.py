import os
import unittest
from datetime import date
from unittest import mock

TEST_DB_URL = os.environ.get("PLANNER_TEST_DB_URL")
if TEST_DB_URL:
    os.environ["PLANNER_DB_URL"] = TEST_DB_URL

from app import daily_log

TODAY = date(2026, 11, 27)  # a Friday


@unittest.skipUnless(TEST_DB_URL, "PLANNER_TEST_DB_URL not set")
class DailyLogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app import planner_db

        assert planner_db.PLANNER_DB_URL == TEST_DB_URL
        planner_db.init_planner_db()
        planner_db.init_planner_db()
        cls.db = planner_db
        app = FastAPI()
        app.include_router(daily_log.router)
        cls.client = TestClient(app)

    def setUp(self):
        self.wipe()
        patcher = mock.patch.object(self.db, "_today", return_value=TODAY)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.wipe()

    def wipe(self):
        with self.db._connect() as conn:
            conn.execute("DELETE FROM daily_log")

    def put(self, on="2026-11-27", **fields):
        return self.client.put(f"/daily/{on}", json=fields)

    def get(self, weeks=13):
        return self.client.get(f"/daily?weeks={weeks}").json()

    def test_filled_in_a_piece_at_a_time(self):
        first = self.put(weight=182.456).json()["day"]
        self.assertEqual((first["weight"], first["calories_in"], first["balance"]), (182.46, None, None))
        day = self.put(calories_in=2300, burned_total=2900, burned_active=700, protein_g=180.25).json()["day"]
        self.assertEqual((day["weight"], day["balance"], day["protein_g"]), (182.46, -600, 180.3))
        self.assertEqual(len(self.get()["days"]), 1)

    def test_clearing(self):
        self.put(weight=182, calories_in=2000)
        self.assertIsNone(self.put(weight=None).json()["day"]["weight"])
        self.assertIsNone(self.put(calories_in=None).json()["day"])
        self.assertEqual(self.get()["days"], [])

    def test_bad_values_change_nothing(self):
        self.put(burned_total=2500, burned_active=600)
        before = self.get()
        for on, fields, status in (
            ("2026-11-27", {"burned_active": 2600}, 400),
            ("2026-11-27", {"burned_total": 500}, 400),
            ("2026-11-28", {"weight": 180}, 400),
            ("2026-11-27", {}, 400),
            ("2026-11-27", {"weight": 5}, 422),
            ("2026-11-27", {"calories_in": -1}, 422),
            ("2026-11-27", {"calories": 100}, 422),
            ("2026-11-27", {"weight": "heavy"}, 422),
            ("someday", {"weight": 180}, 422),
        ):
            with self.subTest(on=on, fields=fields):
                self.assertEqual(self.put(on, **fields).status_code, status)
        self.assertEqual(self.get(), before)

    def test_week_averages_use_only_days_with_the_number(self):
        self.put("2026-11-27", weight=182, calories_in=2000, burned_total=2800)
        self.put("2026-11-25", calories_in=2500)
        self.put("2026-11-23", weight=183, burned_total=2600, calories_in=2900)
        self.put("2026-11-22", weight=184)  # Sunday: last week
        data = self.get()
        week = data["this_week"]
        self.assertEqual((week["days"], week["average"]["weight"], week["counts"]["weight"]), (3, 182.5, 2))
        self.assertEqual((week["average"]["calories_in"], week["average"]["balance"], week["counts"]["balance"]), (2467, -250, 2))
        self.assertIsNone(week["average"]["fat_g"])
        self.assertEqual((data["last_week"]["average"]["weight"], data["last_week"]["days"]), (184, 1))

    def test_range(self):
        self.put("2026-11-22", weight=184)
        self.put("2026-08-01", weight=190)
        one = self.get(1)
        self.assertEqual((one["days"], one["last_week"]["days"]), ([], 1))
        self.assertEqual(len(self.get(52)["days"]), 2)


if __name__ == "__main__":
    unittest.main()
