# Avaya SBCE SNMP Readiness Audit

**Target:** Avaya SBCE `10.2.156.131`  
**Audit date:** 2026-11-09  
**Mode:** Read-only inspection  
**Change safety:** No containers, volumes, Zabbix objects, firewall rules, SBCE settings, or Sentra files were changed.

## Status summary

| Area | Status | Finding |
|---|---|---|
| Running Zabbix server | PASS | `nawari-zabbix-server`, `zabbix/zabbix-server-pgsql:alpine-7.4-latest`, running Zabbix `7.4.16` |
| Running frontend | PASS | `nawari-zabbix-web`, `zabbix/zabbix-web-nginx-pgsql:alpine-7.4-latest`, healthy |
| SNMP polling capability | PASS | Zabbix links to Net-SNMP (`libnetsnmp.so.45`) and has SNMP poller processes configured |
| SNMPv3 authPriv path | PASS | Zabbix 7.4 supports SNMPv3 interfaces; SHA/AES must still be verified against the appliance |
| SNMP walk utility in Zabbix server | NOT TESTED | `snmpwalk`, `snmpget` and `snmpbulkwalk` are not installed in the server container |
| SNMP walk through frontend | NOT TESTED | Requires frontend/API verification after credentials and device access are available |
| Custom Avaya MIBs | FAIL | No Avaya vendor MIBs found in the repository or mounted `nawari-zabbix-mibs` volume |
| Existing SBCE host | PASS | `avaya-sbce-01` exists with SNMP interface `10.2.156.131:161` |
| Existing SBCE template | BLOCKED | `Nawari Avaya SBCE by SNMP` exists, but its vendor/application metrics are marked unverified and are mostly trapper items |
| Host route | PASS | Host route uses gateway `10.2.5.1` on interface `en11` |
| Live SNMP reachability | BLOCKED | SBCE SNMP is not enabled; no credentialed SNMP request was attempted |
| Production changes | PASS | No service restart, recreation, upgrade, or configuration mutation was performed |

## 1. Runtime inventory

The running Compose project is `nawari`, using:

```text
/Users/madeira/Desktop/Projects/nawari/docker/compose.yaml
/Users/madeira/Desktop/Projects/nawari/docker/compose.dev.yaml
```

| Container | Image | State / binding |
|---|---|---|
| `nawari-zabbix-server` | `zabbix/zabbix-server-pgsql:alpine-7.4-latest` | Healthy; TCP `0.0.0.0:10051 -> 10051` |
| `nawari-zabbix-web` | `zabbix/zabbix-web-nginx-pgsql:alpine-7.4-latest` | Healthy; TCP `127.0.0.1:8088 -> 8080` |
| `nawari-snmptraps` | `zabbix/zabbix-snmptraps:alpine-7.4-latest` | Running; UDP `0.0.0.0:162 -> 1162` |
| `nawari-postgres` | `postgres:17-alpine` | Healthy; TCP `127.0.0.1:5433 -> 5432` |
| `nawari-grafana` | `nawari-grafana:11.6.0-zabbix-6.10.2` | Healthy; TCP `127.0.0.1:3001 -> 3000` |

The actual running server reports Zabbix `7.4.16`. The development Compose file uses a floating `alpine-7.4-latest` tag, while the production override uses `alpine-7.4.0`; these are deployment reproducibility issues to resolve separately. No upgrade or restart was performed during this audit.

## 2. Zabbix and SNMP capability assessment

The Zabbix server has:

- `ZBX_ENABLE_SNMP_TRAPS=true`.
- `ZBX_SNMPTRAPPERDIR=/var/lib/zabbix/snmptraps`.
- Five configured pollers.
- Five configured unreachable pollers.
- Five configured trappers.
- Net-SNMP runtime linkage through `libnetsnmp.so.45`.
- Standard Net-SNMP MIBs and SNMPv3 USM/AES support libraries in the server image.

The server image does **not** contain the command-line utilities `snmpwalk`, `snmpget` or `snmpbulkwalk`. This does not prevent Zabbix SNMP polling, but it means a shell-based walk cannot be executed inside the running server container.

The trap container contains `snmptrapd` and shares the `snmptrap-spool` volume with the server. This supports the Zabbix trap architecture, but trap reception is separate from active polling and does not prove that `10.2.156.131` responds to SNMP requests.

### Supported configuration path

Configure the SBCE as a Zabbix SNMP interface:

```text
Address:       10.2.156.131
Port:          161/UDP
Version:       SNMPv3
Security level: authPriv
Security name: Admin
Authentication: SHA (exact variant confirmed with Avaya team)
Privacy:        AES (exact variant confirmed with Avaya team)
```

Do not assume `SHA256` or `AES128` from the simulated fixture is the production setting. The Avaya configuration and deployed Zabbix UI/API choices must agree on the exact algorithm variants.

## 3. Existing Zabbix inventory

The read-only Zabbix API inventory reports:

```text
Host: avaya-sbce-01
Name: Avaya SBCE Primary (HQ-DMZ)
SNMP interface: 10.2.156.131:161
Template: Nawari Avaya SBCE by SNMP
Status: enabled
```

Other relevant existing objects include `mock-avaya-sbce-01`, `avaya-sm-01`, `avaya-cm-01`, and `avaya-g450-01`.

The requested name `Template Avaya SBCE SNMP` does not match the existing template name `Nawari Avaya SBCE by SNMP`. No rename was performed. Use one canonical name before adding a new template or provisioning workflow.

## 4. Template and MIB findings

The existing [nawari_avaya_sbce.yaml](../../provisioning/zabbix/templates/nawari_avaya_sbce.yaml) contains:

- A dependency on `Nawari Generic SNMP Base`.
- Generic system and interface-related design intent.
- Multiple trapper items for active calls, registrations, SRTP, direct media and license utilization.
- Descriptions explicitly marked `CONFIGURED_UNVERIFIED`.

Those trapper items are not verified SBCE SNMP OIDs and must not be presented as SNMP-collected metrics. They may represent a future ingestion design, but they are outside the first SNMP discovery result until an authoritative source and collection method are established.

No Avaya MIB files were found in the repository or the mounted custom MIB volume. Only standard Net-SNMP/RFC MIBs are present. Obtain the exact MIB package for the deployed SBCE release from an approved Avaya source or internal serviceability package before symbolic OID work.

### Sensitive fixture finding

The simulated fixture [mock_avaya_sbce.yaml](../../provisioning/zabbix/hosts/mock_avaya_sbce.yaml) contains example authentication/passphrase values. They are lab values, but they are still a poor production pattern. Do not copy them to `avaya-sbce-01`, and replace them with protected runtime macros or an approved secret mechanism in a separately approved change.

## 5. Network readiness

The Mac currently has:

```text
Interface: en11
Address:   10.2.5.164
Route:     10.2.156.131 via 10.2.5.1
```

This proves a host route exists. It does not prove SNMP service availability.

An ICMP probe received no response. ICMP failure is inconclusive because the SBCE or an intermediate firewall may block ping. A UDP `nc` result is also not a valid SNMP success test because UDP has no handshake.

The decisive test must be a credentialed SNMPv3 request after the Avaya team enables SNMP and permits UDP `161` from the actual Zabbix polling source. The Docker server container currently has a default route through Docker NAT; validate the source address and ACL behavior from the production host before relying on container polling.

## 6. Post-enable discovery procedure

### Avaya team prerequisites

1. Enable SNMPv3 on `10.2.156.131`.
2. Create or approve the `Admin` SNMPv3 user with `authPriv`.
3. Confirm the exact authentication variant and privacy variant.
4. Permit UDP `161` from the Zabbix polling source address.
5. Provide the SBCE release and approved Avaya MIB package.
6. Confirm whether traps are required and, if so, the destination/source policy for UDP `162`.

### Zabbix registration

1. Open the Zabbix frontend at `http://127.0.0.1:8088` on the Nawari host, or use the approved administrative access path.
2. Use the existing host `avaya-sbce-01`; do not create a duplicate host.
3. Confirm the SNMP interface is `10.2.156.131`, port `161`, and the interface is the main interface.
4. Set SNMPv3 security level to `authPriv`.
5. Set security name to `Admin`.
6. Set the exact Avaya-approved SHA and AES variants.
7. Enter credentials through protected Zabbix fields/macros; never place them in YAML, shell history, logs, screenshots or Git.
8. Keep the host disabled until the credentials and firewall path are confirmed, if the operational change window requires that control.

### Discovery sequence

Start with the least expansive checks:

1. `SNMPv2-MIB::sysObjectID.0` / numeric `1.3.6.1.2.1.1.2.0`.
2. `sysDescr.0`, `sysName.0`, `sysUpTime.0`, `sysLocation.0`.
3. `IF-MIB::ifName` and `ifDescr`.
4. `ifOperStatus`, `ifHighSpeed`, HC inbound/outbound octets, errors and discards.
5. Walk only the approved Avaya enterprise subtree after the vendor MIB and release are identified.
6. Record each returned OID before creating an item.

For each candidate, record:

```text
numeric_oid
symbolic_oid
mib_name
object_name
description
returned_value
snmp_datatype
units
table_or_scalar
index_fields
poll_interval
retention_requirement
device_release
validation_source
collection_decision
```

Do not create an item solely because an OID appears in a generic document or an old Sentra configuration.

## 7. Template design gate

The eventual canonical template should contain only:

- Verified scalar system items.
- Verified interface discovery and item prototypes.
- Verified resource/application items with release evidence.
- Explicit preprocessing and units.
- Triggers whose thresholds are operationally approved.
- Tags identifying `vendor=avaya`, `role=sbce`, `collection=snmp`, and validation state.

Every unverified metric must remain out of the production template or be clearly isolated as a disabled lab proposal. The existing trapper items should not be converted into SNMP items without evidence.

## 8. Readiness checklist

- [x] Running Zabbix server identified.
- [x] Running frontend identified.
- [x] Zabbix version identified as `7.4.16`.
- [x] Zabbix SNMP runtime capability identified.
- [x] Existing SBCE host identified.
- [x] Existing SBCE SNMP interface identified.
- [x] Host route identified.
- [ ] SNMPv3 enabled on SBCE.
- [ ] Exact SHA variant confirmed.
- [ ] Exact AES variant confirmed.
- [ ] UDP `161` ACL approved and tested.
- [ ] Credentialed SNMPv3 scalar query succeeds.
- [ ] Approved Avaya MIB package obtained.
- [ ] Vendor OID walk completed.
- [ ] OID inventory reviewed.
- [ ] Canonical SBCE template name and scope approved.
- [ ] Only verified OIDs added to the production template.
- [ ] Trap behavior separately tested, if required.

## 9. Changes requiring approval

No changes were made. The following are proposed only:

1. Add approved Avaya MIB files to the `zabbix-mibs` volume/build path.
2. Replace floating `alpine-7.4-latest` tags with a tested immutable patch tag.
3. Move SBCE credentials out of fixture/config files and into protected Zabbix runtime fields.
4. Remove or isolate speculative SBCE trapper metrics from the production SNMP template.
5. Rename or formally retain the existing `Nawari Avaya SBCE by SNMP` template.
6. Add verified SBCE OIDs and LLD prototypes only after the first authorized walk.

## Final conclusion

The Nawari Zabbix deployment is structurally ready for SBCE SNMPv3 registration: the server is running Zabbix `7.4.16`, has Net-SNMP-backed polling, and already contains `avaya-sbce-01` at `10.2.156.131:161`. Discovery is **BLOCKED**, not successful, until SNMPv3 is enabled on the SBCE, the exact algorithms and credentials are confirmed, UDP `161` is permitted, and an authorized request returns data. No additional SNMP monitoring container is required.
