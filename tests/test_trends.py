import os
import unittest
from datetime import date, datetime, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

TEST_DB_URL = os.environ.get("PLANNER_TEST_DB_URL")
if TEST_DB_URL:
    os.environ["PLANNER_DB_URL"] = TEST_DB_URL

THURSDAY = date(2026, 11, 26)
MONDAY = date(2026, 11, 23)
EASTERN = ZoneInfo("America/New_York")
TABLES = ("tasks", "todo_completions", "habits", "chores", "lift_sets", "activities")


@unittest.skipUnless(TEST_DB_URL, "PLANNER_TEST_DB_URL not set")
class TrendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app import planner_db, trends

        assert planner_db.PLANNER_DB_URL == TEST_DB_URL
        planner_db.init_planner_db()
        cls.db = planner_db
        app = FastAPI()
        app.include_router(trends.router)
        cls.client = TestClient(app)

    def setUp(self):
        with self.db._connect() as conn:
            for table in TABLES:
                conn.execute(f"DELETE FROM {table}")
        patcher = mock.patch.object(self.db, "_today", return_value=THURSDAY)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        with self.db._connect() as conn:
            for table in TABLES:
                conn.execute(f"DELETE FROM {table}")

    def run_sql(self, sql, *params):
        with self.db._connect() as conn:
            return conn.execute(sql, params)

    def trends(self, weeks=4):
        return self.client.get(f"/trends?weeks={weeks}").json()

    def test_empty(self):
        body = self.trends()
        self.assertEqual([w["start"] for w in body["weeks"]][-1], str(MONDAY))
        self.assertEqual(len(body["weeks"]), 4)
        self.assertEqual(
            {k: v for k, v in body["weeks"][-1].items() if k != "start"},
            {"tasks": 0, "todos": 0, "habits": 0, "chores": 0, "gym_days": 0, "activity_minutes": 0},
        )
        self.assertIsNone(body["todo_history_since"])

    def test_counts_by_local_week(self):
        # 11pm Sunday Eastern is already Monday in UTC; it belongs to last week.
        sunday_night = datetime(2026, 11, 22, 23, 0, tzinfo=EASTERN)
        monday_morning = datetime(2026, 11, 23, 0, 30, tzinfo=EASTERN)
        for when in (sunday_night, monday_morning):
            self.run_sql(
                "INSERT INTO tasks (title, quadrant, status, completed_at) VALUES ('t', 'do', 'done', %s)", when
            )
            self.run_sql(
                "INSERT INTO todo_completions (item_id, item_text, list_name, completed_at) VALUES (1, 'a', 'b', %s)",
                when,
            )
        self.run_sql("INSERT INTO tasks (title, quadrant) VALUES ('open', 'do')")
        body = self.trends()
        self.assertEqual([w["tasks"] for w in body["weeks"]], [0, 0, 1, 1])
        self.assertEqual([w["todos"] for w in body["weeks"]], [0, 0, 1, 1])
        self.assertEqual(body["todo_history_since"], "2026-11-22")

    def test_habits_chores_and_training(self):
        habit = self.db.get_or_create_habit("Stretch")
        habit_id = habit["id"] if isinstance(habit, dict) else habit
        for day in (MONDAY, THURSDAY, THURSDAY - timedelta(weeks=30)):
            self.db.set_habit_log(habit_id, day, True)
        chore = self.run_sql("INSERT INTO chores (name) VALUES ('Dust') RETURNING id")
        with self.db._connect() as conn:
            chore_id = conn.execute("SELECT id FROM chores").fetchone()["id"]
        self.run_sql("INSERT INTO chore_logs (chore_id, done_date) VALUES (%s, %s)", chore_id, MONDAY)
        for position in (1, 2):
            self.run_sql(
                "INSERT INTO lift_sets (workout_date, position, exercise, reps) VALUES (%s, %s, 'Squat', 5)",
                MONDAY,
                position,
            )
        for seconds in (1200, 600):
            self.run_sql(
                "INSERT INTO activities (activity_date, activity, duration_seconds) VALUES (%s, 'Walk', %s)",
                MONDAY,
                seconds,
            )
        body = self.trends()
        week = body["weeks"][-1]
        self.assertEqual(
            (week["habits"], week["chores"], week["gym_days"], week["activity_minutes"]), (2, 1, 1, 30)
        )
        # The year grid reaches back further than the chart range.
        [grid] = body["habits"]
        self.assertEqual(len(grid["dates"]), 3)
        self.assertEqual(body["habit_grid"]["weeks"], 52)

    def test_weeks_are_limited(self):
        for weeks in (0, 105):
            self.assertEqual(self.client.get(f"/trends?weeks={weeks}").status_code, 422)


if __name__ == "__main__":
    unittest.main()
