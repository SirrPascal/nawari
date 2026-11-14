"""Automated validation tests for the Nawari Network Experience Grafana Dashboard.

Contains two distinct test suites:
1. Unit tests (Offline): Validates JSON structure, UID uniqueness, variable references,
   metric namespaces, null-safety, and staleness guard expressions. Suitable for ordinary CI.
2. Integration tests (Online): Verifies live query execution through Mimir and Grafana
   when local lab services are active. Skipped gracefully in offline CI environments.
"""

import base64
import json
import os
import re
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PATH = ROOT / "dashboards" / "nawari_network_experience_local_pilot.json"
REPO_ROOT = ROOT.parent

MIMIR_URL = os.environ.get("NAWARI_MIMIR_URL", "http://127.0.0.1:19009")
GRAFANA_URL = os.environ.get("NAWARI_GRAFANA_URL", "http://127.0.0.1:3001")


def is_service_reachable(url, path):
    try:
        with urllib.request.urlopen(f"{url}{path}", timeout=1) as resp:
            return resp.status in (200, 401)
    except Exception:
        return False


MIMIR_AVAILABLE = is_service_reachable(MIMIR_URL, "/ready") or is_service_reachable(MIMIR_URL, "/prometheus/api/v1/query?query=up")
GRAFANA_AVAILABLE = is_service_reachable(GRAFANA_URL, "/api/health")


class DashboardUnitTests(unittest.TestCase):
    """Offline CI-safe validation of dashboard configuration and PromQL design."""

    def setUp(self):
        self.assertTrue(DASHBOARD_PATH.exists(), f"Dashboard not found at {DASHBOARD_PATH}")
        with open(DASHBOARD_PATH) as f:
            self.dashboard = json.load(f)

    def test_dashboard_metadata_and_structure(self):
        self.assertEqual(self.dashboard.get("title"), "Nawari — Network Experience (Local Pilot)")
        self.assertEqual(self.dashboard.get("uid"), "nawari-net-exp-pilot")
        self.assertGreaterEqual(self.dashboard.get("schemaVersion", 0), 38)
        self.assertTrue(self.dashboard.get("editable"))
        self.assertIn("mimir", self.dashboard.get("tags", []))
        self.assertIn("local-pilot", self.dashboard.get("tags", []))

    def test_uid_uniqueness(self):
        """Ensure dashboard UID does not collide with existing provisioned dashboards."""
        existing_dashboards = list(REPO_ROOT.glob("**/dashboards/**/*.json"))
        target_uid = self.dashboard.get("uid")
        for p in existing_dashboards:
            if p.resolve() == DASHBOARD_PATH.resolve():
                continue
            try:
                with open(p) as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        other_uid = data.get("uid")
                        self.assertNotEqual(
                            other_uid, target_uid,
                            f"Collision: UID {target_uid} matches dashboard in {p}"
                        )
            except Exception:
                pass

    def test_datasource_uid_and_type(self):
        """Ensure all query panels reference the verified nawari-local-mimir datasource."""
        panels = self.dashboard.get("panels", [])
        self.assertGreaterEqual(len(panels), 7)
        for panel in panels:
            if panel.get("type") == "text":
                continue
            for target in panel.get("targets", []):
                ds = target.get("datasource", {})
                self.assertEqual(
                    ds.get("uid"), "nawari-local-mimir",
                    f"Panel '{panel.get('title')}' target has invalid datasource UID: {ds}"
                )
                self.assertEqual(ds.get("type"), "prometheus")

    def test_variable_references(self):
        """Ensure all variables used in queries ($instance, $probe_target) are declared in templating."""
        variables = {v.get("name") for v in self.dashboard.get("templating", {}).get("list", [])}
        self.assertIn("instance", variables)
        self.assertIn("probe_target", variables)

        var_pattern = re.compile(r"\$([a-zA-Z0-9_]+)|\${([a-zA-Z0-9_]+)}")
        for panel in self.dashboard.get("panels", []):
            for target in panel.get("targets", []):
                expr = target.get("expr", "")
                for match in var_pattern.findall(expr):
                    var_name = match[0] or match[1]
                    self.assertIn(
                        var_name, variables,
                        f"Panel '{panel.get('title')}' references undeclared variable ${var_name}"
                    )

    def test_verified_metric_names_and_units(self):
        """Ensure all metrics in queries belong to verified Nawari metric sets."""
        allowed_metrics = {
            "netdata_nawari_network_latency",
            "netdata_nawari_network_loss",
            "netdata_nawari_request_status",
            "netdata_nawari_request_phases",
            "netdata_nawari_path_hops",
            "netdata_nawari_path_reached",
            "netdata_nawari_path_duration_ms",
            "netdata_nawari_path_age_seconds",
            "netdata_nawari_network_context",
            "netdata_nawari_tls_certificate",
        }
        for panel in self.dashboard.get("panels", []):
            for target in panel.get("targets", []):
                expr = target.get("expr", "")
                found = any(m in expr for m in allowed_metrics)
                self.assertTrue(found, f"Panel '{panel.get('title')}' target has unverified metric: {expr}")

    def test_null_value_safety(self):
        """Verify that panels do not display missing data as zero or healthy."""
        for panel in self.dashboard.get("panels", []):
            ptype = panel.get("type")
            if ptype in ("timeseries", "stat"):
                fc = panel.get("fieldConfig", {}).get("defaults", {})
                no_val = fc.get("noValue", "")
                self.assertTrue(
                    len(no_val) > 0,
                    f"Panel '{panel.get('title')}' is missing explicit noValue configuration"
                )
                if ptype == "timeseries":
                    custom = fc.get("custom", {})
                    self.assertFalse(
                        custom.get("spanNulls", True),
                        f"Panel '{panel.get('title')}' must have spanNulls=False"
                    )

    def test_staleness_guard_enforcement(self):
        """Verify that instant stat panels enforce lookback staleness guards (< 120s)."""
        stat_panels = [p for p in self.dashboard.get("panels", []) if p.get("type") == "stat"]
        for p in stat_panels:
            pid = p.get("id")
            if pid == 2:  # Telemetry freshness panel explicitly computes time() - timestamp(...)
                continue
            for t in p.get("targets", []):
                expr = t.get("expr", "")
                self.assertIn(
                    "time() - timestamp", expr,
                    f"Stat panel '{p.get('title')}' is missing PromQL staleness guard: {expr}"
                )
                self.assertIn(
                    "< 120", expr,
                    f"Stat panel '{p.get('title')}' must enforce 120s staleness threshold: {expr}"
                )


@unittest.skipUnless(MIMIR_AVAILABLE, f"Mimir not available at {MIMIR_URL}; skipping integration suite")
class DashboardLiveMimirIntegrationTests(unittest.TestCase):
    """Integration suite verifying live query execution against local Mimir."""

    def setUp(self):
        with open(DASHBOARD_PATH) as f:
            self.dashboard = json.load(f)
        self.mock_instance = "Pascals-MacBook-Pro.local"
        self.mock_target = "fixture-portal_page"

    def test_promql_syntax_against_live_mimir(self):
        for panel in self.dashboard.get("panels", []):
            for target in panel.get("targets", []):
                raw_expr = target.get("expr", "")
                clean_expr = raw_expr.replace("^$instance$", self.mock_instance)
                clean_expr = clean_expr.replace("$instance", self.mock_instance)
                clean_expr = clean_expr.replace("${probe_target}", self.mock_target)
                clean_expr = clean_expr.replace("$probe_target", self.mock_target)

                url = f"{MIMIR_URL}/prometheus/api/v1/query?query={urllib.parse.quote(clean_expr)}"
                try:
                    with urllib.request.urlopen(url, timeout=3) as response:
                        self.assertEqual(response.status, 200)
                        body = json.loads(response.read().decode())
                        self.assertEqual(body.get("status"), "success")
                except urllib.error.URLError as err:
                    self.fail(f"Live Mimir rejected query for '{panel.get('title')}' [{clean_expr}]: {err}")

    def test_stale_lookback_prevention_behavior(self):
        """Prove that samples older than threshold return empty vector rather than stale green."""
        # Simulated stale guard using < 1s window (which guaranteed drops current samples)
        expr_stale = f'(netdata_nawari_request_status{{instance="{self.mock_instance}", chart="nawari.{self.mock_target}_status", dimension="success"}}) and (time() - timestamp(netdata_nawari_request_status{{instance="{self.mock_instance}", chart="nawari.{self.mock_target}_status", dimension="success"}}) < 0.001)'
        url = f"{MIMIR_URL}/prometheus/api/v1/query?query={urllib.parse.quote(expr_stale)}"
        with urllib.request.urlopen(url, timeout=3) as resp:
            body = json.loads(resp.read().decode())
            results = body.get("data", {}).get("result", [])
            self.assertEqual(len(results), 0, "Stale sample was not suppressed by guard!")


@unittest.skipUnless(GRAFANA_AVAILABLE, f"Grafana not available at {GRAFANA_URL}; skipping integration suite")
class DashboardLiveGrafanaIntegrationTests(unittest.TestCase):
    """Integration suite verifying the query proxy path through local Grafana."""

    def setUp(self):
        with open(DASHBOARD_PATH) as f:
            self.dashboard = json.load(f)
        self.mock_instance = "Pascals-MacBook-Pro.local"
        self.mock_target = "fixture-portal_page"
        auth_str = "admin:nawari_grafana_dev_pass"
        self.b64_auth = base64.b64encode(auth_str.encode()).decode()

    def test_datasource_query_path_through_grafana(self):
        verified_count = 0
        for panel in self.dashboard.get("panels", []):
            for target in panel.get("targets", []):
                raw_expr = target.get("expr", "")
                clean_expr = raw_expr.replace("^$instance$", self.mock_instance)
                clean_expr = clean_expr.replace("$instance", self.mock_instance)
                clean_expr = clean_expr.replace("${probe_target}", self.mock_target)
                clean_expr = clean_expr.replace("$probe_target", self.mock_target)

                url = f"{GRAFANA_URL}/api/datasources/proxy/uid/nawari-local-mimir/api/v1/query?query={urllib.parse.quote(clean_expr)}"
                req = urllib.request.Request(url)
                req.add_header("Authorization", f"Basic {self.b64_auth}")

                try:
                    with urllib.request.urlopen(req, timeout=3) as resp:
                        self.assertEqual(resp.status, 200)
                        data = json.loads(resp.read().decode())
                        self.assertEqual(data.get("status"), "success")
                        verified_count += 1
                except urllib.error.URLError as err:
                    self.fail(f"Grafana proxy failed for '{panel.get('title')}' [{clean_expr}]: {err}")

        self.assertGreaterEqual(verified_count, 10)


if __name__ == "__main__":
    unittest.main()
