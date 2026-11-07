-- ==============================================================================
-- NAWARI — Enterprise Network & Communications Observability Platform
-- Phase 9: Network Intelligence, Dynamic Topology Mapping & Dependency Schema
-- File: docker/postgresql/initdb/05-topology-schema.sql
-- ==============================================================================

-- 1. Devices Table
CREATE TABLE IF NOT EXISTS topology_devices (
    device_id           VARCHAR(64) PRIMARY KEY,      -- Deterministic UUID: dev-{sha256(chassis_mac or serial)[:16]}
    zabbix_host_id      BIGINT UNIQUE,                -- Reference to Zabbix hosts table
    canonical_name      VARCHAR(255) NOT NULL,        -- Resolvable FQDN or sanitized sysName
    management_ip       INET NOT NULL,                -- Primary management IPv4/IPv6 address
    sys_object_id       VARCHAR(128),                 -- SNMP MIB-II sysObjectID (e.g. .1.3.6.1.4.1.9.1.516)
    vendor              VARCHAR(64) NOT NULL,         -- Cisco, Avaya, Juniper, Linux, Fortinet, Arista
    model               VARCHAR(128),                 -- Catalyst 9500, SBCE 8.1, SRX345
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

CREATE INDEX IF NOT EXISTS idx_topo_devices_site ON topology_devices(site_id);
CREATE INDEX IF NOT EXISTS idx_topo_devices_mgmt_ip ON topology_devices(management_ip);
CREATE INDEX IF NOT EXISTS idx_topo_devices_type ON topology_devices(device_type);

-- 2. Interfaces Table
CREATE TABLE IF NOT EXISTS topology_interfaces (
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

CREATE INDEX IF NOT EXISTS idx_topo_if_device ON topology_interfaces(device_id);
CREATE INDEX IF NOT EXISTS idx_topo_if_mac ON topology_interfaces(mac_address);
CREATE INDEX IF NOT EXISTS idx_topo_if_oper ON topology_interfaces(oper_status);

-- 3. Layer 2 Links Table
CREATE TABLE IF NOT EXISTS topology_layer2_links (
    link_id                 VARCHAR(64) PRIMARY KEY,      -- link-{src_if_id}-{dst_if_id}
    source_interface_id     VARCHAR(64) NOT NULL REFERENCES topology_interfaces(interface_id) ON DELETE CASCADE,
    target_interface_id     VARCHAR(64) NOT NULL REFERENCES topology_interfaces(interface_id) ON DELETE CASCADE,
    discovery_protocol      VARCHAR(32) NOT NULL,         -- LLDP, CDP, BRIDGE_FDB, MANUAL_CONFIG
    link_type               VARCHAR(32) NOT NULL,         -- ACCESS, TRUNK, PORT_CHANNEL_MEMBER, CROSS_CONNECT
    is_bidirectional        BOOLEAN DEFAULT TRUE,
    confidence              NUMERIC(3, 2) NOT NULL,       -- 0.95 for LLDP/CDP, 0.75 for FDB inference
    evidence_metadata       JSONB DEFAULT '{}',           -- Raw neighbour record (remote chassis_id, port_id)
    status                  VARCHAR(32) NOT NULL DEFAULT 'ACTIVE', -- ACTIVE, DEGRADED, STALE, DECOMMISSIONED
    first_detected          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_verified           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (source_interface_id <> target_interface_id)
);

CREATE INDEX IF NOT EXISTS idx_topo_l2_src ON topology_layer2_links(source_interface_id);
CREATE INDEX IF NOT EXISTS idx_topo_l2_dst ON topology_layer2_links(target_interface_id);
CREATE INDEX IF NOT EXISTS idx_topo_l2_status ON topology_layer2_links(status);

-- 4. Subnets Table
CREATE TABLE IF NOT EXISTS topology_subnets (
    subnet_id           VARCHAR(64) PRIMARY KEY,      -- sub-{network_cidr}
    network_cidr        CIDR NOT NULL UNIQUE,         -- e.g. 10.100.20.0/24
    vlan_id             INTEGER,
    gateway_ip          INET,                         -- First-hop gateway IP
    site_id             VARCHAR(64) NOT NULL,
    description         VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS idx_topo_subnets_site ON topology_subnets(site_id);

-- 5. Routing Adjacencies Table
CREATE TABLE IF NOT EXISTS topology_routing_adjacencies (
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

CREATE INDEX IF NOT EXISTS idx_topo_adj_local ON topology_routing_adjacencies(local_device_id);
CREATE INDEX IF NOT EXISTS idx_topo_adj_remote ON topology_routing_adjacencies(remote_device_id);

-- 6. Service Dependencies Table
CREATE TABLE IF NOT EXISTS topology_service_dependencies (
    dependency_id       VARCHAR(64) PRIMARY KEY,      -- dep-{service_id}-{dependent_id}
    service_id          VARCHAR(64) NOT NULL,         -- e.g. voice-synthetic-probe, corp-dns, avaya-sbce-trunk
    dependent_type      VARCHAR(32) NOT NULL,         -- DEVICE, INTERFACE, SUBNET, ROUTE, PATH
    dependent_id        VARCHAR(64) NOT NULL,         -- References device_id, interface_id, or subnet_id
    criticality         VARCHAR(16) NOT NULL,         -- CRITICAL, REDUNDANT, OPTIONAL
    failure_impact      VARCHAR(32) NOT NULL,         -- TOTAL_OUTAGE, DEGRADATION, FAILOVER_TRIGGERED
    impact_weight       NUMERIC(3, 2) DEFAULT 1.00,   -- Multiplier for health score calculation
    notes               TEXT
);

CREATE INDEX IF NOT EXISTS idx_topo_dep_service ON topology_service_dependencies(service_id);
CREATE INDEX IF NOT EXISTS idx_topo_dep_target ON topology_service_dependencies(dependent_id);

-- 7. Topology Changes Table
CREATE TABLE IF NOT EXISTS topology_changes (
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

CREATE INDEX IF NOT EXISTS idx_topo_changes_time ON topology_changes(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_topo_changes_target ON topology_changes(target_entity_type, target_entity_id);

