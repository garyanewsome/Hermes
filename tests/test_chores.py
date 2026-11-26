import os
import unittest
from datetime import date, timedelta
from unittest import mock

TEST_DB_URL = os.environ.get("PLANNER_TEST_DB_URL")
if TEST_DB_URL:
    os.environ["PLANNER_DB_URL"] = TEST_DB_URL


@unittest.skipUnless(TEST_DB_URL, "PLANNER_TEST_DB_URL not set")
class ChoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app import chores, planner_db

        assert planner_db.PLANNER_DB_URL == TEST_DB_URL
        planner_db.init_planner_db()
        planner_db.init_planner_db()
        cls.db = planner_db
        app = FastAPI()
        app.include_router(chores.router)
        cls.client = TestClient(app)

    def setUp(self):
        with self.db._connect() as conn:
            conn.execute("DELETE FROM chores")
        self.today = self.db._today()

    tearDown = setUp

    def add(self, name="Dust ceiling fans", every=None):
        return self.client.post("/chores", json={"name": name, "every_days": every})

    def only(self):
        [chore] = self.client.get("/chores").json()["chores"]
        return chore

    def log(self, chore_id, days_ago=None):
        body = {} if days_ago is None else {"date": str(self.today - timedelta(days=days_ago))}
        return self.client.post(f"/chores/{chore_id}/log", json=body)

    def history(self, chore_id):
        return self.client.get(f"/chores/{chore_id}/history").json()["dates"]

    def test_new_chore_has_never_been_done(self):
        self.add("  Dust   ceiling fans ")
        chore = self.only()
        self.assertEqual(
            (chore["name"], chore["last_done"], chore["days_ago"], chore["times"], chore["due"]),
            ("Dust ceiling fans", None, None, 0, False),
        )

    def test_logging_keeps_the_chore_and_counts_a_day_once(self):
        self.add()
        chore_id = self.only()["id"]
        self.log(chore_id)
        self.log(chore_id)
        chore = self.only()
        self.assertEqual((chore["days_ago"], chore["times"]), (0, 1))
        self.assertEqual(self.history(chore_id), [str(self.today)])

    def test_backdating_does_not_move_last_done_back(self):
        self.add()
        chore_id = self.only()["id"]
        self.log(chore_id, 3)
        self.log(chore_id, 40)
        self.assertEqual((self.only()["days_ago"], self.only()["times"]), (3, 2))
        self.assertEqual(self.history(chore_id)[0], str(self.today - timedelta(days=3)))

    def test_undo(self):
        self.add()
        chore_id = self.only()["id"]
        self.log(chore_id, 5)
        self.log(chore_id)
        self.assertEqual(self.client.delete(f"/chores/{chore_id}/log/{self.today}").status_code, 200)
        self.assertEqual(self.only()["days_ago"], 5)
        self.assertEqual(self.client.delete(f"/chores/{chore_id}/log/{self.today}").status_code, 404)

    def test_due_only_with_an_interval(self):
        self.add(every=30)
        chore_id = self.only()["id"]
        self.assertTrue(self.only()["due"])
        self.log(chore_id, 29)
        self.assertFalse(self.only()["due"])
        self.client.delete(f"/chores/{chore_id}/log/{self.today - timedelta(days=29)}")
        self.log(chore_id, 30)
        self.assertTrue(self.only()["due"])
        self.client.put(f"/chores/{chore_id}", json={"name": "Dust ceiling fans", "every_days": None})
        self.assertFalse(self.only()["due"])

    def on_today(self, day):
        with mock.patch.object(self.db, "_today", return_value=day):
            body = self.client.get("/chores/today").json()
        return [c["name"] for c in body["chores"]]

    def test_today_page_shows_due_chores_on_weekends_only(self):
        saturday = date(2026, 11, 28)
        for name, every in (("Due", 30), ("Fresh", 30), ("No interval", None), ("Done today", 30)):
            self.add(name, every)
        ids = {c["name"]: c["id"] for c in self.client.get("/chores").json()["chores"]}
        with mock.patch.object(self.db, "_today", return_value=saturday):
            for name, ago in (("Due", 40), ("Fresh", 2), ("No interval", 400), ("Done today", 0)):
                self.client.post(f"/chores/{ids[name]}/log", json={"date": str(saturday - timedelta(days=ago))})
        self.assertEqual(self.on_today(saturday), ["Due", "Done today"])
        for offset in range(2, 7):  # Monday to Friday
            self.assertEqual(self.on_today(saturday + timedelta(days=offset)), [])
        # Still due on Sunday; yesterday's finished one has dropped off.
        self.assertEqual(self.on_today(saturday + timedelta(days=1)), ["Due"])

    def test_never_done_first_then_longest_ago(self):
        for name in ("Recent", "Old", "Never"):
            self.add(name)
        ids = {c["name"]: c["id"] for c in self.client.get("/chores").json()["chores"]}
        self.log(ids["Recent"], 1)
        self.log(ids["Old"], 100)
        self.assertEqual(
            [c["name"] for c in self.client.get("/chores").json()["chores"]], ["Never", "Old", "Recent"]
        )

    def test_names(self):
        self.add("Descale kettle")
        self.assertEqual(self.add("descale  KETTLE").status_code, 400)
        self.assertEqual(self.add("   ").status_code, 400)
        chore_id = self.only()["id"]
        # Renaming to a different capitalisation of itself is fine.
        response = self.client.put(f"/chores/{chore_id}", json={"name": "Descale Kettle"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.only()["name"], "Descale Kettle")

    def test_refusals(self):
        for every in (0, -1, 5000, 1.5):
            self.assertEqual(self.add("x", every).status_code, 422)
        self.add()
        chore_id = self.only()["id"]
        self.assertEqual(self.log(chore_id, -1).status_code, 400)
        self.assertEqual(self.log(999999).status_code, 404)
        self.assertEqual(self.client.get("/chores/999999/history").status_code, 404)
        self.assertEqual(self.client.delete("/chores/999999").status_code, 404)

    def test_delete_takes_history(self):
        self.add()
        chore_id = self.only()["id"]
        self.log(chore_id)
        self.assertEqual(self.client.delete(f"/chores/{chore_id}").json()["chores"], [])
        with self.db._connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) AS n FROM chore_logs").fetchone()["n"], 0)


if __name__ == "__main__":
    unittest.main()
