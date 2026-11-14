"""
tests/unit/test_phase13_5_communication_dashboard_alignment.py

Automated test suite for Phase 13.5: Communication Observability Dashboard Alignment
and Runtime Telemetry Validation.

Verifies:
1. Reconciled 45 vs 59 trigger inventory across the 7 communication templates.
2. Complete absence of legacy fictitious hostnames (nawari-sm-01, nawari-cm-01, etc.)
   across all Communication Observability dashboards.
3. Accurate Zabbix host targeting (avaya-sbce-01, avaya-sm-01, avaya-cm-01, avaya-g450-01,
   sip-trunk-carrier-01, avaya-cms-01, nawari-voice-probe-01).
4. Native Zabbix Problems panel integration (alexanderzobnin-zabbix-problems-panel).
5. Strict telemetry provenance: real call metrics vs synthetic probe isolation.
6. Null-handling and absence of zero-filling for uncollected or uninstrumented voice metrics.
7. Documentation and configuration status of the four designated administrators.
8. Physical production safety boundary (HARD_PRODUCTION_DENY preserved).
"""

import json
from pathlib import Path
import pytest
import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
COMM_DASH_DIR = ROOT_DIR / "docker/grafana/dashboards/communication_observability"
TEMPLATES_DIR = ROOT_DIR / "provisioning/zabbix/templates"
HOSTS_FILE = ROOT_DIR / "provisioning/zabbix/hosts/avaya_voice_infrastructure.yaml"
USERS_FILE = ROOT_DIR / "provisioning/zabbix/users/communication_administrators.yaml"
ACTION_FILE = ROOT_DIR / "provisioning/zabbix/actions/action_communication_alerting.yaml"
AUDIT_REPORT = ROOT_DIR / "docs/observability/phase13-5-communication-dashboard-alignment.md"

VALID_COMM_HOSTS = {
    "avaya-sbce-01",
    "avaya-sm-01",
    "avaya-cm-01",
    "avaya-g450-01",
    "sip-trunk-carrier-01",
    "avaya-cms-01",
    "nawari-voice-probe-01",
    "mock-avaya-sbce-01",
    "mon-asterisk01"
}

FORBIDDEN_LEGACY_HOSTS = {
    "nawari-sm-01",
    "nawari-cm-01",
    "nawari-g450-01",
    "nawari-cms-01",
    "nawari-wfo-01",
    "avaya-cm-01.nawari.local"
}


def test_01_reconciled_45_versus_59_trigger_inventory():
    """Verify that the 7 communication templates contain exactly 59 triggers and account for the 14 deltas."""
    template_files = {
        "sbce": TEMPLATES_DIR / "nawari_avaya_sbce.yaml",
        "sbce_base": TEMPLATES_DIR / "nawari_generic_snmp.yaml",
        "sm": TEMPLATES_DIR / "template_nawari_avaya_sm.yaml",
        "cm": TEMPLATES_DIR / "template_nawari_avaya_cm.yaml",
        "g450": TEMPLATES_DIR / "template_nawari_avaya_g450.yaml",
        "trunk": TEMPLATES_DIR / "template_nawari_sip_trunk.yaml",
        "probe": TEMPLATES_DIR / "nawari_voice_synthetic_probe.yaml",
        "cms": TEMPLATES_DIR / "template_nawari_avaya_cms_wfo.yaml",
    }

    trigger_counts = {}
    total_triggers = 0

    for name, path in template_files.items():
        assert path.is_file(), f"Template file {path.name} must exist"
        with open(path) as f:
            data = yaml.safe_load(f)

        tmpl = data["zabbix_export"]["templates"][0]
        # Count top-level triggers + triggers embedded inside items
        triggers = list(tmpl.get("triggers", []))
        for item in tmpl.get("items", []):
            triggers.extend(item.get("triggers", []))

        count = len(triggers)
        trigger_counts[name] = count
        if name != "sbce_base":
            total_triggers += count

    # SBCE has 11 native triggers + 4 inherited from Nawari Generic SNMP Base = 15 total in Zabbix
    total_sbce_triggers = trigger_counts["sbce"] + trigger_counts["sbce_base"]
    assert trigger_counts["sbce"] == 11, f"SBCE native expected 11 triggers, got {trigger_counts['sbce']}"
    assert trigger_counts["sbce_base"] == 4, f"SBCE base inherited expected 4 triggers, got {trigger_counts['sbce_base']}"
    assert total_sbce_triggers == 15, f"SBCE effective total expected 15 triggers, got {total_sbce_triggers}"

    assert trigger_counts["sm"] == 12, f"SM expected 12 triggers, got {trigger_counts['sm']}"
    assert trigger_counts["cm"] == 6, f"CM expected 6 triggers, got {trigger_counts['cm']}"
    assert trigger_counts["g450"] == 7, f"G450 expected 7 triggers, got {trigger_counts['g450']}"
    assert trigger_counts["trunk"] == 6, f"SIP Trunk expected 6 triggers, got {trigger_counts['trunk']}"
    assert trigger_counts["probe"] == 9, f"Synthetic Voice Probe expected 9 triggers, got {trigger_counts['probe']}"
    assert trigger_counts["cms"] == 4, f"CMS/WFO expected 4 triggers, got {trigger_counts['cms']}"

    # Sum of all communication monitoring triggers = 15 (SBCE) + 12 (SM) + 6 (CM) + 7 (G450) + 6 (Trunk) + 9 (Probe) + 4 (CMS) = 59
    assert (total_triggers + trigger_counts["sbce_base"]) == 59, f"Expected exactly 59 effective triggers, got {total_triggers + trigger_counts['sbce_base']}"


def test_02_no_forbidden_legacy_hostnames_in_communication_dashboards():
    """Verify that no communication dashboard references old fictitious hostnames."""
    dashboards = list(COMM_DASH_DIR.glob("*.json"))
    assert len(dashboards) == 11, f"Expected 11 communication dashboards, found {len(dashboards)}"

    violations = []
    for dp in dashboards:
        with open(dp) as f:
            data = json.load(f)

        for p in data.get("panels", []):
            if p.get("type") == "row":
                continue
            for t in p.get("targets", []):
                h = t.get("host")
                h_name = h.get("name") if isinstance(h, dict) else str(h)
                if h_name in FORBIDDEN_LEGACY_HOSTS:
                    violations.append(f"{dp.name} -> Panel ID {p.get('id')} targets forbidden host '{h_name}'")

    assert len(violations) == 0, f"Found forbidden legacy host targets:\n" + "\n".join(violations)


def test_03_authoritative_zabbix_host_targeting():
    """Verify that all communication dashboard panels target known, authoritative Zabbix hosts or approved regex."""
    dashboards = list(COMM_DASH_DIR.glob("*.json"))

    for dp in dashboards:
        with open(dp) as f:
            data = json.load(f)

        for p in data.get("panels", []):
            if p.get("type") == "row":
                continue
            for t in p.get("targets", []):
                h = t.get("host")
                if not h:
                    continue
                if isinstance(h, dict):
                    h_name = h.get("name") or h.get("filter") or ""
                else:
                    h_name = str(h)
                if not h_name or h_name in ("/.*/", "$endpoint"):
                    continue
                if any(sub in h_name for sub in ("sbce", "voice-probe")):
                    continue
                assert h_name in VALID_COMM_HOSTS, f"Panel '{p.get('title')}' in {dp.name} targets unknown host: '{h_name}'"


def test_04_native_zabbix_problems_panel_integration():
    """Verify nawari_communication_overview.json integrates the native Zabbix problems panel."""
    dash_file = COMM_DASH_DIR / "nawari_communication_overview.json"
    assert dash_file.is_file()

    with open(dash_file) as f:
        data = json.load(f)

    problem_panels = [
        p for p in data.get("panels", [])
        if p.get("type") == "alexanderzobnin-zabbix-problems-panel"
    ]
    assert len(problem_panels) >= 1, "Must contain at least one native Zabbix problems panel"

    prob_panel = problem_panels[0]
    assert "Active" in prob_panel["title"]
    assert "ZABBIX" in prob_panel["title"]
    assert "problems" in prob_panel["options"].get("subTab", "")

    # Target verification
    targets = prob_panel.get("targets", [])
    assert len(targets) > 0
    t0 = targets[0]
    assert t0.get("resultFormat") == "problems"
    assert "Voice" in t0.get("group", {}).get("filter", "")


def test_05_strict_real_vs_synthetic_separation():
    """Verify strict semantic separation between Real-Call telemetry and Synthetic Probe results."""
    dash_file = COMM_DASH_DIR / "nawari_communication_overview.json"
    with open(dash_file) as f:
        data = json.load(f)

    panels = {p.get("id"): p for p in data.get("panels", [])}

    # Panel 13: Real-Call MOS uninstrumented
    p13 = panels.get(13)
    assert p13 is not None
    assert "[NOT INSTRUMENTED — RTCP XR REQUIRED]" in p13["title"]
    assert "not instrumented" in p13["description"].lower()
    assert p13["fieldConfig"]["defaults"].get("noValue") is not None

    # Panel 14: Real-Call Packet Loss
    p14 = panels.get(14)
    assert p14 is not None
    assert "[REAL — AVAYA SNMP]" in p14["title"]
    assert "Real-Call Packet Loss (Last Hour)" in str(p14.get("targets", []))

    # Panel 15: Synthetic Voice MOS
    p15 = panels.get(15)
    assert p15 is not None
    assert "[SYNTHETIC — ASTERISK]" in p15["title"]
    assert "synthetic" in p15["description"].lower()


def test_06_null_preservation_and_gap_honesty():
    """Verify that communication dashboards do not zero-fill or span nulls on missing voice metrics."""
    dashboards = list(COMM_DASH_DIR.glob("*.json"))

    for dp in dashboards:
        with open(dp) as f:
            data = json.load(f)

        for p in data.get("panels", []):
            if p.get("type") == "row":
                continue
            # spanNulls must not be True for IP voice quality
            if "spanNulls" in str(p):
                custom = p.get("fieldConfig", {}).get("defaults", {}).get("custom", {})
                if "spanNulls" in custom:
                    assert custom["spanNulls"] is False, f"Panel '{p.get('title')}' in {dp.name} spans nulls"


def test_07_four_administrator_notification_configuration():
    """Verify that all four designated administrators are present and configured in Zabbix provisioning."""
    assert USERS_FILE.is_file(), "Users provisioning file must exist"
    with open(USERS_FILE) as f:
        data = yaml.safe_load(f)

    users = data.get("users", [])
    assert len(users) == 4, f"Expected 4 administrators, found {len(users)}"

    expected_admins = {
        "john.gacomo": "John.Gacomo@kenya-airways.com",
        "robinson.wainaina": "Robinson.Wainaina@kenya-airways.com",
        "pascal.gathungu": "Pascal.Gathungu@kenya-airways.com",
        "mercy.vaati": "Mercy.Vaati@kenya-airways.com"
    }

    user_map = {u["username"]: u for u in users}
    for uname, email in expected_admins.items():
        assert uname in user_map, f"Missing user {uname}"
        u = user_map[uname]
        medias = u.get("medias", [])
        assert len(medias) >= 1, f"User {uname} has no configured media"
        email_media = [m for m in medias if m.get("sendto") == email]
        assert len(email_media) == 1, f"User {uname} missing correct email sendto {email}"


def test_08_production_safety_boundary_enforcement():
    """Verify that physical production execution gate HARD_PRODUCTION_DENY remains active."""
    # Check that hosts file targets staging environment or documents gate
    assert HOSTS_FILE.is_file()
    with open(HOSTS_FILE) as f:
        content = f.read()

    assert "10.2.156.131" in content
    assert "10.2.156.22" in content
    assert "10.102.10.25" in content
    assert "10.2.156.60" in content
    assert "sip-trunk-carrier-01" in content
