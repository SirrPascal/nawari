# Non-SBCE SNMPv3 Device Readiness Inventory

**Audit date:** 2026-11-09  
**Scope:** Nawari repository and currently deployed Zabbix configuration  
**Excluded:** All Avaya SBCE devices, including `avaya-sbce-01`, SBCE candidates, and the simulated SBCE  
**Mode:** Read-only audit; no device polling, Zabbix mutation, service restart, or firewall change

## Status vocabulary

- **CONFIGURED:** SNMPv3 settings are present in the relevant repository/Zabbix configuration. This does not imply device-side or network-path verification.
- **PARTIALLY CONFIGURED:** An SNMP interface exists, but required SNMPv3 settings or effective credentials are incomplete/uncertain.
- **PENDING DEVICE CONFIGURATION:** The target is documented or modeled but requires device-side SNMP enablement before monitoring can work.
- **SNMPV2C:** The configured interface uses SNMPv2c.
- **UNKNOWN:** Evidence is insufficient to establish the effective configuration.
- **NOT APPLICABLE:** The object is not configured for SNMP polling.

`Zabbix status` describes the deployed Zabbix host object. `SNMPv3 readiness` describes whether the device-side and Zabbix-side requirements are evidenced; a Zabbix host being enabled is not proof that the device answers SNMP.

## Executive summary

| Measure | Result |
|---|---:|
| Live non-SBCE Zabbix hosts with SNMP interfaces | 4 production/modelled + 1 lab |
| Documented non-SBCE candidate devices not present as live Zabbix hosts | 5 |
| Non-SBCE devices requiring SNMPv3 enablement or validation | 9, excluding lab objects |
| Devices currently configured as SNMPv2c | 1 live lab object |
| Distinct SNMP polling destination ports | `161/UDP` only |
| Non-default SNMP polling destination ports | None evidenced |
| SNMP trap receiver port | `162/UDP` on Nawari host; separate from device polling |
| Live device-side SNMPv3 verification | None established by this audit |

## Device inventory

### Live or explicitly provisioned Zabbix objects

| Device / Zabbix host | IP or management address | Category / location | SNMP version | SNMP destination port | Zabbix status | SNMPv3 readiness | Evidence |
|---|---|---|---|---|---|---|---|
| `core-gw-01` | `10.2.1.1` | Core distribution gateway, HQ | SNMPv2c in repository; live API interface is SNMP | `161/UDP` explicitly configured | Enabled; template `Network Generic Device by SNMP` | **SNMPV2C** | [core_network.yaml](../../provisioning/zabbix/hosts/core_network.yaml): interface and `version: 2`; live API host `core-gw-01` |
| `avaya-sm-01` | `10.2.156.22` | Avaya Session Manager, Pride/HQ core | SNMPv3 `authPriv` modeled | `161/UDP` via `${AVAYA_SM_SNMP_PORT:-161}` | Enabled; template `Nawari Avaya Session Manager by SNMP` | **PARTIALLY CONFIGURED** | [avaya_voice_infrastructure.yaml](../../provisioning/zabbix/hosts/avaya_voice_infrastructure.yaml): host/interface; live API host `avaya-sm-01`; documentation says off-net/unverified |
| `avaya-g450-01` | `10.2.156.60` | Avaya G450 media gateway, HQ | SNMPv3 `authPriv` modeled | `161/UDP` via `${AVAYA_G450_SNMP_PORT:-161}` | Enabled; template `Nawari Avaya G450 Media Gateway by SNMP` | **PARTIALLY CONFIGURED** | [avaya_voice_infrastructure.yaml](../../provisioning/zabbix/hosts/avaya_voice_infrastructure.yaml): host/interface; live API host `avaya-g450-01`; documentation says off-net/unverified |
| `mock-core-switch-01` | Docker hostname `mock-snmp` / host `127.0.0.1:1161` | Lab simulated network device | SNMPv2c | `161/UDP` inside Docker; host test mapping `1161/UDP` | Enabled; lab template `Nawari Network Device by SNMP` | **SNMPV2C** | [mock_network_device.yaml](../../provisioning/zabbix/hosts/mock_network_device.yaml); live API host; `docker ps` mapping |

The lab object is excluded from production rollout counts. Its host-side `1161/UDP` mapping is a Docker test port, not the configured SNMP destination port of a production device.

### Documented candidates not present as live Zabbix hosts

| Device / candidate | IP or management address | Category / location | SNMP version | SNMP destination port | Zabbix status | SNMPv3 readiness | Evidence |
|---|---|---|---|---|---|---|---|
| `avaya-sm-02` candidate | `10.2.156.23` | Avaya Session Manager secondary, HQ | SNMPv3 modeled in architecture | `161/UDP` documented | Not found in live API inventory | **PENDING DEVICE CONFIGURATION** | [phase13-9-infrastructure-inventory.md](../../docs/phase13/phase13-9-infrastructure-inventory.md); no matching live API host |
| `avaya-sm-dr` candidate | `10.2.156.28` | Avaya Session Manager DR | SNMPv3 modeled in architecture | `161/UDP` documented | Not found in live API inventory | **PENDING DEVICE CONFIGURATION** | [phase13-9-infrastructure-inventory.md](../../docs/phase13/phase13-9-infrastructure-inventory.md); no matching live API host |
| `avaya-cm-standby` candidate | `10.2.156.27` | Avaya Communication Manager standby | SNMPv3 modeled in architecture | `161/UDP` documented | Not found in live API inventory | **PENDING DEVICE CONFIGURATION** | [phase13-9-infrastructure-inventory.md](../../docs/phase13/phase13-9-infrastructure-inventory.md); no matching live API host |
| `avaya-cm-vip` candidate | `10.2.156.30` | Avaya Communication Manager cluster VIP | SNMPv3 modeled in architecture | `161/UDP` documented | Not found in live API inventory | **PENDING DEVICE CONFIGURATION** | [phase13-9-infrastructure-inventory.md](../../docs/phase13/phase13-9-infrastructure-inventory.md); no matching live API host |
| Avaya CM DR candidate | `10.2.156.50` | Avaya Communication Manager DR | SNMPv3 expected by compatibility matrix | `161/UDP` by documented default | Not found in live API inventory | **UNKNOWN** | [avaya-device-compatibility-matrix.md](avaya-device-compatibility-matrix.md); no host/interface evidence |

Candidate entries require confirmation from the network/voice team before host creation. Do not treat architecture candidates as deployed devices.

### Systems modeled without an SNMP interface

| Zabbix host | Address in live Zabbix | Current interface | Readiness | Evidence |
|---|---|---|---|---|
| `sip-trunk-carrier-01` | `127.0.0.1` | Agent/trapper interface `10050`, not SNMP | **NOT APPLICABLE** to current configuration | Live API; [avaya_voice_infrastructure.yaml](../../provisioning/zabbix/hosts/avaya_voice_infrastructure.yaml) |
| `avaya-cms-01` | `127.0.0.1` | Agent/trapper interface `10050`, not SNMP | **UNKNOWN**; architecture proposes SNMPv3 but no target management IP | Live API; [avaya_voice_infrastructure.yaml](../../provisioning/zabbix/hosts/avaya_voice_infrastructure.yaml); [avaya-cms-integration.md](avaya-cms-integration.md) |
| `Zabbix server`, `endpoint-probe-01`, `nawari-voice-probe-01`, `Jimmy_Laptop` | Loopback or local names | Agent/trapper interfaces `10050` | **NOT APPLICABLE** to SNMPv3 device inventory | Live Zabbix API inventory |

These are local agent/trapper objects, not SNMP targets.

## Port findings

### SNMP polling destination

Every production/modelled SNMP interface reviewed uses `161/UDP`, either explicitly or through a `${..._SNMP_PORT:-161}` default. No non-default production SNMP polling destination port was evidenced.

The configured port means the port on the monitored device receiving Zabbix requests:

```text
Zabbix server -> monitored device: UDP 161
```

### SNMP trap receiver

The separate trap path is:

```text
Network device -> Nawari host: UDP 162
Nawari host -> snmptrap container: UDP 1162
snmptrap container -> shared spool -> Zabbix server
```

The host mapping is defined in [compose.dev.yaml](../../docker/compose.dev.yaml), and the production override maps host UDP `162` to the trap container's UDP `1162` in [compose.prod.yaml](../../docker/compose.prod.yaml). This is not the destination port used for Zabbix polling.

## SNMPv3 configuration findings

- The Avaya Session Manager, Communication Manager and G450 repository definitions specify `authPriv`, security name `Admin`, and SHA/AES family settings through environment substitutions.
- The repository defaults show `SHA256` and `AES128`; the actual device configuration and effective runtime values were not independently verified.
- The core gateway is explicitly configured as SNMPv2c and should not be silently changed to SNMPv3. Network-team confirmation is required.
- No device passwords, authentication keys or privacy keys are reproduced in this report.
- The live Zabbix API inventory confirms host names, addresses, interfaces and templates, but this audit did not query or expose secret-valued macros.
- The repository's [mock fixture](../../provisioning/zabbix/hosts/mock_network_device.yaml) is a lab SNMPv2c object and is not evidence for production device security.

## Network-team action list

### Priority 1 — configure/validate existing production targets

1. **`core-gw-01` — `10.2.1.1`**
   - Decide whether SNMPv3 is required.
   - If yes, enable read-only SNMPv3 `authPriv` on the gateway and provide the approved algorithm/security identity through the secret-management process.
   - Permit UDP `161` from the actual Zabbix polling source.
   - Do not assume the documented `public` SNMPv2c community remains acceptable.

2. **`avaya-sm-01` — `10.2.156.22`**
   - Enable/confirm read-only SNMPv3 `authPriv`.
   - Confirm exact SHA and AES variants and permit UDP `161`.
   - Confirm whether `10.2.5.164` is the effective source address after Docker routing/NAT; do not approve an ACL based only on the container address.

3. **`avaya-g450-01` — `10.2.156.60`**
   - Enable/confirm read-only SNMPv3 `authPriv`.
   - Confirm exact device release, MIB package, SHA/AES variants and UDP `161` ACL.

### Priority 2 — candidate devices

Confirm whether the following are real monitoring targets, then enable read-only SNMPv3 and permit UDP `161` if approved:

```text
10.2.156.23  Avaya Session Manager secondary
10.2.156.28  Avaya Session Manager DR
10.2.156.27  Avaya Communication Manager standby
10.2.156.30  Avaya Communication Manager VIP
10.2.156.50  Avaya Communication Manager DR
```

Do not prescribe vendor CLI commands until the exact appliance releases and approved change procedures are known.

## Zabbix-side action list

1. Keep `avaya-sm-01`, `avaya-cm-01` and `avaya-g450-01` as the canonical existing hosts; do not create duplicates.
2. Resolve and protect the effective SNMPv3 credentials and algorithm variants through Zabbix secret fields/macros.
3. Validate each SNMP interface as `161/UDP`; record any approved exception explicitly.
4. Assign the existing vendor template only after its OIDs are verified against the device release/MIB.
5. Add candidate hosts only after the network team confirms the target identity, management IP and monitoring scope.
6. For each host, run a controlled scalar test first (`sysObjectID`, `sysDescr`, `sysName`, `sysUpTime`), then an interface walk.
7. Record numeric OIDs, data types, units, indexes, release/MIB evidence and polling intervals before creating item prototypes.
8. Keep unverified application metrics disabled or clearly marked; do not convert speculative trapper metrics into SNMP items.
9. Validate SNMP availability and item history before enabling production triggers.
10. Keep trap testing separate from polling validation; a received trap does not prove polling works.

## Evidence classification

| Finding type | Meaning in this audit |
|---|---|
| **PASS** | Repository or live Zabbix evidence is present for the stated fact |
| **FAIL** | A required artifact is absent or a current configuration conflicts with the requested SNMPv3 target |
| **BLOCKED** | Further validation requires device-side configuration, credentials, network approval or an authoritative MIB |
| **NOT VERIFIED** | The repository models the capability, but no live device result was obtained |

## Outstanding questions

1. Which non-SBCE devices are truly in the current production monitoring scope?
2. Should `core-gw-01` be migrated from SNMPv2c to SNMPv3, and which exact algorithms are approved?
3. What are the exact releases and approved MIB packages for the Avaya SM, CM and G450 devices?
4. Are the five Avaya candidate addresses real devices, VIPs, or documentation-only placeholders?
5. What source IP does the Zabbix poller present to each network segment?
6. Are any devices intentionally configured on a non-default SNMP destination port?
7. Should CMS/WFO receive host-level SNMP monitoring, and what is its management IP?

## Prioritized implementation sequence

1. Network team confirms scope, device releases, source ACLs and SNMPv3 settings.
2. Zabbix team validates existing host interfaces and protected credentials.
3. Test one scalar OID per existing production host.
4. Obtain and validate vendor MIBs.
5. Perform controlled standard-MIB and vendor-subtree walks.
6. Review OID inventory with the network/voice teams.
7. Add verified items, discovery rules, preprocessing and triggers.
8. Register approved candidates and repeat the same validation sequence.
9. Separately test SNMP traps on UDP `162`.

## Final conclusion

The repository and live Zabbix state identify `161/UDP` as the only SNMP polling destination port. The only separate trap destination is UDP `162` on the Nawari host. Existing Avaya non-SBCE hosts are modeled for SNMPv3 but remain operationally unverified; the core gateway is explicitly SNMPv2c. No device-side SNMPv3 enablement, live polling, firewall change or Zabbix mutation was performed during this audit.
