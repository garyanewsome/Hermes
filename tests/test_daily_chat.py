import os
import unittest
from datetime import date
from unittest import mock

TEST_DB_URL = os.environ.get("PLANNER_TEST_DB_URL")
if TEST_DB_URL:
    os.environ["PLANNER_DB_URL"] = TEST_DB_URL

from app import daily_chat, daily_log, recap, recap_facts

TODAY = date(2026, 11, 27)  # a Friday


class ReportTests(unittest.TestCase):
    def test_reports_and_questions(self):
        for text in ("I weighed 226 this morning", "i weigh in at 225.4", "I ate 2200 calories today", "I had 40g of protein"):
            self.assertIsNotNone(daily_chat.report_note(text), text)
        for text in ("what do I weigh?", "how much protein did I have", "I had 2 coffees", "I walked 2 miles"):
            self.assertIsNone(daily_chat.report_note(text), text)


@unittest.skipUnless(TEST_DB_URL, "PLANNER_TEST_DB_URL not set")
class DailyNumbersTests(unittest.TestCase):
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
            conn.execute("DELETE FROM daily_log")

    def save(self, on, **fields):
        daily_log.save(date.fromisoformat(on), daily_log.DayRequest(**fields))

    def seed(self):
        self.save("2026-11-17", weight=228, calories_in=2400, burned_total=2900, protein_g=160)
        self.save("2026-11-19", weight=227, calories_in=2200, burned_total=2800, protein_g=170)
        self.save("2026-11-24", weight=226, weight_pf=225.2, calories_in=2000, burned_total=2800, protein_g=181, carbs_g=130, fat_g=70)
        self.save("2026-11-26", weight=225, calories_in=2300, burned_total=2600, protein_g=175)
        self.save("2026-11-27", calories_in=900, calories_partial=True, calories_as_of="12:00")

    def test_empty(self):
        self.assertIn("Nothing is in the daily log", daily_chat.numbers())

    def test_overview(self):
        self.seed()
        reply = daily_chat.numbers()
        self.assertIn("Latest home weigh-in: 225 lb on Thursday November 26 (yesterday).", reply)
        self.assertIn("This week so far (from Monday), daily averages: home weight lb 225.5 (2 days)", reply)
        self.assertIn("eaten 2,150 (2 days)", reply)
        self.assertIn("balance 550 deficit (2 days)", reply)
        self.assertIn("week of Nov 16: 227.5, week of Nov 23: 225.5. Overall down 2 lb.", reply)
        self.assertIn("SO FAR as of 12:00", reply)

    def test_periods(self):
        self.seed()
        week = daily_chat.numbers("last week")
        self.assertIn("protein g 165 (2 days)", week)
        self.assertIn("Home weight went from 228 lb", week)
        self.assertIn("down 1 lb", week)
        self.assertIn("eaten 2,300", daily_chat.numbers("yesterday"))
        self.assertIn("eaten 2,000", daily_chat.numbers("tuesday"))
        missing = daily_chat.numbers("2026-11-01")
        self.assertIn("Nothing is logged", missing)
        self.assertNotIn("eaten", missing)
        self.assertIn("couldn't read", daily_chat.numbers("a while back"))

    def test_tools_are_offered(self):
        from app import tools

        for text in ("what's my weight trend?", "how was my protein last week?", "am I in a deficit?", "what did I eat yesterday?"):
            offered = {t["function"]["name"] for t in tools.select_tools([text], False)}
            self.assertIn("daily_numbers", offered, text)

    def test_a_weigh_in_by_chat_is_not_saved(self):
        from app import habit_chat

        with self.db._connect() as conn:
            conn.execute("DELETE FROM habits")
        reply = habit_chat.log("weight", 224)
        self.assertIn("Weigh-ins go in the fitness section", reply)
        self.assertEqual(self.db.list_habits_with_streaks(), [])
        self.assertTrue(habit_chat.log("weigh in").startswith("NOT SAVED"))
        self.assertEqual(self.db.list_habits_with_streaks(), [])

    def test_recap_section(self):
        self.seed()
        facts = recap_facts.week_facts(date(2026, 11, 23))
        body = recap.body(facts)
        self.assertIn("## Body and food", body)
        self.assertIn("- Home weight: average 225.5 lb over 2 weigh-ins, down 2 lb from the week before (227.5 lb)", body)
        self.assertIn("- PF weight: average 225.2 lb over 1 weigh-in", body)
        self.assertIn("- Calories a day: eaten 2,150 (over 2 days), burned 2,700 (over 2 days)", body)
        self.assertIn("- Balance a day: 550 deficit (over 2 days); week before: 550 deficit", body)
        self.assertIn("protein 178 g (week before: 165 g)", body)
        self.assertIsNotNone(recap.check_summary("A 550 deficit and 225.5 lb on average.", body))
        self.assertIsNone(recap.check_summary("You lost 3 lb.", body))

    def test_recap_without_numbers(self):
        facts = recap_facts.week_facts(date(2026, 11, 23))
        self.assertNotIn("Body and food", recap.body(facts))
        del facts["daily"]  # a recap saved before this was tracked
        self.assertNotIn("Body and food", recap.body(facts))


if __name__ == "__main__":
    unittest.main()
