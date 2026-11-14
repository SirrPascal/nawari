import importlib.util
import pathlib


ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_validator():
    path = ROOT / "scripts" / "validate_enterprise_registers.py"
    spec = importlib.util.spec_from_file_location("enterprise_registers", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_enterprise_registers_are_valid():
    module = load_validator()
    module.main()


def test_alerts_default_to_shadow_mode():
    assert load_validator().load("alert-ownership.v1.json")["default_mode"] == "shadow"


def test_no_integration_uses_direct_database_access():
    integrations = load_validator().load("integration-inventory.v1.json")["integrations"]
    assert integrations and all(item["direct_database_access"] is False for item in integrations)


def test_tls_policy_disables_legacy_and_early_data():
    policy = load_validator().load("tls-policy.v1.json")
    assert policy["minimum"] == "TLSv1.2"
    assert policy["preferred"] == "TLSv1.3"
    assert set(policy["disabled"]) == {"SSLv2", "SSLv3", "TLSv1.0", "TLSv1.1"}
    assert policy["early_data"].startswith("disabled")
