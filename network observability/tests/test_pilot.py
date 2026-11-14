"""Coverage and service-response regressions for the standalone pilot."""

import importlib.util
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audit = load_script("audit_agent")
fixture = load_script("fixture_service")


class PilotTests(unittest.TestCase):
    def test_missing_and_stale_coverage_remain_distinct(self):
        policy = {
            "freshness_seconds": 120,
            "checks": [{"id": "http", "context_prefix": "httpcheck.", "scope": "targets"}],
        }
        missing = audit.summarize({}, policy, 1000)[0]
        stale = audit.summarize(
            {"a": {"context": "httpcheck.status", "last_entry": 800}}, policy, 1000
        )[0]
        self.assertEqual(missing["status"], "not_observed")
        self.assertEqual(stale["status"], "observed_stale")

    def test_one_fresh_chart_does_not_hide_an_old_target(self):
        policy = {
            "freshness_seconds": 120,
            "checks": [{"id": "http", "context_prefix": "httpcheck.", "scope": "targets"}],
        }
        charts = {
            "a": {"context": "httpcheck.status", "last_entry": 995},
            "b": {"context": "httpcheck.status", "last_entry": 700},
            "c": {"context": "httpcheck.status", "last_entry": 2000},
        }
        result = audit.summarize(charts, policy, 1000)[0]
        self.assertEqual(result["status"], "partially_fresh")
        self.assertEqual(result["fresh_charts"], 1)
        self.assertEqual(result["invalid_timestamps"], 1)

    def test_service_fixture_exposes_expected_failure(self):
        with ThreadingHTTPServer(("127.0.0.1", 0), fixture.Handler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                with urllib.request.urlopen(base + "/healthy", timeout=3) as response:
                    self.assertEqual(response.status, 200)
                started = time.monotonic()
                with urllib.request.urlopen(base + "/slow", timeout=3) as response:
                    self.assertEqual(response.status, 200)
                self.assertGreaterEqual(time.monotonic() - started, 0.8)
                with self.assertRaises(urllib.error.HTTPError) as failed:
                    urllib.request.urlopen(base + "/unavailable", timeout=3)
                self.assertEqual(failed.exception.code, 503)
            finally:
                server.shutdown()
                thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
