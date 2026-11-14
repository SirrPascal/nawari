#!/usr/bin/env python3
"""
test_stream_test_lab.py

Automated offline test suite for the isolated Nawari Netdata streaming test lab
(Project: nawari-stream-test).

Verifies Compose isolation, network subnets, container boundaries, security hardening,
TLS certificates and SANs, stream authentication alignment, and Alloy multi-host scraping.
"""

import os
import re
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STREAM_TEST_DIR = REPO_ROOT / "network observability" / "server" / "local-lab" / "stream-test"
COMPOSE_FILE = STREAM_TEST_DIR / "compose.yaml"
ALLOY_CONFIG = STREAM_TEST_DIR / "config.alloy"
RUNTIME_DIR = STREAM_TEST_DIR / "runtime"
TEMPLATES_DIR = STREAM_TEST_DIR / "templates"
VALIDATOR = STREAM_TEST_DIR / "validate_stream_lab.py"


class TestStreamTestLab(unittest.TestCase):
    def test_compose_project_and_naming(self):
        """Verifies distinct project name, container names, and volume names."""
        self.assertTrue(COMPOSE_FILE.exists(), "compose.yaml must exist")
        content = COMPOSE_FILE.read_text()

        self.assertIn("name: nawari-stream-test", content)
        self.assertIn("container_name: nawari-stream-test-parent", content)
        self.assertIn("container_name: nawari-stream-test-child", content)
        self.assertIn("container_name: nawari-alloy-stream-test", content)

        # Ensure volume names are uniquely prefixed to prevent collisions
        self.assertIn("stream-test-parent-identity:", content)
        self.assertIn("stream-test-parent-metrics:", content)
        self.assertIn("stream-test-child-identity:", content)
        self.assertIn("stream-test-child-cache:", content)
        self.assertIn("stream-test-alloy-data:", content)

    def test_network_isolation(self):
        """Verifies dedicated bridge subnet and collision-free port mapping."""
        content = COMPOSE_FILE.read_text()

        self.assertIn("nawari-stream-test-net", content)
        self.assertIn("172.28.0.0/16", content)
        self.assertIn("gateway: 172.28.0.1", content)
        self.assertIn("ipv4_address: 172.28.0.10", content)
        self.assertIn("ipv4_address: 172.28.0.20", content)

        # Port mapping must bind to loopback port 19988
        self.assertIn('"127.0.0.1:19988:20000"', content)
        # Ensure no collision with default netdata (19999) or local-lab parent (19998/20000) on host
        self.assertNotIn('"19999:19999"', content)
        self.assertNotIn('"19998:20000"', content)

    def test_security_hardening(self):
        """Verifies container security constraints, dropped privileges, and read-only mounts."""
        content = COMPOSE_FILE.read_text()

        self.assertIn("no-new-privileges:true", content)
        self.assertIn("cap_drop:\n      - ALL", content)
        self.assertIn("cap_add:\n      - SYS_PTRACE\n      - DAC_READ_SEARCH", content)
        self.assertNotIn("/var/run/docker.sock", content)

        # Verify configs are mounted read-only (:ro)
        self.assertIn("./runtime/child-stream.conf:/etc/netdata/stream.conf:ro", content)
        self.assertIn("./runtime/ca-cert.pem:/etc/netdata/ssl/ca-cert.pem:ro", content)
        self.assertIn("./runtime/parent-stream.conf:/run/pilot/stream.conf:ro", content)

    def test_tls_san_and_certificate_chain(self):
        """Validates the test CA, server certificate, SAN entries, and certificate verification."""
        ca_cert = RUNTIME_DIR / "ca-cert.pem"
        server_cert = RUNTIME_DIR / "server-cert.pem"
        self.assertTrue(ca_cert.exists(), "ca-cert.pem must exist")
        self.assertTrue(server_cert.exists(), "server-cert.pem must exist")

        # 1. Verify chain with openssl verify
        res = subprocess.run(
            ["openssl", "verify", "-CAfile", str(ca_cert), str(server_cert)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(res.returncode, 0, f"openssl verify failed: {res.stderr}")
        self.assertIn("OK", res.stdout)

        # 2. Inspect SAN entries in server-cert.pem
        x509_res = subprocess.run(
            ["openssl", "x509", "-in", str(server_cert), "-text", "-noout"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(x509_res.returncode, 0)
        cert_text = x509_res.stdout
        self.assertIn("DNS:netdata-stream-test-parent", cert_text)
        self.assertIn("DNS:nawari-stream-test-parent", cert_text)
        self.assertIn("DNS:localhost", cert_text)
        self.assertIn("IP Address:127.0.0.1", cert_text)

        # 3. Check CA constraint
        ca_x509 = subprocess.run(
            ["openssl", "x509", "-in", str(ca_cert), "-text", "-noout"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertIn("CA:TRUE", ca_x509.stdout)

    def test_stream_conf_alignment_and_key(self):
        """Confirms child and parent stream configs match API key, use SSL, and authorize bridge subnet."""
        child_conf = RUNTIME_DIR / "child-stream.conf"
        parent_conf = RUNTIME_DIR / "parent-stream.conf"
        key_env = RUNTIME_DIR / ".stream-key.env"

        self.assertTrue(child_conf.exists())
        self.assertTrue(parent_conf.exists())
        self.assertTrue(key_env.exists())

        child_text = child_conf.read_text()
        parent_text = parent_conf.read_text()
        key_env_text = key_env.read_text()

        # Extract UUID
        m = re.search(r"STREAMING_API_KEY=([a-f0-9\-]+)", key_env_text)
        self.assertIsNotNone(m, ".stream-key.env must contain valid UUID")
        api_key = m.group(1).strip()
        self.assertEqual(len(api_key), 36)

        # Child assertions
        self.assertIn(f"api key = {api_key}", child_text)
        self.assertIn("destination = netdata-stream-test-parent:19999:SSL", child_text)
        self.assertIn("ssl skip certificate verification = no", child_text)
        self.assertIn("CAfile = /etc/netdata/ssl/ca-cert.pem", child_text)

        # Parent assertions
        self.assertIn(f"[{api_key}]", parent_text)
        self.assertIn("allow from = 127.0.0.1 172.28.*", parent_text)
        self.assertIn("db = dbengine", parent_text)

    def test_alloy_multi_host_scrape_and_remote_write(self):
        """Verifies Alloy configuration collects multi-host metrics and honors host labels."""
        self.assertTrue(ALLOY_CONFIG.exists())
        alloy_text = ALLOY_CONFIG.read_text()

        self.assertIn('"__address__"      = "netdata-stream-test-parent:20000"', alloy_text)
        self.assertIn('"__metrics_path__" = "/api/v1/allmetrics"', alloy_text)
        self.assertIn('"__param_format"   = "prometheus_all_hosts"', alloy_text)
        self.assertIn('"__param_source"   = "as-collected"', alloy_text)
        self.assertIn("honor_labels    = true", alloy_text)
        self.assertIn('"http://host.docker.internal:19009/api/v1/push"', alloy_text)

    def test_static_validator_cli_execution(self):
        """Runs the standalone validator in static mode and checks for 0 exit code."""
        self.assertTrue(VALIDATOR.exists())
        res = subprocess.run(
            ["python3", str(VALIDATOR), "--check-static"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(res.returncode, 0, f"Validator failed: {res.stdout}\n{res.stderr}")
        self.assertIn("[PASS]", res.stdout)


if __name__ == "__main__":
    unittest.main()

