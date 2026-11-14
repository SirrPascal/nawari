"""Regressions for deployment credentials, TLS identity and archive contents."""

import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from deploy_server import validate_destination  # noqa: E402
from package_server import FILES, build_archive  # noqa: E402
from prepare_server import prepare, validate_address  # noqa: E402


class ServerTests(unittest.TestCase):
    def test_platform_candidate_keeps_state_private_and_retention_bounded(self):
        compose = (ROOT / "server/platform/compose.yaml").read_text()
        loki = (ROOT / "server/platform/loki.yaml").read_text()

        self.assertIn("127.0.0.1:${NAWARI_API_PORT:-18090}:18090", compose)
        self.assertIn("internal: true", compose)
        self.assertNotIn("5432:5432", compose)
        self.assertNotIn("9092:9092", compose)
        self.assertNotIn("down -v", compose)
        self.assertIn("profiles: [logs]", compose)
        self.assertIn("profiles: [metrics]", compose)
        self.assertIn("profiles: [shadow]", compose)
        worker = compose.split("\n  worker:\n", 1)[1].split("\n  kafka:\n", 1)[0]
        self.assertNotIn("loki:", worker)
        self.assertIn("retention_period: 144h", loki)
        self.assertIn("retention_enabled: true", loki)
        self.assertIn("retention_delete_delay: 2h", loki)

    def test_destination_rejects_remote_shell_injection(self):
        for target, directory in (
            ("-oProxyCommand=anything", "pilot"),
            ("admin.comms@10.2.1.58", "pilot;exit"),
            ("admin.comms@10.2.1.58", "/opt/../etc"),
        ):
            with self.assertRaises(ValueError):
                validate_destination(target, directory)
        validate_destination("admin.comms@10.2.1.58", "nawari-network-pilot")

    def test_server_address_has_ip_identity(self):
        self.assertEqual(validate_address("10.2.1.58"), ("10.2.1.58", "IP:10.2.1.58"))
        for value in ("10.2.1.58\nkey=bad", "host;bad", "../host"):
            with self.assertRaises(ValueError):
                validate_address(value)

    def test_archive_uses_only_explicit_deployment_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = build_archive(Path(directory) / "pilot.tar.gz")
            with tarfile.open(archive) as package:
                self.assertEqual(set(package.getnames()), set(FILES))
                self.assertTrue(all(member.isfile() for member in package.getmembers()))

    @unittest.skipUnless(shutil.which("openssl"), "OpenSSL is required")
    def test_tls_is_valid_for_server_ip_and_enrollment_survives_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "runtime"
            self.assertTrue(prepare(runtime, "10.2.1.58", "10.2.1.58", "*"))
            original = {p.name: p.read_bytes() for p in runtime.iterdir()}
            self.assertFalse(prepare(runtime, "10.2.1.58", "10.2.1.58", "*"))
            self.assertEqual(original, {p.name: p.read_bytes() for p in runtime.iterdir()})
            verified = subprocess.run(
                [
                    "openssl",
                    "verify",
                    "-CAfile",
                    str(runtime / "ca-cert.pem"),
                    "-verify_ip",
                    "10.2.1.58",
                    "-purpose",
                    "sslserver",
                    str(runtime / "server-cert.pem"),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(verified.returncode, 0, verified.stderr)
            for path in runtime.iterdir():
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(ValueError):
                prepare(runtime, "10.2.1.59", "10.2.1.58", "*")
            self.assertEqual(original["stream.conf"], (runtime / "stream.conf").read_bytes())


if __name__ == "__main__":
    unittest.main()
