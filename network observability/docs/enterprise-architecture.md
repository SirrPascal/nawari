# Nawari enterprise architecture preparation

Status: implementation preparation; source-system inventory, server deployment and enterprise acceptance pending.

Nawari correlates evidence and presents investigations. It does not become a second SNMP poller, wireless controller, firewall log lake or pager merely because those systems can be queried. Source ownership is versioned in `config/source-ownership.v1.json`; alert ownership is versioned separately and defaults new Nawari conditions to shadow mode.

## Logical flow

1. Netdata children and approved regional probes produce endpoint and comparable synthetic observations.
2. Zabbix, SolarWinds, wireless controllers and FortiAnalyzer remain authoritative for their assigned families and expose selected evidence through supported, least-privilege interfaces.
3. Adapters normalize stable source identifiers, observation and receipt time, units, freshness, outcome and a link or opaque reference to the original evidence.
4. PostgreSQL holds mappings, validity intervals, service definitions, deterministic incident state and evidence references.
5. Mimir and Loki retain accepted metrics and redacted operational copies. Their presence never upgrades missing source evidence to healthy.
6. Grafana and the Nawari device investigation page enforce server-side tenant, region and role scope.
7. Hosted AI is optional and receives only scoped evidence after deterministic correlation; its output is an attributed hypothesis, never a confirmed diagnosis or an automatic device action.

## Adapter contract

Every external adapter must be pull-bounded or use an approved forwarder, page results, overlap its cursor safely, deduplicate using source identity plus observation time, and persist query/schema version. Direct database access is forbidden by default. An adapter must emit `unsupported`, `permission_denied`, `collection_error`, `stale` or `missing` instead of inventing values.

Required normalized fields are tenant, source, source object identifier, stable Nawari entity identifier, site, routing domain or VRF, observed time, received time, timestamp quality, unit/semantics where applicable, collection outcome, freshness, source schema/query version and an evidence reference. Secrets, packet content, full URLs and unrestricted employee identifiers are excluded.

## Topology semantics

Migration `003_enterprise_topology.sql` stores entities, external references, integration cursors and time-valid relationships. Relationship classes remain distinct: measured Layer 3 path, discovered Layer 2 topology, controller association, configured dependency and inferred relationship. Every relationship includes source provenance, first/last observation, validity interval and confidence. IP address alone is never an authoritative identity.

## Regional design

A regional collector is required when local breakout, routing, DNS/proxy behavior, residency or troubleshooting comparisons materially differ. Regional queues are byte- and age-bounded and preserve original expiry during replay. Residency-restricted sites may keep raw data locally and export approved aggregates or incident metadata. A central probe is never presented as an employee experience measurement for another country.

## Security boundaries

The initial transport policy is TLS 1.3 preferred with TLS 1.2 fallback, mandatory certificate and hostname verification, TLS 1.0/1.1 disabled, and 0-RTT disabled for authenticated or state-changing traffic. Netdata's streaming protocol is TLS over its own TCP protocol and must not be placed behind an HTTP reverse proxy. TLS 1.3-only is promoted per connection after macOS, Windows, Parent, proxy, database and service clients record successful negotiation.

SSO/MFA, operator roles, region/tenant scope and evidence permissions must be enforced by the API. Grafana folders and frontend navigation are not authorization controls. Every administrative or evidence-access action creates a scoped audit record.

## HA, recovery and external monitoring

The first deployment may be an explicitly accepted single-host pilot, but it is not host-level HA. Production placement requires measured capacity, an availability objective, RPO/RTO, PostgreSQL restore proof, object/Kafka/Parent recovery, regional queue survival, certificate recovery, and reverse-proxy/DNS failover. At least one check outside the central host must test the operator UI, API, certificate and Parent reachability.

## Acceptance status vocabulary

Every test is recorded as `verified`, `partially_verified`, `unsupported`, `failed` or `not_tested`. Fixtures cannot produce `verified` enterprise coverage. Expansion requires macOS and Windows, headquarters and one international site, both wireless families where deployed, legacy and newer switches, each authoritative source integration, regional comparison, stale/missing evidence, relay outage, central restart, revocation, retention/restore, authorization boundaries, and deterministic operation while AI is unavailable.
