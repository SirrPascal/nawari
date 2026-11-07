"""Integration test for Nawari declarative provisioning idempotency.

Validates that running the Reconciler against a live Zabbix instance applies
changes accurately and achieves an idempotent state (0 changes on subsequent run).
"""

import pytest

from services.api.client.zabbix_client import ZabbixClient
from services.api.config import get_settings
from services.api.provisioning.reconciler import Reconciler
from services.api.provisioning.schema import load_desired_state_from_dir


@pytest.fixture(scope="module")
def zabbix_client():
    settings = get_settings()
    client = ZabbixClient(settings.zabbix)
    client.connect()
    yield client
    client.disconnect()


def test_live_provisioning_idempotency(zabbix_client):
    """Exit gate validation: Reconciler must achieve 0-change steady state."""
    settings = get_settings()
    state = load_desired_state_from_dir(settings.provisioning_dir)
    assert len(state.hosts) > 0, "No desired hosts found in provisioning/zabbix"

    reconciler = Reconciler(zabbix_client)

    # 1. Run apply
    report1 = reconciler.apply(state)
    assert report1 is not None

    # 2. Run plan immediately after apply
    report2 = reconciler.plan(state)

    # Exit Gate Check: Idempotency contract
    assert report2.has_changes is False, (
        f"Idempotency violation! Secondary plan detected changes:\n{report2.render_text()}"
    )
    assert len(report2.creates) == 0
    assert len(report2.updates) == 0
    assert len(report2.noops) == len(state.host_groups) + len(state.hosts)


def test_live_hosts_verification(zabbix_client):
    """Verify that provisioned hosts exist in Zabbix with correct attributes."""
    hosts = zabbix_client.get_hosts(["avaya-sbce-01", "core-gw-01"])
    assert len(hosts) == 2, f"Expected 2 hosts, found: {len(hosts)}"

    sbce = next(h for h in hosts if h["host"] == "avaya-sbce-01")
    assert "SBCE Primary" in sbce["name"]
    assert len(sbce["interfaces"]) >= 1
    assert sbce["interfaces"][0]["ip"] == "10.2.156.131"

    gw = next(h for h in hosts if h["host"] == "core-gw-01")
    assert "Core Distribution Gateway" in gw["name"]
    assert len(gw["interfaces"]) >= 1
    assert gw["interfaces"][0]["ip"] == "10.2.1.1"

