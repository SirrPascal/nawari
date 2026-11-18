-- Migration 033: Device Hostname Registry & Evidence-Based Identity Resolution

ALTER TABLE network_discovery_candidates
    ADD COLUMN IF NOT EXISTS dns_hostname TEXT,
    ADD COLUMN IF NOT EXISTS verified_hostname TEXT,
    ADD COLUMN IF NOT EXISTS preferred_display_name TEXT,
    ADD COLUMN IF NOT EXISTS naming_source TEXT DEFAULT 'management_ip',
    ADD COLUMN IF NOT EXISTS discovered_aliases TEXT DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS last_validated_at DOUBLE PRECISION;

ALTER TABLE network_devices
    ADD COLUMN IF NOT EXISTS dns_hostname TEXT,
    ADD COLUMN IF NOT EXISTS verified_hostname TEXT,
    ADD COLUMN IF NOT EXISTS preferred_display_name TEXT,
    ADD COLUMN IF NOT EXISTS naming_source TEXT DEFAULT 'management_ip',
    ADD COLUMN IF NOT EXISTS discovered_aliases TEXT DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS last_validated_at DOUBLE PRECISION;
