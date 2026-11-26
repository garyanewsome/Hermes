import os
import unittest
from datetime import date, timedelta

TEST_DB_URL = os.environ.get("PLANNER_TEST_DB_URL")
if TEST_DB_URL:
    os.environ["PLANNER_DB_URL"] = TEST_DB_URL

from app import chore_chat

NAMES = ["Dust ceiling fans", "Dust shelves", "Clean dryer vent", "Descale coffee maker", "Flip mattress",
         "Mop kitchen floor", "Vacuum"]
LISTED = [{"name": n} for n in NAMES]


def found(text):
    return [c["name"] for c in chore_chat.find(text, LISTED)]


class MatchingTests(unittest.TestCase):
    def test_matches_how_people_say_it(self):
        for said, expected in (
            ("dusted the ceiling fans", "Dust ceiling fans"),
            ("ceiling fan dusting", "Dust ceiling fans"),
            ("fans", "Dust ceiling fans"),
            ("descaled the coffee maker", "Descale coffee maker"),
            ("flipped my mattress", "Flip mattress"),
            ("mopped the kitchen floor", "Mop kitchen floor"),
            ("vacuumed", "Vacuum"),
            ("DRYER VENT", "Clean dryer vent"),
        ):
            with self.subTest(said=said):
                self.assertEqual(found(said), [expected])

    def test_never_guesses(self):
        for said in ("cleaned the oven", "mop the bathroom floor", "fan the flames", "the", ""):
            with self.subTest(said=said):
                self.assertEqual(found(said), [])

    def test_ambiguous_returns_all(self):
        self.assertEqual(found("dusted"), ["Dust ceiling fans", "Dust shelves"])

    def test_dates(self):
        thursday = date(2026, 11, 26)
        for said, expected in (
            (None, "2026-11-26"), ("Today", "2026-11-26"), ("yesterday", "2026-11-25"),
            ("saturday", "2026-11-21"), ("last Saturday", "2026-11-21"), ("on monday", "2026-11-23"),
            ("thursday", "2026-11-26"), ("last thursday", "2026-11-19"), ("3 days ago", "2026-11-23"),
            ("2 weeks ago", "2026-11-12"), ("2026-10-01", "2026-10-01"),
        ):
            with self.subTest(said=said):
                self.assertEqual(chore_chat.parse_when(said, thursday).isoformat(), expected)
        with self.assertRaises(ValueError):
            chore_chat.parse_when("a while back", thursday)


@unittest.skipUnless(TEST_DB_URL, "PLANNER_TEST_DB_URL not set")
class ChatActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import chores, planner_db

        assert planner_db.PLANNER_DB_URL == TEST_DB_URL
        planner_db.init_planner_db()
        cls.db, cls.chores = planner_db, chores

    def setUp(self):
        with self.db._connect() as conn:
            conn.execute("DELETE FROM chores")
        chore_chat.add("Dust ceiling fans", 60)
        chore_chat.add("Dust shelves")

    def tearDown(self):
        with self.db._connect() as conn:
            conn.execute("DELETE FROM chores")

    def times(self):
        return {c["name"]: c["times"] for c in self.chores.list_chores()}

    def test_log_and_status(self):
        reply = chore_chat.log("ceiling fans", "yesterday")
        self.assertIn('Logged "Dust ceiling fans"', reply)
        status = chore_chat.status("fans")
        self.assertIn("last done yesterday", status)
        self.assertIn("every 60 days", status)
        self.assertNotIn("DUE", status)

    def test_nothing_logged_when_unsure(self):
        for name, when in (("dusted", None), ("oven", None), ("fans", "a while back"),
                           ("fans", str(self.db._today() + timedelta(days=2)))):
            with self.subTest(name=name, when=when):
                self.assertRegex(chore_chat.log(name, when), "(?i)nothing was (saved|logged)")
        self.assertEqual(set(self.times().values()), {0})

    def test_status_when_unsure(self):
        both = chore_chat.status("dusted")
        self.assertIn("Dust ceiling fans:", both)
        self.assertIn("Dust shelves:", both)
        self.assertIn("no chore matching", chore_chat.status("oven"))

    def test_all_and_duplicates(self):
        self.assertIn("never logged", chore_chat.status())
        self.assertIn("Couldn't add", chore_chat.add("dust SHELVES"))
        self.assertIn("Couldn't add", chore_chat.add("x", 99999))

    def offered(self, *texts):
        from app import tools

        return {t["function"]["name"] for t in tools.select_tools(list(texts), False)}

    def test_add_is_only_offered_when_asked_about(self):
        self.assertNotIn("add_chore", self.offered("I cleaned the oven today"))
        self.assertIn("log_chore", self.offered("I cleaned the oven today"))
        self.assertIn("add_chore", self.offered("add a chore to clean the dryer vent"))
        # A bare "yes" to the assistant's question.
        self.assertIn("add_chore", self.offered("There's no chore for that. Add it to your chores?", "yes"))

    def test_mentions(self):
        self.assertTrue(chore_chat.mentions_a_chore("i finally did the ceiling fans"))
        self.assertFalse(chore_chat.mentions_a_chore("what's a good amp for blues?"))


if __name__ == "__main__":
    unittest.main()
