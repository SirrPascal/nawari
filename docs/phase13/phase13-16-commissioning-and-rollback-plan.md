# Phase 13.16 — Production Commissioning & Rollback Plan

## Overview

This document specifies the exact technical procedures, pre-flight safety checks, cutover milestones, and emergency rollback procedures for transitioning Nawari from staging into live 24/7 flight operations monitoring.

---

## 1. Production Commissioning Pre-Flight Checklist

Before removing the `HARD_PRODUCTION_DENY` interlock and enabling active alerting:

1. [x] **Repository Isolation Verified**: Adjacent `sentra` repository clean on `main` at `9970404`.
2. [x] **Zabbix Baseline Verified**: 12 hosts, 422 items, 70 triggers with dual-expression recovery hysteresis.
3. [x] **Action Routing Verified**: Mutual exclusivity confirmed across Actions 10–15; no duplicate alert storms.
4. [x] **Recipient Directory Verified**: All 5 named Kenya Airways administrators configured with correct media types.
5. [x] **Gated Telemetry Isolated**: 5 unverified metrics strictly tagged as `NOT_COLLECTED`.
6. [x] **Grafana Dashboards Audited**: 24 dashboards and 282 panels categorized by provenance in isolated folders.
7. [ ] **IPsec/MPLS Routing Permitted**: Network operations enables firewall transit for `10.2.156.0/24` and `10.2.1.0/24`.
8. [ ] **SMTP / SMS Gateway Credential Injection**: Production credentials populated in `.env` for M365 and Safaricom SMS.

---

## 2. Commissioning Procedure (Step-by-Step)

```
[ Pre-Flight Validation ]
          |
          v
[ Enable Network Routing (IPsec/MPLS) ]
          |
          v
[ Test SNMPv3 authPriv against Production Switch ]
          |
          v
[ Update HARD_PRODUCTION_DENY to False in config.py ]
          |
          v
[ Activate Production Zabbix Actions 10, 11, 12, 13, 14 ]
          |
          v
[ Post-Cutover 24-Hour Soak Period ]
```

### Execution Commands:
1. Update `.env` with production parameters:
   ```bash
   sed -i '' 's/HARD_PRODUCTION_DENY=True/HARD_PRODUCTION_DENY=False/g' .env
   ```
2. Verify live Zabbix API connectivity:
   ```bash
   PYTHONPATH=. /usr/bin/python3 scripts/test_phase13_9_physical_telemetry.py
   ```
3. Enable active notification actions via Zabbix API:
   ```bash
   PYTHONPATH=. /usr/bin/python3 -c "
   from services.api.config import ZabbixSettings
   from services.api.client.zabbix_client import ZabbixClient
   client = ZabbixClient(ZabbixSettings())
   client.connect()
   for actionid in ['10', '11', '12', '13', '14']:
       client.call('action.update', {'actionid': actionid, 'status': 0})
   print('Production notification actions activated.')
   "
   ```

---

## 3. Rollback Decision Tree & Procedure

If unintended alert storms, network interface lockups, or host flapping occur within the initial 24-hour window:

```
[ Incident / Anomaly Detected ]
          |
          +--> Alert Storm (> 20 alerts/min)? ----> [ Disable Actions Immediately ]
          |
          +--> Mon-grafana01 Resource Spike? -----> [ Stop Collector Containers ]
          |
          +--> Production Device Lockup? ---------> [ Re-enable HARD_PRODUCTION_DENY ]
```

### Emergency 60-Second Rollback:
```bash
# 1. Immediately disable all notification actions via API
PYTHONPATH=. /usr/bin/python3 -c "
from services.api.config import ZabbixSettings
from services.api.client.zabbix_client import ZabbixClient
client = ZabbixClient(ZabbixSettings())
client.connect()
for actionid in ['10', '11', '12', '13', '14', '15']:
    client.call('action.update', {'actionid': actionid, 'status': 1})
print('EMERGENCY ROLLBACK: All notification actions disabled.')
"

# 2. Re-assert HARD_PRODUCTION_DENY
sed -i '' 's/HARD_PRODUCTION_DENY=False/HARD_PRODUCTION_DENY=True/g' .env

# 3. Restore pre-mutation Zabbix baseline
docker exec -i nawari-postgres psql -U zabbix -d zabbix < provisioning/zabbix/snapshots/phase13_8b_pre_mutation_baseline.sql
```
Total rollback execution time: **< 2 minutes**.
