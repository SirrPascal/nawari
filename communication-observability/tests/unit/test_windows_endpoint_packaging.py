"""Static and cross-platform tests for the Windows MSI deployment source."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from services.endpoint.cli import build_parser, main
from services.endpoint.config import AgentConfig


ROOT = Path(__file__).resolve().parents[2]
WINDOWS = ROOT / "packaging" / "windows"


def test_consolidated_cli_contract(capsys):
    parser = build_parser()
    for command in ("run", "test", "health", "status", "version"):
        parsed = parser.parse_args([command] + (["--all"] if command == "test" else []))
        assert parsed.command == command

    assert main(["version"]) == 0
    assert "Nawari Endpoint Agent" in capsys.readouterr().out


def test_windows_service_command_is_safely_rejected_off_windows():
    assert main(["service"]) == 2


def test_state_directory_environment_override(monkeypatch, tmp_path):
    monkeypatch.setenv("NAWARI_STATE_DIR", str(tmp_path / "state"))
    config = AgentConfig.load_from_env()
    assert config.state_dir == str(tmp_path / "state")


def test_wix_installs_agent_as_managed_service():
    root = ET.parse(WINDOWS / "Product.wxs").getroot()
    ns = {"w": "http://wixtoolset.org/schemas/v4/wxs"}
    service = root.find(".//w:ServiceInstall", ns)
    assert service is not None
    assert service.attrib["Name"] == "NawariEndpointAgent"
    assert service.attrib["Arguments"] == "service"
    assert service.attrib["Start"] == "demand"
    assert root.find(".//w:MajorUpgrade", ns) is not None


def test_release_build_requires_signing_and_x64():
    source = (WINDOWS / "Build-Msi.ps1").read_text(encoding="utf-8")
    assert "NAWARI_SIGNING_THUMBPRINT" in source
    assert "signtool.exe verify /pa /all" in source
    assert "-arch x64" in source
    assert "NawariEndpointAgent-x64.msi" in source


def test_intune_install_enforces_hash_signature_https_and_dpapi():
    source = (WINDOWS / "Install-Intune.ps1").read_text(encoding="utf-8")
    assert "Get-FileHash" in source
    assert "Get-AuthenticodeSignature" in source
    assert 'StartsWith("https://"' in source
    assert "credential-store" in source
    assert "icacls.exe" in source
    assert "NAWARI_ENVIRONMENT=PHYSICAL_PRODUCTION" in source


def test_ordinary_uninstall_preserves_identity_by_default():
    source = (WINDOWS / "Uninstall-Intune.ps1").read_text(encoding="utf-8")
    assert "PurgeIdentityAndTelemetry" in source
    assert "Win32_Product" not in source
    assert "NetdataInstalledByPackage" in source
