import os
import unittest
from datetime import date, timedelta
from unittest import mock

TEST_DB_URL = os.environ.get("PLANNER_TEST_DB_URL")
if TEST_DB_URL:
    os.environ["PLANNER_DB_URL"] = TEST_DB_URL

from app import habit_amounts, habit_chat

TODAY = date(2026, 11, 27)  # a Friday


class PureTests(unittest.TestCase):
    def test_summary_and_chart(self):
        amounts = {TODAY: 45, TODAY - timedelta(days=4): 30, TODAY - timedelta(days=5): 20, TODAY - timedelta(days=18): 10}
        totals = habit_amounts.summary(amounts, TODAY)
        self.assertEqual((totals["today"], totals["this_week"], totals["last_week"]), (45, 75, 20))
        weeks = habit_amounts.chart(amounts, True, TODAY)
        self.assertEqual(
            [(p["date"], p["value"]) for p in weeks["points"]],
            [("2026-11-09", 10), ("2026-11-16", 20), ("2026-11-23", 75)],
        )
        values = habit_amounts.chart(amounts, False, TODAY)
        self.assertEqual([p["value"] for p in values["points"]], [10, 20, 30, 45])
        self.assertEqual(habit_amounts.chart({}, True, TODAY)["points"], [])

    def test_said_numbers(self):
        for text, expected in (
            ("practiced 45 minutes", {45}), ("forty five minutes", {40, 45, 5}), ("read twenty pages", {20}),
            ("half an hour of bass", {0.5}), ("an hour and a half", {1.5}), ("an hour of bass", {1}),
            ("I weigh 182.4", {182.4}), ("practiced bass", set()),
        ):
            with self.subTest(text=text):
                self.assertEqual(habit_chat.said_numbers(text), expected)

    def amount(self, said, amount, unit=None, habit="minutes"):
        token = habit_chat.latest.set(said)
        try:
            return habit_chat._amount(amount, unit, habit)
        finally:
            habit_chat.latest.reset(token)

    def test_amounts_and_units(self):
        self.assertEqual(self.amount("45 min of bass", 45, "min"), 45)
        self.assertEqual(self.amount("2 hours in the studio", 2, "hours"), 120)
        self.assertEqual(self.amount("2 hours in the studio", 2, "minutes"), 120)
        self.assertEqual(self.amount("2 hours in the studio", 2), 120)
        self.assertEqual(self.amount("1.5 hours", 90, "minutes"), 90)
        self.assertEqual(self.amount("an hour of bass", 1), 60)
        self.assertEqual(self.amount("half an hour of bass", 0.5, "hour"), 30)
        self.assertEqual(self.amount("I weigh 182", 182, "pounds", "lbs"), 182)
        for said, amount, unit in (("practiced bass", 30, None), ("played 3 songs", 30, None), ("ran 3 miles", 3, "miles")):
            with self.subTest(said=said), self.assertRaises(ValueError):
                self.amount(said, amount, unit)


@unittest.skipUnless(TEST_DB_URL, "PLANNER_TEST_DB_URL not set")
class HabitAmountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app import planner_db

        assert planner_db.PLANNER_DB_URL == TEST_DB_URL
        planner_db.init_planner_db()
        cls.db = planner_db
        app = FastAPI()
        app.include_router(habit_amounts.router)
        cls.client = TestClient(app)

    def setUp(self):
        self.wipe()
        patcher = mock.patch.object(self.db, "_today", return_value=TODAY)
        patcher.start()
        self.addCleanup(patcher.stop)
        for var in (habit_chat.latest, habit_chat.saved):
            token = var.set(None)
            self.addCleanup(var.reset, token)

    def tearDown(self):
        self.wipe()

    def wipe(self):
        with self.db._connect() as conn:
            conn.execute("DELETE FROM habits")

    def create(self, name="Bass practice", unit="minutes", **fields):
        return self.client.post("/habits", json={"name": name, "unit": unit, **fields}).json()["id"]

    def put(self, habit, amount, on=TODAY, mode="add"):
        return self.client.put(f"/habits/{habit}/amount", json={"date": on.isoformat(), "amount": amount, "mode": mode})

    def habit(self, name="Bass practice"):
        return next(h for h in self.db.list_habits_with_streaks() if h["name"] == name)

    def test_adding_up_and_setting(self):
        habit = self.create()
        self.put(habit, 20)
        self.assertEqual(self.put(habit, 25).json()["amount"], 45)
        self.assertEqual(self.put(habit, 10, mode="set").json()["amount"], 10)
        self.assertEqual(self.habit()["totals"]["this_week"], 10)
        self.assertEqual(self.habit()["streak"], 1)

    def test_replacing(self):
        habit = self.create("Weight", "lbs", add_up=False)
        self.put(habit, 183)
        self.assertEqual(self.put(habit, 182.4).json()["amount"], 182.4)

    def test_a_check_off_keeps_the_number(self):
        habit = self.create()
        self.put(habit, 20)
        self.db.set_habit_log(habit, TODAY, True)
        self.assertEqual(self.habit()["totals"]["today"], 20)
        self.db.set_habit_log(habit, TODAY, False)
        self.assertIsNone(self.habit()["totals"]["today"])
        self.db.set_habit_log(habit, TODAY, True)
        self.put(habit, 15)  # adds to a day logged without a number
        self.assertEqual(self.habit()["totals"]["today"], 15)

    def test_refusals(self):
        habit = self.create()
        plain = self.create("Meditate", "")
        self.assertEqual(self.put(habit, 0).status_code, 422)
        self.assertEqual(self.put(habit, 0.001).status_code, 400)
        self.assertEqual(self.put(habit, 5, TODAY + timedelta(days=1)).status_code, 400)
        self.assertEqual(self.put(plain, 5).status_code, 400)
        self.assertEqual(self.put(999999, 5).status_code, 404)
        self.assertEqual(self.client.post("/habits", json={"name": "Meditate"}).status_code, 400)
        self.assertEqual(self.client.patch("/habits/999999", json={}).status_code, 404)

    def test_settings_keep_numbers_and_history_has_a_chart(self):
        habit = self.create()
        self.put(habit, 20)
        self.client.patch(f"/habits/{habit}", json={"unit": "", "hide_streak": True})
        self.assertIsNone(self.habit()["unit"])
        self.assertTrue(self.habit()["hide_streak"])
        self.client.patch(f"/habits/{habit}", json={"unit": "minutes"})
        history = self.db.habit_history(habit)
        self.assertEqual(history["amounts"], {"2026-11-27": 20})
        self.assertEqual(history["chart"]["points"], [{"date": "2026-11-23", "value": 20}])

    def test_an_older_database_gains_the_columns(self):
        self.db.log_habit("Meditate")
        with self.db._connect() as conn:
            conn.execute("ALTER TABLE habits DROP COLUMN unit, DROP COLUMN add_up, DROP COLUMN hide_streak")
            conn.execute("ALTER TABLE habit_logs DROP COLUMN amount")
        self.db.init_planner_db()
        habit = self.habit("Meditate")
        self.assertEqual((habit["unit"], habit["add_up"], habit["streak"]), (None, True, 1))

    def say(self, text):
        habit_chat.latest.set(text)
        habit_chat.saved.set(set())

    def test_chat_logs_once_per_message(self):
        self.create()
        self.say("practiced bass for 45 minutes")
        reply = habit_chat.log("bass practice session", 45, "minutes")
        self.assertIn("today 45 minutes", reply)
        self.assertIn("Already saved", habit_chat.log("Bass practice", 45))
        self.say("another 15 minutes of bass practice")
        habit_chat.log("practice bass", 15)
        self.assertEqual(self.habit()["totals"]["today"], 60)
        self.assertEqual(len(self.db.list_habits_with_streaks()), 1)

    def test_chat_words_and_dates(self):
        self.create("Studio time")
        self.say("spent 2 hours in the studio yesterday")
        habit_chat.log("studio", 2, "hours", "yesterday")
        self.assertEqual(self.habit("Studio time")["last_7_days"][-2]["amount"], 120)

    def test_chat_refusals_save_nothing(self):
        self.create()
        self.say("practiced bass")
        self.assertTrue(habit_chat.log("bass practice", 30).startswith("NOT SAVED"))
        self.assertFalse(self.habit()["last_7_days"][-1]["logged"])
        self.say("read 20 pages")
        self.assertTrue(habit_chat.log("reading", 20, "pages").startswith("NOT SAVED"))
        self.assertEqual(len(self.db.list_habits_with_streaks()), 1)

    def test_chat_without_a_number_and_plain_habits(self):
        self.create()
        self.say("did my bass practice")
        self.assertIn("Ask how many minutes", habit_chat.log("bass practice"))
        self.say("45")
        habit_chat.log("bass practice", 45)
        self.assertEqual(self.habit()["totals"]["today"], 45)
        self.say("meditated for 10 minutes")
        habit_chat.log("meditate")  # new habits still start as check-offs
        habit_chat.saved.set(set())
        self.assertIn("doesn't track a number", habit_chat.log("meditate", 10, "minutes"))

    def test_reports_get_a_nudge(self):
        self.create()
        for text in ("played bass for an hour yesterday", "I practiced bass"):
            self.assertIsNotNone(habit_chat.report_note(text), text)
        for text in ("what bass should I buy?", "how much did I practice bass", "I walked the dog"):
            self.assertIsNone(habit_chat.report_note(text), text)

    def test_status_and_offering_tools(self):
        habit = self.create("Studio time", hide_streak=True)
        self.put(habit, 90)
        status = habit_chat.status("studio")
        self.assertIn("this week (from Monday) 90 minutes", status)
        self.assertNotIn("streak", status)
        from app import tools

        for text in ("how long was I in the studio this week", "I weigh 182", "practiced for an hour"):
            with self.subTest(text=text):
                offered = {t["function"]["name"] for t in tools.select_tools([text], False)}
                self.assertLessEqual({"log_habit", "habit_status"}, offered)


if __name__ == "__main__":
    unittest.main()
