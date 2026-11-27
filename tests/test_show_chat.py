import os
import unittest
from datetime import date
from unittest import mock

TEST_DB_URL = os.environ.get("PLANNER_TEST_DB_URL")
if TEST_DB_URL:
    os.environ["PLANNER_DB_URL"] = TEST_DB_URL

from app import entertainment, show_chat

TITLES = ["Star Trek Voyager", "Star Trek Strange New Worlds", "3 Body Problem", "You", "Devs", "Spiderverse 3"]
LISTED = [{"title": t} for t in TITLES]


def found(text):
    return [e["title"] for e in show_chat.find(text, LISTED)]


class MatchingTests(unittest.TestCase):
    def test_matches_how_people_say_it(self):
        for said, expected in (
            ("strange new worlds", "Star Trek Strange New Worlds"),
            ("Voyager", "Star Trek Voyager"),
            ("three body problem", "3 Body Problem"),
            ("you", "You"),
            ("Spider-Verse", "Spiderverse 3"),
        ):
            with self.subTest(said=said):
                self.assertEqual(found(said), [expected])

    def test_never_guesses(self):
        for said in ("Severance", "Star Wars", "", "the"):
            with self.subTest(said=said):
                self.assertEqual(found(said), [])
        self.assertEqual(len(found("star trek")), 2)

    def test_title_mentions(self):
        with mock.patch.object(entertainment, "list_entries", return_value={"entries": LISTED}):
            self.assertTrue(show_chat.mentions_a_title("finished 3 body problem last night"))
            self.assertTrue(show_chat.mentions_a_title("I finished Devs"))
            self.assertTrue(show_chat.mentions_a_title("started strange new worlds"))
            self.assertFalse(show_chat.mentions_a_title("can you check my devs board"))
            self.assertFalse(show_chat.mentions_a_title("thank you, that is new to me"))


@unittest.skipUnless(TEST_DB_URL, "PLANNER_TEST_DB_URL not set")
class ChatActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import planner_db

        assert planner_db.PLANNER_DB_URL == TEST_DB_URL
        planner_db.init_planner_db()
        cls.db = planner_db

    def setUp(self):
        self.wipe()
        patcher = mock.patch.object(self.db, "_today", return_value=date(2026, 11, 26))
        patcher.start()
        self.addCleanup(patcher.stop)
        for fields in (
            {"title": "Star Trek Strange New Worlds", "status": "watching", "season": 4, "episode": 2},
            {"title": "3 Body Problem", "status": "waiting", "season": 2, "return_date": "2027-01-14"},
            {"title": "Devs"},
            {"title": "Spiderverse 3", "kind": "movie"},
        ):
            entertainment.add(entertainment.Entry(**fields))
        entertainment._changed.clear()

    def tearDown(self):
        self.wipe()

    def wipe(self):
        with self.db._connect() as conn:
            conn.execute("DELETE FROM entertainment")

    def entry(self, title):
        return next(e for e in entertainment.list_entries()["entries"] if e["title"] == title)

    def place(self, title):
        e = self.entry(title)
        return e["status"], e["season"], e["episode"]

    def test_episode_without_a_title_uses_the_one_being_watched(self):
        self.assertTrue(show_chat.update(episode="4").startswith("Saved."))
        self.assertEqual(self.place("Star Trek Strange New Worlds"), ("watching", 4, 4))
        self.assertTrue(entertainment._changed.is_set())

    def test_without_a_title_it_asks_when_unsure(self):
        show_chat.update("Devs", status="watching")
        reply = show_chat.update(episode=3)
        self.assertTrue(reply.startswith("NOT SAVED"))
        self.assertIn("Devs", reply)
        self.assertIsNone(self.entry("Devs")["episode"])

    def test_new_season_clears_the_episode(self):
        show_chat.update("strange new worlds", season=5)
        self.assertEqual(self.place("Star Trek Strange New Worlds"), ("watching", 5, None))

    def test_finishing_and_starting(self):
        show_chat.update("devs", status="done")
        self.assertEqual(self.entry("Devs")["status"], "done")
        show_chat.update("three body problem", episode=1)
        entry = self.entry("3 Body Problem")
        self.assertEqual((entry["status"], entry["episode"], entry["return_date"]), ("watching", 1, None))
        show_chat.update("spiderverse", status="done", episode=3)
        self.assertEqual(self.place("Spiderverse 3"), ("done", None, None))

    def test_nothing_is_saved_for_bad_requests(self):
        before = entertainment.list_entries()
        for kwargs in (
            {"title": "Severance", "episode": 2}, {"title": "Devs"}, {"title": "Devs", "status": "seen"},
            {"title": "Devs", "episode": "four"}, {"title": "Devs", "season": 9999},
        ):
            with self.subTest(kwargs=kwargs):
                self.assertTrue(show_chat.update(**kwargs).startswith("NOT SAVED"))
        self.assertEqual(entertainment.list_entries(), before)
        self.assertFalse(entertainment._changed.is_set())

    def heard(self, text):
        token = show_chat.said.set(text)
        self.addCleanup(show_chat.said.reset, token)

    def test_numbers_nobody_said_are_ignored(self):
        self.heard("I'm on episode two of Devs")
        show_chat.update("Devs", season=1, episode=2)
        self.assertEqual(self.place("Devs"), ("watching", None, 2))
        self.heard("another strange new worlds down")
        self.assertTrue(show_chat.update("strange new worlds", episode=3).startswith("NOT SAVED"))
        self.heard("watched S5E3")
        show_chat.update("strange new worlds", season=5, episode=3)
        self.assertEqual(self.place("Star Trek Strange New Worlds"), ("watching", 5, 3))

    def test_another_episode_counts_up(self):
        for said, expected in (("watched another episode", 3), ("saw the next ep", 4)):
            token = show_chat.latest.set(said)
            self.addCleanup(show_chat.latest.reset, token)
            show_chat.update("strange new worlds")
            self.assertEqual(self.entry("Star Trek Strange New Worlds")["episode"], expected)

    def test_finishing_a_season_waits_for_the_next(self):
        for kwargs in ({"finished_season": 4}, {"season": 4, "status": "done"}):
            with self.subTest(kwargs=kwargs):
                self.heard("finished season 4 of strange new worlds")
                reply = show_chat.update("strange new worlds", **kwargs)
                self.assertIn("waiting for season 5", reply)
                self.assertEqual(self.place("Star Trek Strange New Worlds"), ("waiting", 5, None))
        self.heard("season 4 was the final season, strange new worlds is done")
        show_chat.update("strange new worlds", season=4, status="done")
        self.assertEqual(self.entry("Star Trek Strange New Worlds")["status"], "done")

    def test_add_with_a_place(self):
        self.heard("I watched episode 5 of Severance yes please")
        show_chat.add("Severance", "tv", "want", season=1, episode=5)
        self.assertEqual(self.place("Severance"), ("watching", None, 5))

    def test_status(self):
        everything = show_chat.status()
        self.assertIn("season 4, watched through episode 2", everything)
        self.assertIn("waiting for season 2, which comes out Thursday January 14, 2027 (in 49 days)", everything)
        self.assertIn("Want to watch, TV (1): Devs.", everything)
        self.assertIn("Want to watch, movies (1): Spiderverse 3.", everything)
        self.assertIn("isn't on the list", show_chat.status("Severance"))

    def test_add(self):
        self.assertTrue(show_chat.add("Severance", "tv").startswith("Added"))
        self.assertEqual(self.entry("Severance")["status"], "want")
        self.assertTrue(show_chat.add("devs").startswith("NOT ADDED"))
        show_chat.add("Dune", "film", "seen")
        self.assertEqual((self.entry("Dune")["kind"], self.entry("Dune")["status"]), ("movie", "want"))

    def test_tools_are_offered_when_relevant(self):
        from app import tools

        def offered(text):
            return {t["function"]["name"] for t in tools.select_tools([text], False)}

        self.assertLessEqual({"show_status", "update_show"}, offered("I am on episode 4"))
        self.assertNotIn("add_show", offered("what was I watching?"))
        self.assertIn("add_show", offered("add Severance to my watch list"))
        self.assertIn("update_show", offered("finished strange new worlds"))
        self.assertNotIn("update_show", offered("add milk to the grocery list"))
        self.assertLessEqual({"add_show", "add_todo_item"}, offered("add Severance to my list"))
        reply = show_chat.update("Severance", episode=5)
        asked = reply.split('nothing else: "')[1].rstrip('"')
        self.assertIn("add_show", {t["function"]["name"] for t in tools.select_tools([asked, "yes please"], False)})


if __name__ == "__main__":
    unittest.main()
