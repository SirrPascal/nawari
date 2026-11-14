import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
PACKAGING = ROOT / "packaging" / "macos"


class MacOSPackagingTests(unittest.TestCase):
    def test_packaging_scripts_are_valid_posix_shell(self):
        for script in PACKAGING.glob("*.sh"):
            result = subprocess.run(["sh", "-n", str(script)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, f"{script}: {result.stderr}")

    def test_build_declares_required_release_controls(self):
        build = (PACKAGING / "build.sh").read_text()
        for token in ("pkgbuild", "APPLICATION_IDENTITY", "INSTALLER_IDENTITY", "notarytool", "REQUIRE_SIGNING"):
            self.assertIn(token, build)
        install = (PACKAGING / "install.sh").read_text()
        self.assertIn('target_volume="${1:-/}"', install)
        self.assertIn('payload_dir="${target_volume%/}/usr/local/libexec/nawari"', install)
        self.assertIn('--prefix netdata', install)
        self.assertIn('/opt/homebrew/opt/netdata', install)

    def test_verification_requires_native_and_numeric_telemetry(self):
        verify = (PACKAGING / "verify.sh").read_text()
        self.assertIn('"system.cpu', verify)
        self.assertIn('"system.ram', verify)
        self.assertIn("numeric recent samples", verify)


if __name__ == "__main__":
    unittest.main()
