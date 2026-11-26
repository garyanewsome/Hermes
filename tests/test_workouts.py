import os
import unittest
from datetime import date

from app import workout_parser

TEST_DB_URL = os.environ.get("PLANNER_TEST_DB_URL")
if TEST_DB_URL:
    os.environ["PLANNER_DB_URL"] = TEST_DB_URL

TODAY = date(2026, 11, 26)


def parse(text):
    return workout_parser.parse(text, TODAY)


class ParserTests(unittest.TestCase):
    def test_lifts_and_walks(self):
        result = parse(
            "```\nWORKOUT 2026-11-26\nlift | Bench  Press | 135 lbs | 8, 8, 7\n"
            "Lift|Pull Up|bw|3x6\nlift | Dip | bw+25 lb | 8\nlift | Row | 60.5 KG | 5\n"
            "walk | walking pad | 1.5 mi | 30 min\nwalk | walking pad | 1:05:00\n```"
        )
        self.assertEqual(result["errors"], [])
        [day] = result["days"]
        self.assertEqual(
            day["lifts"][0],
            {"exercise": "Bench Press", "bodyweight": False, "weight": 135.0, "unit": "lb", "reps": [8, 8, 7]},
        )
        self.assertEqual(day["lifts"][1]["reps"], [6, 6, 6])
        self.assertIsNone(day["lifts"][1]["weight"])
        self.assertEqual((day["lifts"][2]["bodyweight"], day["lifts"][2]["weight"]), (True, 25.0))
        self.assertEqual(day["lifts"][3]["unit"], "kg")
        self.assertEqual(day["walks"][0]["duration_seconds"], 1800)
        self.assertEqual(day["walks"][1]["duration_seconds"], 3900)
        self.assertIsNone(day["walks"][1]["distance"])

    def test_several_days_sorted_and_merged(self):
        result = parse(
            "WORKOUT 2026-11-25\nwalk | pad | 10 min\nWORKOUT 2026-11-24\nwalk | pad | 5 min\n"
            "WORKOUT 2026-11-25\nwalk | pad | 20 min"
        )
        self.assertEqual([d["date"] for d in result["days"]], ["2026-11-24", "2026-11-25"])
        self.assertEqual(len(result["days"][1]["walks"]), 2)

    def test_bad_lines_are_reported_with_line_numbers(self):
        for line in (
            "lift | Bench | 135 | 8",
            "lift | Bench | 135 lb | eight",
            "lift | Bench | 135 lb | 0",
            "lift | Bench | 135 lb | 99x8",
            "lift | Bench | 135 lb",
            "lift |  | 135 lb | 8",
            "lift | Bench | 9999 lb | 8",
            "lift | Bench | nan lb | 8",
            "walk | pad | far",
            "walk | pad | 0 min",
            "walk | pad | 1 mi | 2 mi",
            "walk | pad",
            "swim | pool | 30 min",
            "Bench 135x8",
        ):
            with self.subTest(line=line):
                result = parse(f"WORKOUT 2026-11-26\n{line}")
                self.assertEqual([e["line"] for e in result["errors"]], [2])

    def test_bad_headers(self):
        for header in ("WORKOUT 2026-02-30", "WORKOUT 2027-01-01", "WORKOUT yesterday"):
            with self.subTest(header=header):
                result = parse(f"WORKOUT 2026-11-20\nwalk | pad | 5 min\n{header}\nwalk | pad | 5 min")
                self.assertEqual([e["line"] for e in result["errors"]], [3])
                # Lines under a bad header must not drift into the day above.
                self.assertEqual(len(result["days"][0]["walks"]), 1)

    def test_empty_and_headerless(self):
        for text in ("", "```\n```", "WORKOUT 2026-11-26", "walk | pad | 5 min"):
            with self.subTest(text=text):
                self.assertTrue(parse(text)["errors"])


@unittest.skipUnless(TEST_DB_URL, "PLANNER_TEST_DB_URL not set")
class StorageTests(unittest.TestCase):
    PASTE = "WORKOUT 2020-01-02\nlift | Squat | 185 lb | 3x5\nwalk | pad | 1 mi | 20 min"

    @classmethod
    def setUpClass(cls):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app import planner_db, workouts

        assert planner_db.PLANNER_DB_URL == TEST_DB_URL
        planner_db.init_planner_db()
        cls.db = planner_db
        app = FastAPI()
        app.include_router(workouts.router)
        cls.client = TestClient(app)

    def setUp(self):
        self.wipe()

    tearDown = setUp

    def wipe(self):
        with self.db._connect() as conn:
            for table in ("lift_sets", "activities", "walks", "workout_pastes"):
                conn.execute(f"DELETE FROM {table}")

    def save(self, text):
        return self.client.post("/workouts", json={"text": text})

    def day(self):
        [day] = self.client.get("/workouts").json()["days"]
        return day

    def test_preview_saves_nothing(self):
        response = self.client.post("/workouts/preview", json={"text": self.PASTE})
        self.assertEqual(response.json()["days"][0]["replaces"], {"lift_sets": 0, "walks": 0})
        self.assertEqual(self.client.get("/workouts").json()["days"], [])

    def test_save_twice_does_not_duplicate(self):
        self.assertEqual(self.save(self.PASTE).status_code, 200)
        self.assertEqual(self.save(self.PASTE).status_code, 200)
        day = self.day()
        self.assertEqual((len(day["sets"]), len(day["activities"])), (3, 1))
        self.assertEqual(day["sets"][0]["weight"], 185.0)

    def test_replacing_one_kind_keeps_the_other(self):
        self.save(self.PASTE)
        text = "WORKOUT 2020-01-02\nwalk | pad | 2 mi"
        preview = self.client.post("/workouts/preview", json={"text": text}).json()
        self.assertEqual(preview["days"][0]["replaces"], {"lift_sets": 0, "walks": 1})
        self.save(text)
        day = self.day()
        self.assertEqual(len(day["sets"]), 3)
        self.assertEqual([w["distance"] for w in day["activities"]], [2.0])

    def test_any_error_saves_nothing(self):
        self.save(self.PASTE)
        response = self.save("WORKOUT 2020-01-02\nlift | Squat | 200 lb | 5\nlift | oops")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"][0]["line"], 3)
        self.assertEqual(len(self.day()["sets"]), 3)

    def test_date_range_and_order(self):
        self.save("WORKOUT 2020-01-01\nwalk | pad | 5 min\nWORKOUT 2020-01-03\nwalk | pad | 5 min")
        dates = lambda query: [d["date"] for d in self.client.get(f"/workouts{query}").json()["days"]]
        self.assertEqual(dates(""), ["2020-01-03", "2020-01-01"])
        self.assertEqual(dates("?start=2020-01-02"), ["2020-01-03"])
        self.assertEqual(dates("?end=2020-01-02"), ["2020-01-01"])

    def test_doc_example_parses(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "docs", "workout-format.md")) as handle:
            block = handle.read().split("```")[1]
        self.assertEqual(parse(block)["errors"], [])


if __name__ == "__main__":
    unittest.main()
