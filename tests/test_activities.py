import os
import unittest

TEST_DB_URL = os.environ.get("PLANNER_TEST_DB_URL")
if TEST_DB_URL:
    os.environ["PLANNER_DB_URL"] = TEST_DB_URL


@unittest.skipUnless(TEST_DB_URL, "PLANNER_TEST_DB_URL not set")
class ActivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app import activities, planner_db, workouts

        assert planner_db.PLANNER_DB_URL == TEST_DB_URL
        planner_db.init_planner_db()
        cls.db = planner_db
        app = FastAPI()
        app.include_router(activities.router)
        app.include_router(workouts.router)
        cls.client = TestClient(app)

    def setUp(self):
        with self.db._connect() as conn:
            for table in ("lift_sets", "activities", "walks", "workout_pastes"):
                conn.execute(f"DELETE FROM {table}")

    tearDown = setUp

    def body(self, **changes):
        return {"activity": "Work walk", "date": "2020-01-05", "minutes": 20, "distance": 1.0, **changes}

    def add(self, **changes):
        return self.client.post("/activities", json=self.body(**changes))

    def listing(self):
        return self.client.get("/activities").json()

    def test_each_add_is_its_own_entry(self):
        self.add()
        self.add()
        entries = self.listing()["entries"]
        self.assertEqual(len(entries), 2)
        self.assertEqual(
            (entries[0]["date"], entries[0]["distance"], entries[0]["distance_unit"], entries[0]["duration_seconds"]),
            ("2020-01-05", 1.0, "mi", 1200),
        )

    def test_time_only(self):
        self.assertEqual(self.add(activity="Deep Squat Sit", minutes=5, distance=None).status_code, 200)
        [entry] = self.listing()["entries"]
        self.assertEqual((entry["distance"], entry["distance_unit"], entry["duration_seconds"]), (None, None, 300))

    def test_names_are_offered_again_without_duplicates(self):
        self.assertEqual(self.listing()["types"], ["Work walk", "Walk", "Bike", "Elliptical"])
        self.add(activity="Deep Squat Sit")
        self.add(activity="  deep   squat SIT ")
        self.add(activity="work WALK")
        listing = self.listing()
        self.assertEqual(listing["types"], ["Work walk", "Walk", "Bike", "Elliptical", "Deep Squat Sit"])
        self.assertEqual({e["activity"] for e in listing["entries"]}, {"Deep Squat Sit", "Work walk"})

    def test_bad_entries_are_refused(self):
        for changes in (
            {"activity": "  "}, {"activity": "x" * 81}, {"minutes": 0}, {"minutes": 2000}, {"minutes": 0.001},
            {"distance": 0}, {"distance": 0.001}, {"distance": -1}, {"distance_unit": "furlong"},
            {"date": "2999-01-01"}, {"date": "soon"},
        ):
            with self.subTest(changes=changes):
                self.assertIn(self.add(**changes).status_code, (400, 422))
        self.assertEqual(self.listing()["entries"], [])

    def test_edit_and_delete(self):
        entry_id = self.add().json()["id"]
        response = self.client.put(f"/activities/{entry_id}", json=self.body(minutes=25, distance=None))
        self.assertEqual(response.status_code, 200)
        [entry] = self.listing()["entries"]
        self.assertEqual((entry["duration_seconds"], entry["distance"]), (1500, None))
        self.assertEqual(self.client.delete(f"/activities/{entry_id}").status_code, 200)
        self.assertEqual(self.client.delete(f"/activities/{entry_id}").status_code, 404)
        self.assertEqual(self.client.put(f"/activities/{entry_id}", json=self.body()).status_code, 404)

    def test_paste_never_replaces_entries_added_or_edited_by_hand(self):
        paste = {"text": "WORKOUT 2020-01-05\nwalk | pad | 5 min\nwalk | pad | 6 min"}
        self.add()
        self.client.post("/workouts", json=paste)
        edited = next(e for e in self.listing()["entries"] if e["duration_seconds"] == 360)
        self.client.put(f"/activities/{edited['id']}", json=self.body(activity="pad", minutes=9))
        self.client.post("/workouts", json={"text": "WORKOUT 2020-01-05\nwalk | pad | 7 min"})
        self.assertEqual(
            sorted(e["duration_seconds"] for e in self.listing()["entries"]), [420, 540, 1200]
        )

    def test_shows_in_workout_history(self):
        self.add()
        [day] = self.client.get("/workouts").json()["days"]
        self.assertEqual([a["activity"] for a in day["activities"]], ["Work walk"])

    def test_old_walks_copy_over_once(self):
        with self.db._connect() as conn:
            conn.execute("DROP TABLE activities")  # only ever the throwaway test database
            paste = conn.execute("INSERT INTO workout_pastes (raw_text) VALUES ('x') RETURNING id").fetchone()["id"]
            conn.execute(
                "INSERT INTO walks (paste_id, workout_date, position, activity, duration_seconds) "
                "VALUES (%s, '2020-01-01', 1, 'pad', 600)",
                (paste,),
            )
        self.db.init_planner_db()
        [entry] = self.listing()["entries"]
        self.assertEqual((entry["activity"], entry["duration_seconds"]), ("pad", 600))
        self.client.delete(f"/activities/{entry['id']}")
        self.db.init_planner_db()
        self.assertEqual(self.listing()["entries"], [])


if __name__ == "__main__":
    unittest.main()
