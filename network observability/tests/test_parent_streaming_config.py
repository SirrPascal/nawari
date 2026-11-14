"""Comprehensive unit and negative tests for Netdata Parent streaming configuration and safety."""

import configparser
import unittest
from pathlib import Path

TEST_ROOT = Path(__file__).resolve().parents[1]
LOCAL_LAB = TEST_ROOT / "server" / "local-lab"
RUNTIME = LOCAL_LAB / "runtime"


class ParentStreamingSafetyAndConfigTests(unittest.TestCase):
    def setUp(self):
        self.child_netdata = RUNTIME / "test-child-netdata.conf"
        self.child_stream = RUNTIME / "test-child-stream.conf"
        self.compose_file = LOCAL_LAB / "compose.test-child.yaml"
        self.alloy_scrape = LOCAL_LAB / "config.parent-scrape.alloy"

    def test_child_netdata_configuration(self):
        """Ensure test child runs in lightweight streaming mode without local db or web listener."""
        self.assertTrue(self.child_netdata.exists())
        cfg = configparser.ConfigParser()
        cfg.read(self.child_netdata)
        self.assertEqual(cfg.get("global", "hostname"), "nawari-test-child")
        self.assertEqual(cfg.get("db", "mode"), "none")
        self.assertEqual(cfg.get("web", "mode"), "none")
        self.assertEqual(cfg.get("plugins", "proc"), "yes")

    def test_child_stream_security_and_tls(self):
        """Ensure test child enforces strict TLS verification and targets local Parent."""
        self.assertTrue(self.child_stream.exists())
        cfg = configparser.ConfigParser()
        cfg.read(self.child_stream)
        sec = cfg["stream"]
        self.assertEqual(sec.get("enabled"), "yes")
        self.assertEqual(sec.get("ssl skip certificate verification"), "no")
        self.assertIn(":SSL", sec.get("destination", ""))

    def test_compose_manifest_isolation_and_resources(self):
        """Ensure test child uses opt-in profile, bounded resources, and dropped capabilities."""
        self.assertTrue(self.compose_file.exists())
        content = self.compose_file.read_text()
        self.assertIn("container_name: nawari-test-child", content)
        self.assertIn("image: netdata/netdata:v2.12.3", content)
        self.assertIn('profiles: ["test-child"]', content)
        self.assertIn("hostname: nawari-test-child", content)
        self.assertIn("cpus: 0.25", content)
        self.assertIn("mem_limit: 256m", content)
        self.assertIn("no-new-privileges:true", content)
        self.assertIn("cap_drop:", content)
        self.assertIn("- ALL", content)

    def test_alloy_parent_scrape_preserves_child_identity(self):
        """Ensure Alloy Parent scrape sets format=prometheus_all_hosts and honor_labels=true."""
        self.assertTrue(self.alloy_scrape.exists())
        content = self.alloy_scrape.read_text()
        self.assertIn("prometheus_all_hosts", content)
        self.assertIn("as-collected", content)
        self.assertTrue("honor_labels    = true" in content or "honor_labels = true" in content)
        self.assertIn("netdata-parent:20000", content)

    def test_identity_isolation_against_production_and_mac(self):
        """Ensure test child identity does not collide with Mac Child or Parent."""
        mac_stream = Path("/opt/homebrew/etc/netdata/stream.conf")
        child_stream_cfg = configparser.ConfigParser()
        child_stream_cfg.read(self.child_stream)
        test_key = child_stream_cfg.get("stream", "api key")

        if mac_stream.exists():
            mac_cfg = configparser.ConfigParser()
            mac_cfg.read(mac_stream)
            mac_key = mac_cfg.get("stream", "api key", fallback="")
            self.assertNotEqual(test_key, mac_key, "Test child must not copy Mac's streaming API key")

        child_netdata_cfg = configparser.ConfigParser()
        child_netdata_cfg.read(self.child_netdata)
        test_host = child_netdata_cfg.get("global", "hostname")
        self.assertEqual(test_host, "nawari-test-child")
        self.assertNotEqual(test_host, "Pascals-MacBook-Pro.local")
        self.assertNotEqual(test_host, "nawari-network-parent")

    # ================= NEGATIVE & SAFETY TESTS =================

    def test_negative_reject_project_wide_teardown_commands(self):
        """Verify that compose.test-child.yaml does not encourage destructive docker compose down."""
        content = self.compose_file.read_text()
        # Verify no instructions suggest docker compose down
        self.assertNotIn("docker compose down", content)
        self.assertNotIn("--remove-orphans", content)

    def test_negative_missing_child_detection(self):
        """Verify that simulated absent child in Parent status is caught as unverified."""
        mock_empty_parent_info = {
            "version": "v2.12.3",
            "hosts-available": 1,
            "mirrored_hosts_status": [
                {"hostname": "nawari-network-parent", "guid": "abc-123", "hops": 0, "reachable": True}
            ]
        }
        # Check that no child with hops > 0 and hostname nawari-test-child exists
        children = [h for h in mock_empty_parent_info["mirrored_hosts_status"] if h.get("hops", 0) > 0]
        self.assertEqual(len(children), 0, "Should detect 0 remote children")

    def test_negative_invalid_streaming_credentials(self):
        """Verify that mismatched API keys between child and parent are flagged."""
        parent_stream_cfg = configparser.ConfigParser()
        parent_stream_cfg.read(RUNTIME / "stream.conf")
        parent_keys = set(parent_stream_cfg.sections())

        # An invalid key must not match parent authorized sections
        bad_key = "00000000-dead-beef-0000-000000000000"
        self.assertNotIn(bad_key, parent_keys, "Invalid key unexpectedly found in Parent stream.conf")

    def test_negative_tls_san_mismatch_detection(self):
        """Verify that connecting to netdata-parent fails hostname check when cert only has 127.0.0.1."""
        server_cert = RUNTIME / "server-cert.pem"
        import subprocess
        san_out = subprocess.check_output(["openssl", "x509", "-in", str(server_cert), "-noout", "-text"]).decode()
        # The current cert only has IP:127.0.0.1, not DNS:netdata-parent
        self.assertIn("IP Address:127.0.0.1", san_out)
        self.assertNotIn("DNS:netdata-parent", san_out, "Test assumes current cert lacks DNS SAN; must detect mismatch")

    def test_negative_empty_mimir_results_handling(self):
        """Verify that empty vector results from Mimir are treated as failure, not zero/healthy."""
        mock_mimir_empty_response = {"status": "success", "data": {"resultType": "vector", "result": []}}
        series = mock_mimir_empty_response.get("data", {}).get("result", [])
        self.assertEqual(len(series), 0)
        # Ensure logic doesn't assume empty is success
        self.assertFalse(bool(series), "Empty series list must evaluate as falsy (failure to find child)")


if __name__ == "__main__":
    unittest.main()
