import os
import unittest
from datetime import date
from unittest import mock

TEST_DB_URL = os.environ.get("PLANNER_TEST_DB_URL")
if TEST_DB_URL:
    os.environ["PLANNER_DB_URL"] = TEST_DB_URL

from app import workout_chat

TODAY = date(2026, 11, 27)  # a Friday
LIFTS = [
    # date, exercise, weight, unit, reps
    ("2026-11-14", "Flat Bench", 235, "lb", 3),
    ("2026-11-21", "Flat Bench", 225, "lb", 7),
    ("2026-11-21", "Flat Bench", 200, "lb", 9),
    ("2026-11-21", "Incline DB Press", 70, "lb", 8),
    ("2026-11-25", "HS Dead Lift", 342, "lb", 5),
    ("2026-11-25", "Dead Hang", None, None, 40),
    ("2026-11-25", "DB Stiff Leg Deadlift", 80, "lb", 10),
    ("2026-11-25", "Negative Pull Up", None, None, 3),
    ("2026-11-25", "45 Degree Assisted Pull Ups", None, None, 8),
]
WALKS = [
    # date, activity, miles, km, seconds
    ("2026-10-30", "Work walk", 1.0, "mi", 1200),
    ("2026-11-17", "Work walk", 1.5, "mi", 1800),
    ("2026-11-23", "Work walk", 2.0, "mi", 2400),
    ("2026-11-26", "Outdoor walk", 1.609344, "km", 900),
    ("2026-11-27", "Deep Squat Sit", None, None, 300),
]


class PeriodTests(unittest.TestCase):
    def test_ranges(self):
        for said, expected in (
            ("this week", ("2026-11-23", "2026-11-27")),
            ("last week", ("2026-11-16", "2026-11-22")),
            ("Last Month", ("2026-10-01", "2026-10-31")),
            ("last 7 days", ("2026-11-21", "2026-11-27")),
            ("past 2 weeks", ("2026-11-14", "2026-11-27")),
        ):
            with self.subTest(said=said):
                self.assertEqual(tuple(d.isoformat() for d in workout_chat._range(said, TODAY)), expected)
        self.assertIsNone(workout_chat._range("a while", TODAY))


class ReportTests(unittest.TestCase):
    def test_reports_are_flagged_and_questions_are_not(self):
        for text in ("I walked 2 miles today", "i just benched 225", "I went to the gym"):
            with self.subTest(text=text):
                self.assertIsNotNone(workout_chat.report_note(text))
        self.assertIn("+ button", workout_chat.report_note("I walked 2 miles"))
        self.assertIn("spreadsheet", workout_chat.report_note("I just benched 225"))
        for text in ("how far have I walked this week?", "when did I last bench", "I dusted the fans"):
            with self.subTest(text=text):
                self.assertIsNone(workout_chat.report_note(text))


@unittest.skipUnless(TEST_DB_URL, "PLANNER_TEST_DB_URL not set")
class WorkoutChatTests(unittest.TestCase):
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
            for table in ("lift_sets", "activities", "exercise_aliases"):
                conn.execute(f"DELETE FROM {table}")

    def seed(self):
        with self.db._connect() as conn:
            for position, (on, name, weight, unit, reps) in enumerate(LIFTS):
                conn.execute(
                    "INSERT INTO lift_sets (workout_date, position, exercise, weight, weight_unit, reps) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (on, position, name, weight, unit, reps),
                )
            for on, name, distance, unit, seconds in WALKS:
                conn.execute(
                    "INSERT INTO activities (activity_date, activity, distance, distance_unit, duration_seconds) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (on, name, distance, unit, seconds),
                )

    def test_nothing_logged(self):
        self.assertIn("No lifting", workout_chat.lifts("bench"))
        self.assertIn("No activities", workout_chat.activity_totals("walk"))

    def test_last_time_and_best(self):
        self.seed()
        reply = workout_chat.lifts("flat bench")
        self.assertIn("done on 2 days", reply)
        self.assertIn("Last time: Saturday November 21, 2026 (6 days ago): 225 lb x 7; 200 lb x 9.", reply)
        self.assertIn("Personal best set: 235 lb x 3 on Saturday November 14, 2026", reply)

    def test_finding_the_exercise(self):
        self.seed()
        deadlifts = workout_chat.lifts("deadlifts")
        self.assertIn("HS Dead Lift: done", deadlifts)
        self.assertIn("DB Stiff Leg Deadlift: done", deadlifts)
        pulls = workout_chat.lifts("pull ups")
        self.assertIn("Negative Pull Up: done", pulls)
        self.assertIn("45 Degree Assisted Pull Ups: done", pulls)
        self.assertIn("Flat Bench: done", workout_chat.lifts("bench press"))
        self.assertIn("40 reps (no weight recorded)", workout_chat.lifts("dead hang"))
        self.assertIn("3 exercises match", workout_chat.lifts("dead"))
        missing = workout_chat.lifts("leg press")
        self.assertIn("No logged exercise matches", missing)
        self.assertIn("Incline DB Press", missing)
        self.assertNotIn(" lb x ", missing)

    def test_overview(self):
        self.seed()
        reply = workout_chat.lifts()
        self.assertIn("Wednesday November 25, 2026 (2 days ago): HS Dead Lift, Dead Hang, DB Stiff", reply)
        self.assertIn("Flat Bench: 235 lb x 3 on November 14, 2026.", reply)
        self.assertEqual(reply, workout_chat.lifts("workout"))

    def test_walk_totals(self):
        self.seed()
        self.assertIn("Activity: Work walk, Outdoor walk.", workout_chat.activity_totals("walking"))
        reply = workout_chat.activity_totals("walks")
        self.assertIn("Activity: Work walk, Outdoor walk.", reply)
        self.assertIn("This week (Nov 23 to Nov 27): 2 entries on 2 day(s), 55 min, 3 miles.", reply)
        self.assertIn("Last week (Nov 16 to Nov 22): 1 entry on 1 day(s), 30 min, 1.5 miles.", reply)
        self.assertIn("All time: 4 entries on 4 day(s), 1 h 45 min, 5.5 miles.", reply)
        self.assertIn("Most recent: Outdoor walk on Thursday November 26, 2026 (yesterday)", reply)
        one = workout_chat.activity_totals("work walk", "last month")
        self.assertIn("Last month (Oct 1 to Oct 31): 1 entry on 1 day(s), 20 min, 1 miles.", one)
        self.assertNotIn("This week", one)
        self.assertIn("No logged activity", workout_chat.activity_totals("swim"))

    def test_tools_are_offered_when_relevant(self):
        from app import tools

        self.seed()

        def offered(text):
            return {t["function"]["name"] for t in tools.select_tools([text], False)}

        for text in (
            "when did I last bench?", "how far have I walked this week?", "any new PRs?",
            "what did I do for incline press last time", "how long was my deep squat sit",
            "what's my best leg press?", "what's my max on pull ups",
        ):
            with self.subTest(text=text):
                self.assertLessEqual({"lift_history", "activity_totals"}, offered(text))
        self.assertNotIn("lift_history", offered("add milk to the grocery list for April"))


if __name__ == "__main__":
    unittest.main()
