"""A brand-new database: the other tests reuse one that already has every
table, which hides statements that run before their table exists."""

import os
import unittest
from unittest import mock

TEST_DB_URL = os.environ.get("PLANNER_TEST_DB_URL")
if TEST_DB_URL:
    os.environ["PLANNER_DB_URL"] = TEST_DB_URL

from app import planner_db

NAME = "planner_fresh_check"


@unittest.skipUnless(TEST_DB_URL, "PLANNER_TEST_DB_URL not set")
class FreshDatabaseTests(unittest.TestCase):
    def admin(self, statement):
        import psycopg

        with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
            conn.execute(statement)

    def test_setup_from_nothing_and_again(self):
        self.admin(f"DROP DATABASE IF EXISTS {NAME}")
        self.admin(f"CREATE DATABASE {NAME}")
        self.addCleanup(self.admin, f"DROP DATABASE IF EXISTS {NAME} WITH (FORCE)")
        url = TEST_DB_URL.rsplit("/", 1)[0] + f"/{NAME}"
        with mock.patch.object(planner_db, "PLANNER_DB_URL", url):
            planner_db.init_planner_db()
            planner_db.init_planner_db()


if __name__ == "__main__":
    unittest.main()
