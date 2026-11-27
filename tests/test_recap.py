import os
import unittest
from datetime import date, datetime, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

TEST_DB_URL = os.environ.get("PLANNER_TEST_DB_URL")
if TEST_DB_URL:
    os.environ["PLANNER_DB_URL"] = TEST_DB_URL

from app import recap

EASTERN = ZoneInfo("America/New_York")
MONDAY = date(2026, 11, 16)
TODAY = date(2026, 11, 26)
TABLES = ("recaps", "tasks", "todo_completions", "todo_lists", "habits", "chores", "lift_sets", "activities",
          "exercise_aliases")


def at(day, hour=12):
    return datetime(day.year, day.month, day.day, hour, tzinfo=EASTERN)


class ScheduleTests(unittest.TestCase):
    def test_due_week(self):
        for now, expected in (
            (at(date(2026, 11, 22), 19), date(2026, 11, 9)),  # Sunday before 8pm
            (at(date(2026, 11, 22), 20), MONDAY),
            (at(date(2026, 11, 23), 0), MONDAY),
            (at(date(2026, 11, 28), 23), MONDAY),  # Saturday
            (at(date(2026, 11, 29), 20), date(2026, 11, 23)),
        ):
            with self.subTest(now=now):
                self.assertEqual(recap.due_week(now), expected)


class SummaryCheckTests(unittest.TestCase):
    SOURCE = "2 gym days, 12,700 lb lifted. Stretch: 5 of 7 days. Walk: 1.5 mi"

    def test_keeps_numbers_from_the_facts(self):
        for text in ("You lifted 12700 lb over two gym days.", "Stretch 5 of seven; 1.5 miles walked.",
                     "A good week, and a big one."):
            with self.subTest(text=text):
                self.assertIsNotNone(recap.check_summary(text, self.SOURCE))

    def test_drops_invented_numbers_and_junk(self):
        for text in ("You lifted 13,000 lb.", "That's 71% of days.", "You went three times.", "", "# Heading",
                     "x" * 800):
            with self.subTest(text=text[:30]):
                self.assertIsNone(recap.check_summary(text, self.SOURCE))

    def test_strips_thinking(self):
        self.assertEqual(recap.check_summary("<think>99</think> Nice week.", self.SOURCE), "Nice week.")


@unittest.skipUnless(TEST_DB_URL, "PLANNER_TEST_DB_URL not set")
class RecapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app import planner_db

        assert planner_db.PLANNER_DB_URL == TEST_DB_URL
        planner_db.init_planner_db()
        cls.db = planner_db
        app = FastAPI()
        app.include_router(recap.router)
        cls.client = TestClient(app)

    def setUp(self):
        self.wipe()
        for target, value in ((self.db, ("_today", TODAY)), (recap, ("summarize", "A steady week."))):
            patcher = mock.patch.object(target, value[0], return_value=value[1])
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        self.wipe()

    def wipe(self):
        with self.db._connect() as conn:
            for table in TABLES:
                conn.execute(f"DELETE FROM {table}")

    def sql(self, query, *params):
        with self.db._connect() as conn:
            cursor = conn.execute(query, params)
            return cursor.fetchone() if cursor.description else None

    def seed(self):
        done = "INSERT INTO tasks (title, quadrant, status, completed_at) VALUES (%s, 'do', 'done', %s)"
        self.sql(done, "Mix the single", at(date(2026, 11, 22), 23))
        self.sql(done, "Too late", at(date(2026, 11, 23), 1))
        self.sql("INSERT INTO tasks (title, quadrant, due_date) VALUES ('Invoice', 'do', '2026-11-20')")
        self.sql("INSERT INTO tasks (title, quadrant, due_date) VALUES ('Restring', 'next', '2026-11-25')")
        self.sql(
            "INSERT INTO todo_completions (item_id, item_text, list_name, completed_at) VALUES (1, 'Milk', 'Shop', %s)",
            at(MONDAY),
        )
        habit = self.sql("INSERT INTO habits (name) VALUES ('Stretch') RETURNING id")["id"]
        slipped = self.sql("INSERT INTO habits (name) VALUES ('Guitar') RETURNING id")["id"]
        log = "INSERT INTO habit_logs (habit_id, logged_date) VALUES (%s, %s)"
        for offset in (0, 1, 2, -3):
            self.sql(log, habit, MONDAY + timedelta(days=offset))
        self.sql(log, slipped, MONDAY - timedelta(days=2))
        lift = ("INSERT INTO lift_sets (workout_date, position, exercise, weight, weight_unit, reps) "
                "VALUES (%s, %s, %s, %s, 'lb', %s)")
        self.sql(lift, MONDAY - timedelta(days=7), 1, "Squat", 100, 5)
        self.sql(lift, MONDAY - timedelta(days=7), 2, "Bench", 150, 5)
        self.sql(lift, MONDAY, 1, "Squat", 110, 5)
        self.sql(lift, MONDAY, 2, "Bench", 150, 5)  # a tie is not a new best
        self.sql(lift, MONDAY, 3, "Curl", 30, 10)  # first time is not a record
        chore = self.sql("INSERT INTO chores (name, every_days) VALUES ('Air filter', 5) RETURNING id")["id"]
        self.sql("INSERT INTO chore_logs (chore_id, done_date) VALUES (%s, %s)", chore, MONDAY)
        self.sql(
            "INSERT INTO activities (activity_date, activity, distance, distance_unit, duration_seconds) "
            "VALUES (%s, 'Walk', 1.5, 'mi', 1800)",
            MONDAY,
        )

    def test_facts(self):
        from app import recap_facts

        self.seed()
        facts = recap_facts.week_facts(MONDAY)
        self.assertEqual(facts["tasks_done"], ["Mix the single"])
        self.assertEqual(facts["todos_done"], [{"text": "Milk", "list": "Shop"}])
        habits = {h["name"]: (h["days"], h["previous"]) for h in facts["habits"]}
        self.assertEqual(habits, {"Guitar": (0, 1), "Stretch": (3, 1)})
        self.assertEqual((facts["volume"], facts["previous_volume"]), (1600, 1250))
        self.assertEqual([b["exercise"] for b in facts["new_bests"]], ["Squat"])
        self.assertEqual(facts["activities"], [{"name": "Walk", "count": 1, "minutes": 30, "miles": 1.5}])
        self.assertEqual([t["title"] for t in facts["slipping"]["tasks"]], ["Invoice", "Restring"])
        self.assertEqual(facts["slipping"]["habits"], ["Guitar"])
        self.assertEqual(facts["slipping"]["chores"], ["Air filter"])
        self.assertEqual([u["title"] for u in facts["upcoming"]], ["Restring"])
        text = recap.render(facts, "A steady week.")
        for expected in ("Week of Mon Nov 16 to Sun Nov 22", "A steady week.", "1,600 lb lifted",
                         "New best, Squat: 110 lb × 5 (was 100 lb × 5)", "Stretch: 3 of 7 days"):
            self.assertIn(expected, text)

    def test_empty_week_renders(self):
        from app import recap_facts

        self.assertIn("0 board tasks and 0 todos finished.", recap.render(recap_facts.week_facts(MONDAY), None))

    def vault(self, status=200, path="01 Hermes/Weekly Recaps/Week of 2026-11-16.md"):
        response = mock.Mock(status_code=status)
        response.json.return_value = {"note_path": path, "detail": "Daily write limit reached"}
        return mock.patch.object(recap.httpx, "post", return_value=response)

    def test_scheduled_run_writes_the_vault_once(self):
        with self.vault() as post:
            recap.run_scheduled(at(date(2026, 11, 22), 20))
            recap.run_scheduled(at(date(2026, 11, 23), 9))
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.kwargs["json"]["filename"], "Week of 2026-11-16.md")
        stored = self.client.get("/recaps/latest").json()["recap"]
        self.assertEqual((stored["week_start"], stored["vault_stale"]), ("2026-11-16", False))

    def test_failed_vault_write_is_retried(self):
        with self.vault(status=403):
            recap.run_scheduled(at(date(2026, 11, 23)))
        self.assertIn("limit", recap.latest()["vault_error"])
        with self.vault() as post:
            recap.run_scheduled(at(date(2026, 11, 23)))
        self.assertEqual(post.call_count, 1)
        self.assertIsNone(recap.latest()["vault_error"])

    def test_update_marks_the_vault_copy_stale(self):
        with self.vault() as post:
            recap.run_scheduled(at(date(2026, 11, 23)))
            self.seed()
            body = self.client.post("/recaps/2026-11-16").json()["recap"]
            self.assertEqual(post.call_count, 1)  # updating never writes by itself
        self.assertTrue(body["vault_stale"])
        self.assertIn("Mix the single", body["markdown"])
        with self.vault():
            saved = self.client.post("/recaps/2026-11-16/vault").json()["recap"]
        self.assertFalse(saved["vault_stale"])

    def test_bad_requests(self):
        self.assertEqual(self.client.post("/recaps/2026-11-17").status_code, 400)
        self.assertEqual(self.client.post("/recaps/2026-12-07").status_code, 400)
        self.assertEqual(self.client.post("/recaps/2026-11-09/vault").status_code, 404)
        self.assertIsNone(self.client.get("/recaps/latest").json()["recap"])


if __name__ == "__main__":
    unittest.main()
