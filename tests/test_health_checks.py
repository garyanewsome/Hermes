import unittest
from unittest import mock

import httpx

from app import health_checks


def _response(status: int, body: dict) -> httpx.Response:
    return httpx.Response(status, json=body)


class VaultKeeperCheckTest(unittest.TestCase):
    def run_check(self, *outcomes):
        with mock.patch.object(health_checks.httpx, "get", side_effect=list(outcomes)) as get, \
                mock.patch.object(health_checks.time, "sleep") as sleep:
            return health_checks._check_vault_keeper(), get, sleep

    def test_pass_asks_once(self):
        result, get, sleep = self.run_check(_response(200, {"status": "ok"}))
        self.assertTrue(result["ok"])
        self.assertEqual(get.call_count, 1)
        sleep.assert_not_called()

    def test_one_timeout_is_not_an_alert(self):
        result, get, sleep = self.run_check(httpx.ReadTimeout("slow"), _response(200, {"status": "ok"}))
        self.assertTrue(result["ok"])
        self.assertEqual(get.call_count, 2)
        sleep.assert_called_once_with(health_checks.VAULT_RETRY_DELAY)

    def test_two_timeouts_alert(self):
        result, get, _ = self.run_check(httpx.ReadTimeout("slow"), httpx.ReadTimeout("slow"))
        self.assertFalse(result["ok"])
        self.assertIn("ReadTimeout", result["text"])
        self.assertEqual(get.call_count, 2)

    def test_lasting_remote_error_alerts_with_its_reason(self):
        bad = {"detail": "Can't reach the vault remote: Permission denied"}
        result, get, _ = self.run_check(_response(502, bad), _response(502, bad))
        self.assertFalse(result["ok"])
        self.assertIn("Permission denied", result["text"])
        self.assertEqual(get.call_count, 2)


if __name__ == "__main__":
    unittest.main()
