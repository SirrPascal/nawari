# Nawari Phase 9 Master Technical Specification
## Network Intelligence, Dynamic Topology Mapping & Dependency Graph Engine

**Document Version:** 1.0.0  
**Status:** Approved Master Architecture Specification  
**Date:** 2026-11-08  
**Baseline Commit:** [`b45dbf1`](file:///Users/madeira/Desktop/Projects/nawari) (Phase 7 Complete, 188 Passing Tests)  
**Target Environment:** Production Host `mon-grafana01` (Ubuntu 24.04 LTS, 2 vCPU, 7.8 GiB RAM) & Enterprise Network Infrastructure  
**Core Architectural Directive:**  
> *"Zabbix monitors. Grafana visualizes. Nawari discovers topology, correlates cross-domain evidence, and assures services."*

---

## 1. Executive Summary & Problem Statement

Across Phases 1 through 8, Nawari established enterprise infrastructure monitoring (Zabbix 7.4), Avaya SBCE appliance telemetry, controlled synthetic voice testing (Asterisk 22 AMI), endpoint-to-service probing (DNS, TCP, TLS, HTTP, Paris traceroute), and multi-domain root-cause correlation.

However, existing monitoring remains **device-centric rather than relationship-centric**:
* Zabbix observes that switch interface `Te1/0/1` transitioned to `operStatus = down (2)`.
* An endpoint in the airport terminal observes packet loss to its default gateway.
* Synthetic voice probes observe elevated call setup latency (SIP 180 Ringing delayed by 4.2s).

Currently, Nawari's correlation engine must infer causality through temporal proximity and heuristic rules. It lacks authoritative knowledge of the **physical and logical structure connecting these components**:
1. Does switch interface `Te1/0/1` carry the uplink for the affected airport terminal access switch?
2. Does the primary SIP signaling path traverse this specific switch trunk, or does a redundant LACP port-channel provide hitless failover?
3. Which corporate subnets, IP phones, gate check-in workstations, and business services depend on this physical asset?
4. What exact topological change occurred immediately prior to the observed service degradation?

**Phase 9 introduces the Network Intelligence Layer.** It transforms Nawari from an alert correlator into a **topology-aware service assurance platform**. By combining SNMP MIB-II, LLDP, CDP, ARP/MAC forwarding tables, IP routing tables (OSPF/BGP), Zabbix host discovery, and endpoint Paris traceroute hops, Nawari constructs an authoritative Layer 2/Layer 3 topological dependency graph stored in PostgreSQL.

```
+----------------------------------------------------------------------------------------------------+
|                                    NAWARI PHASE 9 PIPELINE                                         |
|                                                                                                    |
|  [ Multi-Source Discovery ]                                                                        |
|         │                                                                                          |
|         ├─► Zabbix API           (Monitored hosts, LLD interfaces, status, alarms)                 |
|         ├─► SNMPv2c/v3 Engine    (sysDescr, ifTable, ifXTable, ipAddrTable, ipRouteTable)           |
|         ├─► LLDP Engine          (IEEE 802.1AB lldpRemTable, chassis/port IDs)                     |
|         ├─► CDP Engine           (CISCO-CDP-MIB cdpCacheTable, device capabilities)                |
|         ├─► Forwarding Tables    (BRIDGE-MIB dot1dTpFdbTable, MAC-to-port mapping)                 |
|         └─► Endpoint Traces      (Stage 7C Paris traceroute ingress hops)                          |
|                     │                                                                              |
|                     ▼                                                                              |
|  [ 9A/9B: Normalization & Identity Resolver ]                                                      |
|         │  - Resolves Chassis MAC, Serial Number, Management IP, FQDN to canonical UUID            |
|         │  - Assigns multi-source evidentiary confidence (Confirmed vs Inferred vs Unknown)        |
|         ▼                                                                                          |
|  [ 9C: Topology Graph Engine (PostgreSQL) ]                                                        |
|         │  - Layer 2 Switching Topology (Trunks, Access Ports, LAGs, VLANs)                        |
|         │  - Layer 3 Routing Topology (Subnets, Gateways, OSPF Areas, BGP ASNs)                    |
|         ▼                                                                                          |
|  [ 9D: Service Dependency Engine ]                                                                 |
|         │  - Maps Device/Interface -> Network Path -> Endpoint -> Telephony/App -> Business Service |
|         │  - Computes blast radius and single points of failure (SPOF)                             |
|         ▼                                                                                          |
|  [ 9E: Network Change Detector ]                                                                   |
|         │  - Snapshot diffing (T0 -> T1): Neighbour lost, uplink flap, route divergence           |
|         │  - Causal timeline integration with incident correlator                                  |
|         ▼                                                                                          |
|  [ 9F: Visual Graph & Assurance Integration ]                                                      |
|            - Node Graph / Cytoscape API contracts (`/api/v1/topology/...`)                         |
|            - Cross-Domain Assurance Correlator topology path verification                          |
+----------------------------------------------------------------------------------------------------+
```

---

## 2. Core Architectural Principles & Invariants

### Invariant 1: PostgreSQL as Canonical Source of Truth (Zero External Graph DB)
* Do **not** introduce Neo4j, ArangoDB, or dedicated graph databases.
* The production VM (`mon-grafana01`) is constrained to **2 vCPUs and 7.8 GiB RAM**. Adding a Java-based graph database would violate memory budgets and create operational complexity.
* Topology is stored natively in PostgreSQL using relational adjacency models (`devices`, `interfaces`, `links`, `dependencies`) with recursive common table expressions (`WITH RECURSIVE`) and GIN/GiST indices for fast path traversal ($< 15\text{ ms}$ for 5-hop subgraphs).

### Invariant 2: Strict Read-Only Infrastructure Discovery
* Nawari performs strictly **read-only SNMP GET / GETNEXT / GETBULK** operations and Zabbix API queries.
* Zero SNMP SET operations or CLI SSH push commands are permitted.
* Network discovery must never alter device state, reload interfaces, or modify routing tables.

### Invariant 3: Multi-Source Evidentiary Confidence Standards
* Relationships must never be assumed as absolute facts without validating the protocol source:
  1. **`CONFIRMED` ($\ge 0.95$ confidence):** Direct mutual protocol handshake, such as IEEE 802.1AB LLDP or Cisco CDP where both peer interface names and chassis IDs match reciprocally.
  2. **`PROBABLE` ($0.75 - 0.90$ confidence):** IP routing next-hop adjacency (OSPF full / BGP established) or bridge forwarding table (FDB) MAC address observed exclusively on an access port.
  3. **`INFERRED` ($0.50 - 0.74$ confidence):** ARP cache correlation or traceroute TTL sequence where intermediate devices suppress Layer 2 identity.
  4. **`UNKNOWN / UNVERIFIED` ($< 0.50$ confidence):** Discovered IP with unresolved MAC/LLDP; displayed with dashed edges on topology maps.

### Invariant 4: Non-Volatile Canonical Device Identity
* Hostnames change, IP addresses are reassigned by DHCP/IPAM, and SNMP sysNames are frequently misconfigured.
* Nawari establishes a canonical device UUID through a deterministic priority cascade:
  $$\text{Chassis MAC Address} \succ \text{Hardware Serial Number} \succ \text{Zabbix Host ID} \succ \text{Management IP}$$

### Invariant 5: Preservation of Existing Baseline & Sentra Boundary
* Work exclusively in `nawari/`. The `sentra/` repository remains 100% clean and untouched.
* All existing 188 tests across Phases 1–8 must remain passing with zero regressions.

---

## 3. Detailed Topology Data Models (PostgreSQL Schema)

The relational schema resides in the Nawari application schema within PostgreSQL, isolated from Zabbix's internal database tables.

```
                              +-----------------------+
                              |        sites          |
                              +-----------------------+
                                          │ 1
                                          │
                                          │ *
+-----------------------+ 1     * +-----------------------+
|  service_dependencies |────────►|        devices        |
+-----------------------+         +-----------------------+
                                          │ 1
                                          │
                                          │ *
                                  +-----------------------+ 1       * +-----------------------+
                                  |      interfaces       |──────────►|     ip_addresses      |
                                  +-----------------------+           +-----------------------+
                                    │ 1                 │ 1
               source_interface_id  │                   │ target_interface_id
                                    ▼ *                 ▼ *
                                  +-----------------------+
                                  |     layer2_links      |
                                  +-----------------------+
```

### 3.1 `devices` Table
Represents physical switches, routers, firewalls, SBCs, PBXs, and servers.

```sql
CREATE TABLE topology_devices (
    device_id           VARCHAR(64) PRIMARY KEY,      -- Deterministic UUID: dev-{sha256(chassis_mac or serial)[:16]}
    zabbix_host_id      BIGINT UNIQUE,                -- Foreign key / reference to Zabbix hosts table
    canonical_name      VARCHAR(255) NOT NULL,        -- Resolvable FQDN or sanitized sysName
    management_ip       INET NOT NULL,                -- Primary management IPv4/IPv6 address
    sys_object_id       VARCHAR(128),                 -- SNMP MIB-II sysObjectID (e.g. .1.3.6.1.4.1.9.1.516)
    vendor              VARCHAR(64) NOT NULL,         -- Cisco, Avaya, Juniper, Linux, Fortinet, Arista
    model               VARCHAR(128),                 -- Catalyst 3850, SBCE 10.1, SRX345
    device_type         VARCHAR(32) NOT NULL,         -- CORE_ROUTER, DIST_SWITCH, ACCESS_SWITCH, SBC, FIREWALL, PBX, SERVER
    chassis_mac         MACADDR,                      -- Base chassis MAC from dot1dBaseBridgeAddress
    serial_number       VARCHAR(128),                 -- EntPhysicalSerialNum
    os_version          VARCHAR(128),                 -- Software release version
    site_id             VARCHAR(64) NOT NULL,         -- Site identifier (e.g. NBO-HQ, MBA-AIRPORT, KIS-BRANCH)
    is_managed          BOOLEAN DEFAULT TRUE,
    confidence_score    NUMERIC(3, 2) DEFAULT 1.00,   -- 0.00 to 1.00
    first_seen          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_discovered     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_topo_devices_site ON topology_devices(site_id);
CREATE INDEX idx_topo_devices_mgmt_ip ON topology_devices(management_ip);
CREATE INDEX idx_topo_devices_type ON topology_devices(device_type);
```

### 3.2 `interfaces` Table
Represents physical ports, logical VLAN interfaces (SVIs), port-channels (LAGs), and sub-interfaces.

```sql
CREATE TABLE topology_interfaces (
    interface_id        VARCHAR(64) PRIMARY KEY,      -- if-{device_id}-{if_index}
    device_id           VARCHAR(64) NOT NULL REFERENCES topology_devices(device_id) ON DELETE CASCADE,
    if_index            INTEGER NOT NULL,             -- SNMP IF-MIB ifIndex
    if_name             VARCHAR(128) NOT NULL,        -- e.g. GigabitEthernet1/0/1, Port-channel1, Vlan10
    if_descr            TEXT,                         -- Configured interface description / alias (ifAlias)
    if_type             INTEGER NOT NULL,             -- IANA ifType (6=ethernetCsmacd, 53=propVirtual, 161=ieee8023adLag)
    mac_address         MACADDR,                      -- Physical interface MAC address
    speed_bps           BIGINT,                       -- Negotiated link speed in bits/sec (from ifHighSpeed)
    admin_status        SMALLINT NOT NULL,            -- 1=UP, 2=DOWN, 3=TESTING
    oper_status         SMALLINT NOT NULL,            -- 1=UP, 2=DOWN, 3=TESTING, 4=UNKNOWN, 5=DORMANT, 6=NOT_PRESENT, 7=LOWER_LAYER_DOWN
    mtu                 INTEGER,                      -- Maximum Transmission Unit
    is_uplink           BOOLEAN DEFAULT FALSE,        -- True if identified as carrying traffic toward network core
    is_trunk            BOOLEAN DEFAULT FALSE,        -- True if carrying multiple 802.1Q tagged VLANs
    native_vlan         INTEGER DEFAULT 1,            -- Native VLAN ID
    tagged_vlans        INTEGER[] DEFAULT '{}',       -- Array of permitted VLAN IDs
    lag_master_id       VARCHAR(64),                  -- References parent port-channel interface_id if aggregated
    last_change         TIMESTAMPTZ,                  -- Timestamp of last operStatus transition
    last_discovered     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (device_id, if_index)
);
CREATE INDEX idx_topo_if_device ON topology_interfaces(device_id);
CREATE INDEX idx_topo_if_mac ON topology_interfaces(mac_address);
CREATE INDEX idx_topo_if_oper ON topology_interfaces(oper_status);
```

### 3.3 `layer2_links` Table
Represents confirmed or inferred point-to-point Layer 2 adjacency between two interfaces.

```sql
CREATE TABLE topology_layer2_links (
    link_id                 VARCHAR(64) PRIMARY KEY,      -- link-{src_if_id}-{dst_if_id}
    source_interface_id     VARCHAR(64) NOT NULL REFERENCES topology_interfaces(interface_id) ON DELETE CASCADE,
    target_interface_id     VARCHAR(64) NOT NULL REFERENCES topology_interfaces(interface_id) ON DELETE CASCADE,
    discovery_protocol      VARCHAR(32) NOT NULL,         -- LLDP, CDP, BRIDGE_FDB, MANUAL_CONFIG
    link_type               VARCHAR(32) NOT NULL,         -- ACCESS, TRUNK, PORT_CHANNEL_MEMBER, CROSS_CONNECT
    is_bidirectional        BOOLEAN DEFAULT TRUE,
    confidence              NUMERIC(3, 2) NOT NULL,       -- 0.95 for LLDP/CDP, 0.75 for FDB inference
    evidence_metadata       JSONB DEFAULT '{}',           -- Raw neighbour record (remote chassis_id, port_id)
    status                  VARCHAR(16) NOT NULL DEFAULT 'ACTIVE', -- ACTIVE, DEGRADED, STALE, DECOMMISSIONED
    first_detected          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_verified           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (source_interface_id <> target_interface_id)
);
CREATE INDEX idx_topo_l2_src ON topology_layer2_links(source_interface_id);
CREATE INDEX idx_topo_l2_dst ON topology_layer2_links(target_interface_id);
CREATE INDEX idx_topo_l2_status ON topology_layer2_links(status);
```

### 3.4 `layer3_routes` & `routing_adjacencies` Tables
Captures IP subnet ownership, default gateways, and dynamic routing peering (OSPF/BGP).

```sql
CREATE TABLE topology_subnets (
    subnet_id           VARCHAR(64) PRIMARY KEY,      -- sub-{network_cidr}
    network_cidr        CIDR NOT NULL UNIQUE,         -- e.g. 10.100.20.0/24
    vlan_id             INTEGER,
    gateway_ip          INET,                         -- First-hop gateway IP
    site_id             VARCHAR(64) NOT NULL,
    description         VARCHAR(255)
);

CREATE TABLE topology_routing_adjacencies (
    adjacency_id        VARCHAR(64) PRIMARY KEY,
    local_device_id     VARCHAR(64) NOT NULL REFERENCES topology_devices(device_id) ON DELETE CASCADE,
    remote_device_id    VARCHAR(64) REFERENCES topology_devices(device_id) ON DELETE SET NULL,
    protocol            VARCHAR(16) NOT NULL,         -- OSPF, BGP, STATIC, CONNECTED
    local_ip            INET NOT NULL,
    remote_ip           INET NOT NULL,
    state               VARCHAR(32) NOT NULL,         -- OSPF: FULL, 2WAY, ATTEMPT; BGP: ESTABLISHED, ACTIVE, IDLE
    area_or_asn         VARCHAR(32),                  -- OSPF Area ID or BGP Autonomous System Number
    metric              INTEGER,
    last_flap           TIMESTAMPTZ,
    last_verified       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_topo_adj_local ON topology_routing_adjacencies(local_device_id);
CREATE INDEX idx_topo_adj_remote ON topology_routing_adjacencies(remote_device_id);
```

### 3.5 `service_dependencies` Table
Binds higher-level voice, network, and application services to their underlying physical assets.

```sql
CREATE TABLE topology_service_dependencies (
    dependency_id       VARCHAR(64) PRIMARY KEY,      -- dep-{service_id}-{target_id}
    service_id          VARCHAR(64) NOT NULL,         -- e.g. voice-synthetic-probe, corp-dns, avaya-sbce-trunk
    dependent_type      VARCHAR(32) NOT NULL,         -- DEVICE, INTERFACE, SUBNET, ROUTE, PATH
    dependent_id        VARCHAR(64) NOT NULL,         -- References device_id, interface_id, or subnet_id
    criticality         VARCHAR(16) NOT NULL,         -- CRITICAL, REDUNDANT, OPTIONAL
    failure_impact      VARCHAR(32) NOT NULL,         -- TOTAL_OUTAGE, DEGRADATION, FAILOVER_TRIGGERED
    impact_weight       NUMERIC(3, 2) DEFAULT 1.00,   -- Multiplier for health score calculation
    notes               TEXT
);
CREATE INDEX idx_topo_dep_service ON topology_service_dependencies(service_id);
CREATE INDEX idx_topo_dep_target ON topology_service_dependencies(dependent_id);
```

### 3.6 `topology_changes` Table
Chronological log of structural network modifications used for causal timeline analysis.

```sql
CREATE TABLE topology_changes (
    change_id           BIGSERIAL PRIMARY KEY,
    timestamp           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    change_type         VARCHAR(32) NOT NULL,         -- DEVICE_ADDED, DEVICE_REMOVED, LINK_UP, LINK_DOWN,
                                                      -- NEIGHBOUR_LOST, NEIGHBOUR_ADDED, ROUTE_CHANGED, SPEED_CHANGED
    target_entity_type  VARCHAR(32) NOT NULL,         -- DEVICE, INTERFACE, LINK, ADJACENCY
    target_entity_id    VARCHAR(64) NOT NULL,
    before_state        JSONB,
    after_state         JSONB,
    detected_by         VARCHAR(32) NOT NULL,         -- SNMP_DISCOVERY, LLDP_POLLER, ZABBIX_WEBHOOK
    correlated_problem_id BIGINT                      -- Zabbix eventid if correlated
);
CREATE INDEX idx_topo_changes_time ON topology_changes(timestamp DESC);
CREATE INDEX idx_topo_changes_target ON topology_changes(target_entity_type, target_entity_id);
```

---

## 4. Multi-Source Discovery Engine Architecture

Discovery runs as an orchestrated, asynchronous background service within the Nawari platform container, scheduled with bounded concurrency to prevent CPU saturation on the monitoring host.

### 4.1 Discovery Sources & Ingestion Mechanics

| Discovery Source | Protocol / Standard | OID / API Target | Ingested Metadata | Confidence |
| :--- | :--- | :--- | :--- | :---: |
| **Zabbix API** | JSON-RPC over HTTP | `host.get`, `item.get`, `trigger.get` | Inventory hosts, active interfaces, current operational states, active problem alarms. | 0.90 |
| **LLDP Discovery** | SNMPv2c/SNMPv3 | `1.0.8802.1.1.2` (`LLDP-MIB`) | Remote chassis ID, remote port ID, remote system name, port descriptions, capabilities. | **0.98** |
| **CDP Discovery** | SNMPv2c/SNMPv3 | `1.3.6.1.4.1.9.9.23` (`CISCO-CDP-MIB`) | Cisco neighbour device IDs, remote port names, device platform/model, native VLAN. | **0.95** |
| **Interface Table** | SNMPv2c/SNMPv3 | `1.3.6.1.2.1.31.1.1` (`IF-MIB` / `ifXTable`) | Exact interface names, aliases (`ifAlias`), 64-bit octet counters, duplex, speed. | 0.95 |
| **Bridge / FDB** | SNMPv2c/SNMPv3 | `1.3.6.1.2.1.17.4.3` (`dot1dTpFdbTable`) | MAC address forwarding table mapping client and endpoint MACs to physical switch ports. | 0.75 |
| **IP Route Table** | SNMPv2c/SNMPv3 | `1.3.6.1.2.1.4.24.4` (`ipCidrRouteTable`) | Routing next hops, destination CIDRs, interface indices, routing protocol origins. | 0.85 |
| **OSPF / BGP** | SNMPv2c/SNMPv3 | `1.3.6.1.2.1.14.10` / `1.3.6.1.2.1.15.3` | Router adjacency states, OSPF neighbour IDs, BGP peer states (Established, Idle). | 0.92 |
| **Endpoint Traces** | HTTPS Ingestion Gateway | Stage 7C Paris Traceroute Hops | IP addresses of first-hop, transit, and boundary hops correlated to switch interfaces. | 0.80 |

### 4.2 LLDP / CDP Discovery Protocol Traversal Algorithm

```
                    +------------------------------------+
                    | Query Root / Core Seed Device(s)   |
                    +------------------------------------+
                                      │
                                      ▼
                    +------------------------------------+
                    | Fetch Local Interface Table (IF-MIB)|
                    +------------------------------------+
                                      │
                                      ▼
                    +------------------------------------+
                    | Fetch Remote Neighbours (LLDP-MIB) |
                    +------------------------------------+
                                      │
                 ┌────────────────────┴────────────────────┐
                 ▼                                         ▼
   [ Peer Chassis MAC In Inventory ]        [ Peer Chassis MAC Is New ]
                 │                                         │
                 ▼                                         ▼
   +---------------------------+             +---------------------------+
   | Correlate Local ifIndex   |             | Enqueue New Device IP     |
   | to Remote Peer ifIndex    |             | For SNMP Credentials Probe|
   +---------------------------+             +---------------------------+
                 │                                         │
                 ▼                                         ▼
   +---------------------------+             +---------------------------+
   | Upsert topology_layer2_link|             | Recursively Discover Neigh |
   | with CONFIRMED (0.98)     |             | (Max Depth = 5 Hops)      |
   +---------------------------+             +---------------------------+
```

1. **Seed Ingestion:** Discovery begins with seed devices configured in `config/topology.yaml` or imported from Zabbix host groups (`Voice Infrastructure`, `Network Devices`, `Core Switches`).
2. **Local Interface Enumeration:** Query `ifXTable` for interface speeds, names, operational statuses, and MAC addresses.
3. **Neighbour Table Sweep:** Query `lldpRemTable` (`1.0.8802.1.1.2.1.4.1`):
   * `lldpRemChassisIdSubtype` and `lldpRemChassisId`: Canonical MAC or network address of peer device.
   * `lldpRemPortId`: Remote interface identifier (e.g. `GigabitEthernet1/0/24`).
   * `lldpRemSysName`: Remote device hostname.
4. **Reciprocal Link Binding:** Query the discovered remote device. Verify that its local `lldpRemTable` confirms the connection back to the originating device and port.
   * If reciprocal: Create `topology_layer2_links` entry with `confidence = 0.98` and `status = 'ACTIVE'`.
   * If unidirectional: Create entry with `confidence = 0.85` and `status = 'DEGRADED_UNIDIRECTIONAL'`.

---

## 5. Network Dependency Mapping & Blast-Radius Engine

One of the central differentiators of Phase 9 is the **Dependency Engine**. Rather than viewing devices in isolation, it computes the directional graph from physical network infrastructure down to endpoints and enterprise services.

### 5.1 Directional Dependency Chain

$$\text{Core Router} \longrightarrow \text{Distribution Switch} \longrightarrow \text{Access Switch} \longrightarrow \text{Access Port} \longrightarrow \text{Workstation/Endpoint} \longrightarrow \text{Voice Service}$$

### 5.2 Blast-Radius Calculation (Recursive CTE)

When an interface fails or an appliance is overloaded, Nawari runs a deterministic topological blast-radius query to identify all impacted downstream assets:

```sql
WITH RECURSIVE downstream_impact AS (
    -- Anchor member: Initial failing interface or device
    SELECT 
        i.device_id,
        i.interface_id,
        i.if_name,
        1 AS hop_depth
    FROM topology_interfaces i
    WHERE i.interface_id = :failing_interface_id
    
    UNION ALL
    
    -- Recursive member: Traverse Layer 2 links down to access layer
    SELECT 
        child_if.device_id,
        child_if.interface_id,
        child_if.if_name,
        d.hop_depth + 1
    FROM downstream_impact d
    JOIN topology_layer2_links l ON l.source_interface_id = d.interface_id
    JOIN topology_interfaces child_if ON child_if.interface_id = l.target_interface_id
    WHERE d.hop_depth < 10
)
SELECT 
    di.device_id,
    dev.canonical_name,
    dev.device_type,
    dep.service_id,
    dep.criticality,
    dep.failure_impact
FROM downstream_impact di
JOIN topology_devices dev ON dev.device_id = di.device_id
LEFT JOIN topology_service_dependencies dep ON dep.dependent_id = di.device_id
GROUP BY di.device_id, dev.canonical_name, dev.device_type, dep.service_id, dep.criticality, dep.failure_impact;
```

### 5.3 Redundancy & Single Point of Failure (SPOF) Analysis
* **Redundant Path Awareness:** If a link in a Link Aggregation Group (LAG / 802.3ad) fails while peer member links remain active, Nawari classifies the failure as `REDUNDANCY_DEGRADED` rather than `SERVICE_OUTAGE`.
* **SPOF Detection:** Identifies any access switch or voice gateway connected via a single physical uplink without Spanning Tree / LACP redundancy. Flags an architectural risk warning in service assurance reports.

---

## 6. Network Change Detection Engine

The change detector compares successive discovery snapshots ($T_0 \to T_{\text{current}}$) to pinpoint infrastructure modifications that precede service incidents:

### 6.1 Detected Change Taxonomy

| Change Event Type | Detection Trigger | Operational Severity | Impact on Correlator |
| :--- | :--- | :---: | :--- |
| `NEIGHBOUR_LOST` | An active LLDP/CDP neighbour disappeared from an interface. | **HIGH** | Potential cable unplug, remote device crash, or SFP failure. |
| `NEIGHBOUR_ADDED` | A new chassis ID or port appeared on an existing switch port. | **MEDIUM** | Physical recabling, rogue switch attachment, or topology reconvergence. |
| `UPLINK_FLAP` | An interface marked `is_uplink = TRUE` transitioned states $> 3$ times in 5 min. | **HIGH** | Spanning Tree recalculation, micro-flaps causing RTP voice packet drops. |
| `SPEED_DEGRADATION` | Link speed dropped (e.g. 10 Gbps $\to$ 1 Gbps, or 1 Gbps $\to$ 100 Mbps). | **WARNING** | Duplex mismatch, dirty optical fiber, or auto-negotiation failure. |
| `ROUTE_DIVERGENCE` | Next-hop IP for corporate core subnets changed in routing table. | **MEDIUM** | BGP/OSPF route shift; explains sudden latency jumps on endpoint traces. |
| `VLAN_MEMBERSHIP_CHANGE`| Permitted VLAN IDs modified on an operational trunk interface. | **HIGH** | Accidental VLAN pruning; causes sudden silent drop of voice traffic. |

### 6.2 Causal Timeline Correlator Integration
When a synthetic call fails or an endpoint reports high gateway latency, the Correlator inspects `topology_changes` for events that occurred within the **preceding 15 minutes**:
$$\Delta t = t_{\text{incident}} - t_{\text{topology\_change}} \le 900\text{ seconds}$$
If a `NEIGHBOUR_LOST` or `UPLINK_FLAP` event is found on an upstream dependency of the failing service, the incident confidence is automatically elevated to **`CONFIRMED`** with the physical change explicitly cited as the primary root cause.

---

## 7. Topology Visualisation & REST API Contracts

### 7.1 Visual Architecture: Grafana Native & Cytoscape.js Compatible
The visualisation layer exposes standard Node Graph models consumed by:
1. **Grafana Node Graph Panel:** Native Grafana visualization displaying nodes, connections, health colors, and directional throughput.
2. **Interactive Topology UI (Cytoscape.js):** Dynamic zoomable network map supporting hierarchical layout (Core $\to$ Distribution $\to$ Access $\to$ Endpoints).

### 7.2 REST API Specification (`/api/v1/topology/`)

#### `GET /api/v1/topology/graph`
Returns the complete or filtered node-link topological graph.
* **Query Parameters:**
  * `site_id` (optional): Filter to a specific airport or campus site (e.g. `MBA-AIRPORT`).
  * `device_type` (optional): Filter by device role (`CORE_ROUTER`, `ACCESS_SWITCH`, `SBC`).
  * `depth` (optional): Maximum traversal depth from root (default: 5).
  * `service_id` (optional): Return only subgraphs supporting a specific service.
* **Response Contract:**
```json
{
  "nodes": [
    {
      "id": "dev-001a2b3c4d5e",
      "title": "sw-core-01.nbo.kenya-airways.com",
      "subTitle": "Cisco Catalyst 9500 (Core Switch)",
      "mainStat": "100% OK",
      "secondaryStat": "0 Problems",
      "color": "green",
      "icon": "server",
      "metadata": {
        "management_ip": "10.100.1.1",
        "vendor": "Cisco",
        "site_id": "NBO-HQ",
        "confidence": 0.98
      }
    },
    {
      "id": "dev-001a2b3c4d99",
      "title": "sbce-edge-01.nbo.kenya-airways.com",
      "subTitle": "Avaya SBCE 10.1 (Voice SBC)",
      "mainStat": "Active",
      "secondaryStat": "Port 5061 OK",
      "color": "green",
      "icon": "phone",
      "metadata": {
        "management_ip": "10.100.10.50",
        "vendor": "Avaya",
        "site_id": "NBO-HQ",
        "confidence": 1.00
      }
    }
  ],
  "edges": [
    {
      "id": "link-dev01-eth1-dev99-eth0",
      "source": "dev-001a2b3c4d5e",
      "target": "dev-001a2b3c4d99",
      "mainStat": "10 Gbps",
      "secondaryStat": "Trunk (VLAN 10,20,50)",
      "color": "green",
      "metadata": {
        "source_interface": "TenGigabitEthernet1/0/1",
        "target_interface": "eth0",
        "discovery_protocol": "LLDP",
        "confidence": 0.98,
        "is_lag": false
      }
    }
  ]
}
```

#### `GET /api/v1/topology/devices/{id}/dependencies`
Returns the upstream and downstream dependency tree for a specific device, including impacted services.

#### `GET /api/v1/topology/path?source={ip}&destination={ip}`
Reconstructs the multi-layer forwarding path between two endpoints, detailing traversed switches, ports, VLANs, routers, and expected round-trip time.

#### `GET /api/v1/topology/changes?since={timestamp}`
Returns chronological network changes with before/after state diffs for auditability and incident root-cause confirmation.

---

## 8. Integration with Nawari Cross-Domain Assurance Engine

Phase 9 feeds directly into `services/assurance/correlator.py`:

```python
# Conceptual Integration in CrossDomainCorrelator
class CrossDomainCorrelator:
    def __init__(self, zabbix_client=None, topology_engine=None):
        self.zabbix_client = zabbix_client
        self.topology_engine = topology_engine

    def correlate(self, voice_event=None, endpoint_reports=None, ...):
        # 1. Standard telemetry extraction
        ...
        # 2. Topology-Aware Dependency Resolution
        if self.topology_engine and endpoint_reports:
            for rep in endpoint_reports:
                # Resolve physical switch port where endpoint connects
                client_mac = rep.local_network.mac_address
                access_link = self.topology_engine.find_access_port_by_mac(client_mac)
                if access_link:
                    # Check if access switch port or upstream trunk is currently degraded
                    upstream_chain = self.topology_engine.get_upstream_path(access_link.device_id)
                    for dev, iface in upstream_chain:
                        if iface.oper_status != 1:  # Down
                            # We have DETERMINISTIC proof of link outage causing endpoint loss!
                            hypotheses.append(
                                IncidentHypothesis(
                                    status=HypothesisStatus.CONFIRMED,
                                    root_cause_domain=RootCauseDomain.NETWORK_LINK,
                                    title=f"Physical Uplink Failure on {dev.canonical_name} ({iface.if_name})",
                                    confidence=0.98,
                                    evidence=[...]
                                )
                            )
```

---

## 9. Modular Implementation Structure & Directory Layout

To maintain strict modularity, Phase 9 code is contained within `services/topology/` and `tests/`:

```
nawari/
├── services/
│   └── topology/
│       ├── __init__.py
│       ├── discovery/
│       │   ├── __init__.py
│       │   ├── snmp_engine.py         # Async SNMPv2c/v3 MIB-II, IF-MIB collector
│       │   ├── lldp_collector.py      # IEEE 802.1AB LLDP parser and collector
│       │   ├── cdp_collector.py       # Cisco CDP collector
│       │   ├── fdb_collector.py       # Bridge FDB MAC forwarding table collector
│       │   ├── route_collector.py     # IP routing table and OSPF/BGP collector
│       │   └── zabbix_collector.py    # Zabbix host/interface discovery integration
│       ├── models/
│       │   ├── __init__.py
│       │   ├── device.py              # Device dataclasses and enums
│       │   ├── interface.py           # Interface, VLAN, and LAG dataclasses
│       │   ├── link.py                # Layer 2/Layer 3 link models
│       │   ├── dependency.py          # Service dependency models
│       │   └── change.py              # Topology change event dataclasses
│       ├── engine/
│       │   ├── __init__.py
│       │   ├── identity_resolver.py   # Deterministic UUID and MAC matching
│       │   ├── graph_builder.py       # Constructs in-memory and PostgreSQL graph
│       │   ├── path_tracer.py         # L2/L3 path traversal and shortest-path
│       │   ├── blast_radius.py        # Failure impact analysis engine
│       │   ├── change_detector.py     # Snapshot diffing and change detection
│       │   └── confidence.py          # Evidentiary scoring and calibration
│       └── api/
│           ├── __init__.py
│           ├── router.py              # FastAPI router mount point
│           ├── devices.py             # Device inventory endpoints
│           ├── topology.py            # Node Graph / Cytoscape endpoints
│           └── changes.py             # Network change timeline endpoints
├── docker/
│   ├── postgresql/
│   │   └── initdb/
│   │       └── 05-topology-schema.sql # PostgreSQL schema definitions
│   └── grafana/
│       └── dashboards/
│           └── network_topology.json  # Native Grafana Node Graph dashboard
└── tests/
    ├── unit/
    │   ├── test_snmp_topology_parsers.py
    │   ├── test_lldp_collector.py
    │   ├── test_topology_identity_resolver.py
    │   ├── test_graph_builder.py
    │   ├── test_blast_radius_engine.py
    │   └── test_topology_change_detector.py
    └── integration/
        ├── test_topology_zabbix_integration.py
        ├── test_topology_snmp_discovery.py
        └── test_topology_assurance_correlation.py
```

---

## 10. Testable Implementation Roadmap & Stage Sequencing

Phase 9 is structured into six discrete, test-driven stages:

| Stage | Name | Core Engineering Scope | Validation Deliverable |
| :---: | :--- | :--- | :--- |
| **9A** | **Data Models & Schema** | PostgreSQL schema (`05-topology-schema.sql`), Python dataclasses (`Device`, `Interface`, `Link`, `Dependency`), migrations, and CRUD operations. | Unit tests validating data models, serialization, and PostgreSQL schema constraints. |
| **9B** | **Multi-Source Discovery Engine** | Async SNMP MIB-II, `IF-MIB`, and `LLDP-MIB` collectors, Zabbix host discovery integration, rate-limiting poller. | Unit tests against mock SNMP responses and synthetic LLDP payloads. |
| **9C** | **Layer 2/3 Graph Builder** | Canonical identity resolution, reciprocal link binding, confidence calibration, OSPF/BGP adjacency extraction. | Graph construction tests on multi-vendor synthetic topologies (Campus, Spine-Leaf). |
| **9D** | **Dependency & Blast Radius** | Service-to-infrastructure dependency bindings, recursive blast-radius traversal, SPOF identification. | Failure simulation tests verifying correct identification of impacted voice services. |
| **9E** | **Network Change Detector** | Topology snapshot diffing, change classification, chronological timeline generation. | Diff engine tests verifying detection of uplink flaps, neighbour loss, and route divergence. |
| **9F** | **Visual APIs & Assurance Link** | REST API (`/api/v1/topology/...`), Grafana Node Graph provisioning, integration into `services/assurance/correlator.py`. | Integration tests validating Grafana loading, API contracts, and topology-backed incident resolution. |

---

## 11. Acceptance Criteria for Phase 9 Completion

Phase 9 will be accepted when:
1. **Schema & Models:** PostgreSQL schema cleanly provisions without errors and persists device, interface, link, and dependency records.
2. **Discovery Verification:** SNMP and LLDP engines successfully discover and reconstruct topology from mock network devices (`nawari-mock-snmp`) and Zabbix inventory.
3. **Graph Integrity:** Reciprocal Layer 2 connections achieve $\ge 0.95$ confidence; inferred links are properly tagged with evidentiary metadata.
4. **Blast Radius Accuracy:** Simulating an uplink failure accurately returns the exact list of downstream access switches, endpoints, and dependent voice services.
5. **Change Detection:** Toggling an interface state generates a structured `topology_changes` event within 60 seconds.
6. **Assurance Correlator Enhancement:** The Correlator cites physical topology links when explaining network transit and gateway failures.
7. **Regression Guarantee:** All existing 188 unit and integration tests continue to pass 100% with zero regressions.
8. **Working Tree Cleanliness:** Nawari git working tree is clean; Sentra remains untouched.
