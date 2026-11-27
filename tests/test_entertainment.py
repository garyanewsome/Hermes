import os
import unittest
from datetime import date
from unittest import mock

TEST_DB_URL = os.environ.get("PLANNER_TEST_DB_URL")
if TEST_DB_URL:
    os.environ["PLANNER_DB_URL"] = TEST_DB_URL

from app import entertainment

TODAY = date(2026, 11, 26)
def entry(title, **fields):
    blank = dict.fromkeys(entertainment.FIELDS)
    return {**blank, "title": title, "kind": "tv", "status": "want", **fields}


class RenderTests(unittest.TestCase):
    def test_note_style(self):
        note = entertainment.render(
            [
                entry("Spiderverse 3", kind="movie"),
                entry("Devs", season=1, episode=3, status="watching", where_to_watch="Hulu", note="so\ngood"),
                entry("TOS", group_name="Star Trek", status="done"),
                entry("3 Body Problem", season=2, status="waiting", return_date="2027-01-14"),
                entry("You", status="paused"),
                entry("Later", status="waiting"),
            ]
        )
        self.assertEqual(
            note.split("\n")[1:],
            [
                "",
                "## TV",
                "",
                "### Star Trek",
                "- TOS - ✅",
                "",
                "### Others",
                "- Devs - Season 1, watched E3 - on Hulu - ▶️ watching",
                "    - so good",
                "- 3 Body Problem - Season 2 - 2027.01.14",
                "- You - ⏸️ paused",
                "- Later - ⏳ waiting",
                "",
                "## Movies",
                "",
                "- Spiderverse 3",
                "",
            ],
        )

    def test_no_others_heading_without_groups(self):
        self.assertNotIn("###", entertainment.render([entry("Devs")]))


@unittest.skipUnless(TEST_DB_URL, "PLANNER_TEST_DB_URL not set")
class EntertainmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app import planner_db

        assert planner_db.PLANNER_DB_URL == TEST_DB_URL
        planner_db.init_planner_db()
        cls.db = planner_db
        app = FastAPI()
        app.include_router(entertainment.router)
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
            conn.execute("DELETE FROM entertainment")

    def add(self, **fields):
        return self.client.post("/entertainment", json={"title": "Devs", **fields})

    def entries(self):
        return self.client.get("/entertainment").json()["entries"]

    def test_add_edit_delete(self):
        self.assertEqual(self.add(status="waiting", return_date="2027-01-14").status_code, 200)
        [entry] = self.entries()
        self.assertEqual((entry["days_until"], entry["kind"]), (49, "tv"))
        body = {"title": "Devs", "status": "watching", "season": 1, "episode": 3}
        self.assertEqual(self.client.put(f"/entertainment/{entry['id']}", json=body).status_code, 200)
        [entry] = self.entries()
        self.assertEqual((entry["episode"], entry["return_date"]), (3, None))
        self.assertEqual(self.client.delete(f"/entertainment/{entry['id']}").status_code, 200)
        self.assertEqual(self.client.delete(f"/entertainment/{entry['id']}").status_code, 404)

    def test_titles_are_unique_per_kind(self):
        self.add()
        self.assertEqual(self.add(title="  DEVS ").status_code, 400)
        self.assertEqual(self.add(kind="movie").status_code, 200)
        self.assertEqual(self.add(title="  ").status_code, 400)

    def test_movies_have_no_episodes(self):
        self.add(kind="movie", season=2, episode=4)
        self.assertEqual((self.entries()[0]["season"], self.entries()[0]["episode"]), (None, None))

    def test_bad_values(self):
        for fields in ({"status": "seen"}, {"kind": "book"}, {"season": 0}, {"episode": -1}, {"return_date": "soon"}):
            with self.subTest(fields=fields):
                self.assertEqual(self.add(**fields).status_code, 422)

    def vault(self, status=200):
        response = mock.Mock(status_code=status)
        response.json.return_value = {"detail": "Not allowed there"}
        return mock.patch.object(entertainment.httpx, "post", return_value=response)

    def test_changes_ask_for_the_note_to_be_rewritten(self):
        entertainment._changed.clear()
        self.assertEqual(self.add().status_code, 200)
        self.assertTrue(entertainment._changed.is_set())
        entertainment._changed.clear()
        self.add()  # refused as a duplicate
        self.assertFalse(entertainment._changed.is_set())
        self.client.delete(f"/entertainment/{self.entries()[0]['id']}")
        self.assertTrue(entertainment._changed.is_set())

    def test_write_note(self):
        self.add()
        with self.vault() as post:
            self.assertTrue(entertainment.write_note())
        sent = post.call_args.kwargs["json"]
        self.assertTrue(post.call_args.args[0].endswith("/owned/write"))
        self.assertEqual((sent["path"], sent["source"]), ("01 Hermes/Entertainment.md", "hermes-sync"))
        self.assertIn("- Devs", sent["content"])

    def test_startup_never_blanks_the_note(self):
        with self.vault() as post:
            self.assertTrue(entertainment.write_note(skip_empty=True))
            post.assert_not_called()
            entertainment.write_note()  # emptied by the user
            post.assert_called_once()

    def test_failures_show_on_the_page_until_a_write_works(self):
        self.add()
        for status, words in ((403, "Not allowed there"), (404, "needs updating")):
            with self.vault(status=status):
                self.assertFalse(entertainment.write_note())
            self.assertIn(words, self.client.get("/entertainment").json()["vault"]["error"])
        with mock.patch.object(entertainment.httpx, "post", side_effect=entertainment.httpx.ConnectError("x")):
            self.assertFalse(entertainment.write_note())
        with self.vault():
            entertainment.write_note()
        self.assertIsNone(self.client.get("/entertainment").json()["vault"]["error"])


if __name__ == "__main__":
    unittest.main()
