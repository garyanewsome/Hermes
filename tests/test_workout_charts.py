import os
import unittest
from datetime import timedelta

TEST_DB_URL = os.environ.get("PLANNER_TEST_DB_URL")
if TEST_DB_URL:
    os.environ["PLANNER_DB_URL"] = TEST_DB_URL


@unittest.skipUnless(TEST_DB_URL, "PLANNER_TEST_DB_URL not set")
class ChartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app import activities, planner_db, workout_charts, workout_import, workouts

        assert planner_db.PLANNER_DB_URL == TEST_DB_URL
        planner_db.init_planner_db()
        cls.db = planner_db
        app = FastAPI()
        for module in (activities, workouts, workout_import, workout_charts):
            app.include_router(module.router)
        cls.client = TestClient(app)

    def setUp(self):
        with self.db._connect() as conn:
            for table in ("lift_sets", "activities", "walks", "workout_pastes", "workouts", "exercise_aliases"):
                conn.execute(f"DELETE FROM {table}")
        today = self.db._today()
        self.monday = today - timedelta(days=today.weekday())

    tearDown = setUp

    def lift(self, day, line):
        response = self.client.post("/workouts", json={"text": f"WORKOUT {day}\n{line}"})
        self.assertEqual(response.status_code, 200, response.text)

    def activity(self, day, **changes):
        body = {"activity": "Work walk", "date": str(day), "minutes": 20, "distance": 1, **changes}
        self.assertEqual(self.client.post("/activities", json=body).status_code, 200)

    def charts(self, weeks=4):
        return self.client.get(f"/workouts/charts?weeks={weeks}").json()

    def test_empty(self):
        body = self.charts()
        self.assertEqual(len(body["weeks"]), 4)
        self.assertEqual((body["weeks"][-1]["start"], body["weeks"][-1]["volume"]), (str(self.monday), 0))
        self.assertEqual((body["days"], body["activities"], body["bests"]), ([], [], []))

    def test_weekly_volume_and_range(self):
        last_week = self.monday - timedelta(days=1)  # a Sunday belongs to the week before
        too_old = self.monday - timedelta(weeks=4, days=1)
        self.lift(self.monday, "lift | Squat | 100 lb | 5, 5")
        self.lift(last_week, "lift | Squat | 100 kg | 1\nlift | Pull Up | bw | 8")
        self.lift(too_old, "lift | Squat | 500 lb | 1")
        body = self.charts()
        self.assertEqual([w["volume"] for w in body["weeks"]], [0, 0, 220, 1000])
        self.assertEqual([w["sets"] for w in body["weeks"]], [0, 0, 2, 2])
        self.assertEqual(body["weeks"][-1]["gym_days"], 1)
        self.assertEqual([d["date"] for d in body["days"]], [str(last_week), str(self.monday)])
        # Bests are all time, whatever the range.
        squat = next(b for b in body["bests"] if b["exercise"] == "Squat")
        self.assertEqual((squat["weight"], squat["date"]), (500, str(too_old)))

    def test_activities_per_week(self):
        self.activity(self.monday)
        self.activity(self.monday, distance=1.609344, distance_unit="km")
        self.activity(self.monday, activity="Deep Squat Sit", minutes=5, distance=None)
        body = self.charts()
        self.assertEqual([a["activity"] for a in body["activities"]], ["Deep Squat Sit", "Work walk"])
        walk = body["activities"][1]["weeks"][-1]
        self.assertEqual((walk["count"], walk["seconds"], walk["miles"]), (2, 2400, 2.0))
        self.assertEqual((body["days"][0]["activities"], body["days"][0]["sets"]), (3, 0))

    def test_bests_follow_links(self):
        self.lift(self.monday, "lift | Bench | 135 lb | 5\nlift | Flat Bench | 145 lb | 3")
        self.client.post("/workouts/exercises/link", json={"name": "Flat Bench", "same_as": "Bench"})
        [best] = self.charts()["bests"]
        self.assertEqual((best["exercise"], best["weight"], best["reps"]), ("Bench", 145, 3))

    def test_each_day_has_a_top_set(self):
        self.lift(self.monday, "lift | Bench | 135 lb | 5\nlift | Bench | 145 lb | 3")
        [day] = self.client.get("/workouts/exercises/history?name=bench").json()["days"]
        self.assertEqual((day["best"]["weight"], day["best"]["reps"]), (145, 3))

    def test_weeks_are_limited(self):
        for weeks in (0, 105, "many"):
            self.assertEqual(self.client.get(f"/workouts/charts?weeks={weeks}").status_code, 422)


if __name__ == "__main__":
    unittest.main()
