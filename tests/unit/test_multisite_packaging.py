"""tests/unit/test_multisite_packaging.py
=======================================
Unit tests for Deployment Profiles and Packaging Engine (Workstream 13G).
"""

import pytest
from services.multisite.packaging import (
    DeploymentProfileManager,
    DeploymentTier,
    PackagingTarget,
    ProductionGatingViolation,
    SystemdServiceConfig,
    SystemdUnitGenerator,
)


@pytest.fixture
def profile_mgr():
    return DeploymentProfileManager()


def test_profile_loading_and_attributes(profile_mgr):
    # 1. Simulation profile
    sim = profile_mgr.load_profile("simulation")
    assert sim["profile_name"] == "simulation"
    assert sim["live_mutation_allowed"] is False
    assert sim["production_gate_required"] is False

    # 2. Staging profile
    stg = profile_mgr.load_profile("staging")
    assert stg["profile_name"] == "staging"
    assert stg["host_resource_budget"]["max_container_memory_mb"] <= 2252

    # 3. Production profiles
    prod_single = profile_mgr.load_profile("single-site-production")
    assert prod_single["phase_8_2_commissioning_required"] is True

    prod_multi = profile_mgr.load_profile("multi-site-production")
    assert prod_multi["phase_8_2_commissioning_required"] is True

    # 4. Unknown profile
    with pytest.raises(FileNotFoundError):
        profile_mgr.load_profile("nonexistent-profile")


def test_phase_8_2_production_gating_enforcement(profile_mgr):
    # 1. Simulation is allowed without Phase 8.2
    res_sim = profile_mgr.validate_deployment_eligibility("simulation", is_phase_8_2_certified=False)
    assert res_sim["allowed"] is True
    assert res_sim["status"] == "APPROVED_FOR_DEPLOYMENT"

    # 2. Staging is allowed without Phase 8.2
    res_stg = profile_mgr.validate_deployment_eligibility("staging", is_phase_8_2_certified=False)
    assert res_stg["allowed"] is True
    assert res_stg["status"] == "APPROVED_FOR_DEPLOYMENT"

    # 3. Production WITHOUT Phase 8.2 certification -> HARD_PRODUCTION_DENY
    res_prod = profile_mgr.validate_deployment_eligibility("multi-site-production", is_phase_8_2_certified=False)
    assert res_prod["allowed"] is False
    assert res_prod["status"] == "HARD_PRODUCTION_DENY"
    assert "Phase 8.2 physical enterprise commissioning" in res_prod["reason"]

    with pytest.raises(ProductionGatingViolation) as exc_info:
        profile_mgr.assert_deployment_allowed("multi-site-production", is_phase_8_2_certified=False)
    assert "HARD_PRODUCTION_DENY" in str(exc_info.value)

    # 4. Production WITH Phase 8.2 certification -> APPROVED_FOR_DEPLOYMENT
    res_prod_ok = profile_mgr.validate_deployment_eligibility("multi-site-production", is_phase_8_2_certified=True)
    assert res_prod_ok["allowed"] is True
    assert res_prod_ok["status"] == "APPROVED_FOR_DEPLOYMENT"


def test_systemd_unit_file_generation():
    # 1. Hub config unit
    hub_cfg = SystemdUnitGenerator.get_standard_hub_config()
    hub_unit = SystemdUnitGenerator.generate_unit(hub_cfg)
    assert "Description=Nawari Central Hub" in hub_unit
    assert "MemoryMax=768M" in hub_unit
    assert "CPUQuota=80%" in hub_unit
    assert "ProtectSystem=strict" in hub_unit
    assert "NoNewPrivileges=true" in hub_unit
    assert "Restart=always" in hub_unit
    assert "WatchdogSec=30s" in hub_unit

    # 2. Regional proxy unit
    proxy_cfg = SystemdUnitGenerator.get_standard_proxy_config()
    proxy_unit = SystemdUnitGenerator.generate_unit(proxy_cfg)
    assert "MemoryMax=256M" in proxy_unit
    assert "CPUQuota=40%" in proxy_unit

    # 3. Edge collector unit
    edge_cfg = SystemdUnitGenerator.get_standard_edge_config()
    edge_unit = SystemdUnitGenerator.generate_unit(edge_cfg)
    assert "MemoryMax=128M" in edge_unit
    assert "CPUQuota=25%" in edge_unit

