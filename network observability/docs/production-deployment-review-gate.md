# Production deployment review gate

Status: not ready for approval because the server audit and placement decision are blocked.

The first possible mutation must be narrower than the prepared full profile unless the audit proves adequate capacity.

## Candidate bounded wave

- New versioned Nawari release directory discovered from the actual host layout.
- Dedicated PostgreSQL database/roles outside the Zabbix schema.
- Nawari API and worker behind an existing or approved TLS reverse proxy.
- No Netdata Parent restart until its current configuration, identity and backup are captured.
- No Kafka/Mimir/Loki/Alloy deployment in this wave unless separately approved after capacity review.

## Required review evidence

- Sanitized read-only audit and existing service baseline.
- Exact release archive SHA-256, OCI image digest and target architecture.
- Listener/firewall delta; internal services remain unexposed.
- PostgreSQL fresh/upgrade migration results and isolated restore test.
- Existing files/services affected, migration commands and abort conditions.
- Rollback or forward-repair procedure; container rollback alone does not reverse migrations.

## Abort conditions

- Unidentified existing Compose ownership or uncommitted server changes.
- Insufficient disk, memory, I/O or backup headroom.
- Missing verified backup/restore evidence.
- Port collision, TLS trust failure or regression in Zabbix, Grafana, Netdata Parent or communications/AVTEST health.
- Any requirement to disable certificate or SSH host verification.

