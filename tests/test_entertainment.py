import os
import unittest
from datetime import date
from unittest import mock

TEST_DB_URL = os.environ.get("PLANNER_TEST_DB_URL")
if TEST_DB_URL:
    os.environ["PLANNER_DB_URL"] = TEST_DB_URL

from app import entertainment

TODAY = date(2026, 11, 26)
NOTE = """---
tags: [x]
---
## TV

### Star Trek
- Star Trek TOS - ✅
- Star Trek Lower Decks
- Star Trek Strange New Worlds - Season 4

### Others
- 3 Body Problem - Season 2 - 2027.01.14
- Mission - Impossible
- Old Show - Season 3 - ✅
## MOVIES
- Spiderverse 3
- 
"""


def summary(entries):
    return [(e["title"], e["kind"], e["group_name"], e["status"], e["season"], e["return_date"]) for e in entries]


class ParseTests(unittest.TestCase):
    def test_reads_the_note_style(self):
        self.assertEqual(
            summary(entertainment.parse_note(NOTE, TODAY)),
            [
                ("Star Trek TOS", "tv", "Star Trek", "done", None, None),
                ("Star Trek Lower Decks", "tv", "Star Trek", "want", None, None),
                ("Star Trek Strange New Worlds", "tv", "Star Trek", "watching", 4, None),
                ("3 Body Problem", "tv", None, "waiting", 2, "2027-01-14"),
                ("Mission - Impossible", "tv", None, "want", None, None),
                ("Old Show", "tv", None, "done", 3, None),
                ("Spiderverse 3", "movie", None, "want", None, None),
            ],
        )

    def test_odd_lines(self):
        [past] = entertainment.parse_note("- Show - Season 2 - 2026.01.01", TODAY)
        self.assertEqual(past["status"], "watching")  # it's out already
        [bad] = entertainment.parse_note("- Show - 2027.13.40", TODAY)
        self.assertEqual((bad["title"], bad["status"]), ("Show - 2027.13.40", "want"))
        self.assertEqual(entertainment.parse_note("just text\n\n## TV\n-\n- ✅", TODAY), [])


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
        response.json.return_value = {"content": NOTE, "detail": "No note there"}
        return mock.patch.object(entertainment.httpx, "post", return_value=response)

    def test_import_adds_once_and_changes_nothing_existing(self):
        self.add(title="Spiderverse 3", kind="movie", status="done")
        with self.vault():
            preview = self.client.get("/entertainment/import").json()["entries"]
        self.assertEqual([e["exists"] for e in preview], [False] * 6 + [True])
        body = {"entries": [{k: v for k, v in e.items() if k != "exists"} for e in preview]}
        self.assertEqual(self.client.post("/entertainment/import", json=body).json()["added"], 6)
        self.assertEqual(self.client.post("/entertainment/import", json=body).json()["added"], 0)
        statuses = {e["title"]: e["status"] for e in self.entries()}
        self.assertEqual((len(statuses), statuses["Spiderverse 3"]), (7, "done"))
        self.assertEqual([e["title"] for e in self.entries()][1:3], ["Star Trek TOS", "Star Trek Lower Decks"])

    def test_missing_note(self):
        with self.vault(status=404):
            self.assertEqual(self.client.get("/entertainment/import").status_code, 404)


if __name__ == "__main__":
    unittest.main()
