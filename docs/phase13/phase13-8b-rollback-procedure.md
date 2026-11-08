# Phase 13.8B Rollback and Emergency Recovery Procedure

**Author:** Antigravity Engineering (pair programming with User)  
**Date:** 2026-11-08  
**Status:** Approved Operational Runbook  
**Target Environment:** Nawari Staging Environment (`mon-grafana01`)  
**Target Platform:** Zabbix 7.4.4 / PostgreSQL Engine  
**Snapshot Baseline:** `provisioning/zabbix/snapshots/phase13_8b_pre_mutation_baseline.json`

---

## 1. Scope and Objective

This runbook defines the emergency rollback procedure for **Phase 13.8B: Controlled Zabbix Threshold Implementation, Hysteresis & Alert Policy Enforcement**.

If staging triggers exhibit unexpected evaluation loops, false flapping, or communication action instability, this procedure restores all 76 triggers and 11 trigger prototypes across the 11 monitored templates to their exact pre-mutation state (`recovery_mode: 0`, baseline problem expressions, empty recovery expressions, and original tags).

### Operational Safety Guard
- **`HARD_PRODUCTION_DENY`**: This procedure is strictly scoped to the staging platform (`http://localhost:8088`). Under no circumstances may this script be directed against production Zabbix infrastructure.
- **Sentra Isolation**: The upstream Sentra repository (`/Users/madeira/Desktop/Projects/sentra`) remains isolated at commit `9970404` and is never modified during rollback.

---

## 2. Pre-Mutation Baseline Snapshot Artifacts

The rollback state was captured prior to any Phase 13.8B mutations and is committed in the repository:

1. **Full Baseline Snapshot:** `provisioning/zabbix/snapshots/phase13_8b_pre_mutation_baseline.json`
   - Captured: 2026-11-08T15:20:00 UTC
   - Templates: 11 templates
   - Triggers: 76 triggers (68 non-inherited template triggers)
   - Prototypes: 11 trigger prototypes
   - Discovered Triggers: 54 discovered interface triggers on mock lab hosts
2. **Exact Template Inventory:** `provisioning/zabbix/snapshots/phase13_8b_exact_template_inventory.json`
   - Maps every template trigger ID to its exact host template and item key.
3. **Change Manifest:** `provisioning/zabbix/snapshots/phase13_8b_change_manifest.json`
   - Records every mutation applied in Phase 13.8B for bi-directional auditing.

---

## 3. Rollback Execution Procedure

### Step 1: Pre-Rollback Health & Connectivity Check
Verify connectivity to the local Zabbix JSON-RPC API:
```bash
cd /Users/madeira/Desktop/Projects/nawari
python3 -c '
from services.api.client.zabbix_client import ZabbixClient
from services.api.config import ZabbixSettings
client = ZabbixClient(ZabbixSettings())
client.connect()
print("Zabbix API Connected Successfully")
'
```

### Step 2: Execute Automated Rollback Script
Execute the rollback restoration script using the baseline snapshot:
```bash
cd /Users/madeira/Desktop/Projects/nawari
PYTHONPATH=. /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -c '
import json
import logging
from pathlib import Path
from services.api.client.zabbix_client import ZabbixClient
from services.api.config import ZabbixSettings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Phase13_8B_Rollback")

baseline_path = Path("provisioning/zabbix/snapshots/phase13_8b_pre_mutation_baseline.json")
with open(baseline_path, "r", encoding="utf-8") as f:
    baseline = json.load(f)

client = ZabbixClient(ZabbixSettings())
client.connect()

# Revert Template Triggers
logger.info("Reverting %d template triggers to baseline...", len(baseline["triggers"]))
for trig in baseline["triggers"]:
    tid = trig["triggerid"]
    try:
        client.call("trigger.update", {
            "triggerid": tid,
            "expression": trig["expression"],
            "recovery_mode": int(trig.get("recovery_mode", 0)),
            "recovery_expression": trig.get("recovery_expression", ""),
            "priority": int(trig.get("priority", 2)),
            "tags": trig.get("tags", []),
        })
        logger.info("   [REVERTED] Trigger %s: %s", tid, trig["description"])
    except Exception as e:
        logger.error("   [ERROR] Failed reverting trigger %s: %s", tid, e)

# Revert Template Prototypes
logger.info("Reverting %d trigger prototypes to baseline...", len(baseline["prototypes"]))
for proto in baseline["prototypes"]:
    pid = proto["triggerid"]
    try:
        client.call("triggerprototype.update", {
            "triggerid": pid,
            "expression": proto["expression"],
            "recovery_mode": int(proto.get("recovery_mode", 0)),
            "recovery_expression": proto.get("recovery_expression", ""),
            "priority": int(proto.get("priority", 2)),
            "tags": proto.get("tags", []),
        })
        logger.info("   [REVERTED] Prototype %s: %s", pid, proto["description"])
    except Exception as e:
        logger.error("   [ERROR] Failed reverting prototype %s: %s", pid, e)

logger.info("Rollback complete.")
'
```

### Step 3: Reload Zabbix Server Configuration Cache
Force Zabbix Server to reload its in-memory configuration cache from PostgreSQL:
```bash
docker exec nawari-zabbix-server zabbix_server -R config_cache_reload
```

### Step 4: Re-trigger LLD Discovery on Mock Hosts
Trigger discovery rules on `mock-core-switch-01` and `mock-avaya-sbce-01` to synchronize discovered triggers:
```bash
PYTHONPATH=. /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -c '
from services.api.client.zabbix_client import ZabbixClient
from services.api.config import ZabbixSettings
client = ZabbixClient(ZabbixSettings())
client.connect()
hosts = client.call("host.get", {"filter": {"host": ["mock-avaya-sbce-01", "mock-core-switch-01"]}})
hostids = [h["hostid"] for h in hosts]
drules = client.call("discoveryrule.get", {"hostids": hostids, "output": ["itemid"]})
if drules:
    client.call("task.create", [{"type": 6, "request": {"itemid": dr["itemid"]}} for dr in drules])
    print(f"Triggered {len(drules)} LLD rediscovery tasks.")
'
```

---

## 4. Post-Rollback Verification

1. **Verify Trigger Recovery Modes:**
   Confirm that template triggers have returned to `recovery_mode: 0`:
   ```bash
   PYTHONPATH=. /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -c '
   from services.api.client.zabbix_client import ZabbixClient
   from services.api.config import ZabbixSettings
   client = ZabbixClient(ZabbixSettings())
   client.connect()
   trigs = client.call("trigger.get", {"templateids": ["10784"], "output": ["triggerid", "recovery_mode"]})
   for t in trigs:
       assert str(t["recovery_mode"]) == "0", f"Trigger {t[\"triggerid\"]} not reverted"
   print("All triggers verified at recovery_mode: 0")
   '
   ```

2. **Run Master Regression Suites:**
   ```bash
   bash scripts/verify_phase10.sh
   bash scripts/verify_phase13.sh
   ```

---

## 5. Rollback Decision Matrix

| Symptom / Condition | Severity | Immediate Action | Escalation Path |
| :--- | :--- | :--- | :--- |
| Single trigger flapping due to narrow deadband | Low | Adjust threshold via `implement_phase13_8b_thresholds.py` | Voice/Network Lead |
| LLD discovery task crash on mock switches | Medium | Re-run discovery task creation after 15s | Antigravity Pair Lead |
| Zabbix Server process crash or DB deadlocks | Critical | Execute Full Rollback (Section 3) | Platform Architect |
| Duplicate alerts dispatched across Actions 10-15 | Critical | Execute Full Rollback (Section 3) | Platform Architect |

