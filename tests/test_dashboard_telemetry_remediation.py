#!/usr/bin/env python3
"""
Test-Driven Development (TDD) Verification Suite for Nawari Grafana Phase A Remediation.
Tests the seams of dashboard queries, host targeting, Loki performance, and unit configuration.
"""

import unittest
import json
import os
import urllib.request
import ssl
import base64
import time

GF_URL = "https://10.2.1.58:18443/grafana/api"
AUTH = "admin:admin"
ctx = ssl._create_unverified_context()

def gf_post(path, data):
    req = urllib.request.Request(f"{GF_URL}{path}", method="POST")
    b64 = base64.b64encode(AUTH.encode()).decode()
    req.add_header("Authorization", f"Basic {b64}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, data=json.dumps(data).encode(), context=ctx, timeout=20) as resp:
        return resp.status, json.loads(resp.read().decode())

def gf_get(path):
    req = urllib.request.Request(f"{GF_URL}{path}")
    b64 = base64.b64encode(AUTH.encode()).decode()
    req.add_header("Authorization", f"Basic {b64}")
    with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
        return resp.status, json.loads(resp.read().decode())

class TestDashboardRemediation(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        cls.now_ms = int(time.time() * 1000)
        cls.from_ms_1h = cls.now_ms - 3600 * 1000
        cls.from_ms_24h = cls.now_ms - 24 * 3600 * 1000

    def test_seam_1_avaya_cm_reachability_query_returns_frames(self):
        """CM reachability panel must query exact visible name and return live frames."""
        payload = {
            "from": str(self.from_ms_1h),
            "to": str(self.now_ms),
            "queries": [
                {
                    "refId": "A",
                    "datasource": {"uid": "PA67C5EADE9207728", "type": "alexanderzobnin-zabbix-datasource"},
                    "group": {"filter": "/.*/"},
                    "host": {"filter": "Avaya Communication Manager Duplex (HQ-CORE)"},
                    "item": {"filter": "ICMP ping"},
                    "mode": 0
                }
            ]
        }
        st, res = gf_post("/ds/query", payload)
        self.assertEqual(st, 200)
        frames = res.get("results", {}).get("A", {}).get("frames", [])
        self.assertGreater(len(frames), 0, "Avaya CM reachability must return at least 1 frame")
        values = frames[0].get("data", {}).get("values", [])
        self.assertTrue(len(values) > 1 and len(values[1]) > 0, "Must contain data points")
        self.assertIn(values[1][-1], [0, 1], "Latest value must be 0 or 1")

    def test_seam_2_avaya_sbce_reachability_query_returns_frames(self):
        """SBCE reachability panel must query exact visible name and return live frames."""
        payload = {
            "from": str(self.from_ms_1h),
            "to": str(self.now_ms),
            "queries": [
                {
                    "refId": "A",
                    "datasource": {"uid": "PA67C5EADE9207728", "type": "alexanderzobnin-zabbix-datasource"},
                    "group": {"filter": "/.*/"},
                    "host": {"filter": "Avaya SBCE Primary (HQ-DMZ)"},
                    "item": {"filter": "ICMP ping"},
                    "mode": 0
                }
            ]
        }
        st, res = gf_post("/ds/query", payload)
        self.assertEqual(st, 200)
        frames = res.get("results", {}).get("A", {}).get("frames", [])
        self.assertGreater(len(frames), 0, "Avaya SBCE reachability must return at least 1 frame")

    def test_seam_3_avaya_sm_reachability_query_returns_frames(self):
        """SM reachability panel must query exact visible name and return live frames."""
        payload = {
            "from": str(self.from_ms_1h),
            "to": str(self.now_ms),
            "queries": [
                {
                    "refId": "A",
                    "datasource": {"uid": "PA67C5EADE9207728", "type": "alexanderzobnin-zabbix-datasource"},
                    "group": {"filter": "/.*/"},
                    "host": {"filter": "Avaya Session Manager Primary (HQ-CORE)"},
                    "item": {"filter": "ICMP ping"},
                    "mode": 0
                }
            ]
        }
        st, res = gf_post("/ds/query", payload)
        self.assertEqual(st, 200)
        frames = res.get("results", {}).get("A", {}).get("frames", [])
        self.assertGreater(len(frames), 0, "Avaya SM reachability must return at least 1 frame")

    def test_seam_4_avaya_g450_reachability_query_returns_frames(self):
        """G450 gateway reachability panel must query exact visible name and return live frames."""
        payload = {
            "from": str(self.from_ms_1h),
            "to": str(self.now_ms),
            "queries": [
                {
                    "refId": "A",
                    "datasource": {"uid": "PA67C5EADE9207728", "type": "alexanderzobnin-zabbix-datasource"},
                    "group": {"filter": "/.*/"},
                    "host": {"filter": "Avaya G450 Media Gateway (HQ-GATEWAY)"},
                    "item": {"filter": "ICMP ping"},
                    "mode": 0
                }
            ]
        }
        st, res = gf_post("/ds/query", payload)
        self.assertEqual(st, 200)
        frames = res.get("results", {}).get("A", {}).get("frames", [])
        self.assertGreater(len(frames), 0, "Avaya G450 reachability must return at least 1 frame")

    def test_seam_5_loki_solarwinds_instant_query_responds_under_15s(self):
        """Loki LogQL severity instant query over 24h must return without 504 timeout."""
        now_s = int(time.time())
        expr = 'sum by (cisco_severity) (count_over_time({source="solarwinds", environment="production"}[24h]))'
        import urllib.parse
        params = {
            "query": expr,
            "time": str(now_s * 1000000000)
        }
        qs = urllib.parse.urlencode(params)
        t0 = time.time()
        st, res = gf_get(f"/datasources/proxy/uid/P8E80F9AEF21F6940/loki/api/v1/query?{qs}")
        elapsed = time.time() - t0
        self.assertEqual(st, 200, f"Loki instant query must return 200 OK (got {st})")
        self.assertLess(elapsed, 15.0, f"Query took {elapsed:.2f}s, expected < 15.0s (nginx timeout)")
        data = res.get("data", {}).get("result", [])
        self.assertGreater(len(data), 0, "Must return severity distribution series")

    def test_seam_6_net_avail_unit_is_percent(self):
        """Packet loss panel in nawari-net-avail must be configured with 'percent' unit."""
        st, dash_data = gf_get("/dashboards/uid/nawari-net-avail")
        dash = dash_data.get("dashboard", {})
        loss_panel = None
        for p in dash.get("panels", []):
            if p.get("id") == 2:
                loss_panel = p
                break
        self.assertIsNotNone(loss_panel)
        unit = loss_panel.get("fieldConfig", {}).get("defaults", {}).get("unit")
        self.assertEqual(unit, "percent", f"Unit must be 'percent', got '{unit}'")

if __name__ == "__main__":
    unittest.main()
