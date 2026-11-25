-- Rollback Migration 034: Canonical Entities, HA Clusters, Sites, and Evidence States

DROP TABLE IF EXISTS canonical_entity_states;
DROP TABLE IF EXISTS canonical_device_sites;
DROP TABLE IF EXISTS canonical_ha_clusters;

DELETE FROM schema_migrations WHERE version = 34;
