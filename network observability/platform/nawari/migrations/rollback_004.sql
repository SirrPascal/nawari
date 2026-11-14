-- rollback_004.sql
-- Reverses Migration 004 (Endpoint & Infrastructure Identity Registry)
--
-- NON-DESTRUCTIVE FAIL-CLOSED POLICY:
-- This rollback script safeguards against accidental loss of canonical endpoint
-- identity, source mappings, network history, and conflict records.
--
-- If ANY of the identity tables contain records, the transaction immediately ABORTS
-- via a CHECK constraint violation on temporary guard table '_rollback_guard'.
--
-- OPERATOR RECOVERY & MIGRATION PROCEDURES:
-- 1. Forward Recovery (Standard):
--    Fix issues via forward schema migrations (e.g. 005_fix.sql) rather than rolling back.
-- 2. Planned Downward Migration / Archiving:
--    If rollback is required, first export or archive all identity records:
--      CREATE TABLE endpoint_registry_backup AS SELECT * FROM endpoint_registry;
--      CREATE TABLE endpoint_source_mappings_backup AS SELECT * FROM endpoint_source_mappings;
--      CREATE TABLE endpoint_network_observations_backup AS SELECT * FROM endpoint_network_observations;
--      CREATE TABLE endpoint_hostname_history_backup AS SELECT * FROM endpoint_hostname_history;
--      CREATE TABLE endpoint_identity_conflicts_backup AS SELECT * FROM endpoint_identity_conflicts;
--    Then explicitly truncate/delete the tables:
--      DELETE FROM endpoint_identity_conflicts;
--      DELETE FROM endpoint_hostname_history;
--      DELETE FROM endpoint_network_observations;
--      DELETE FROM endpoint_source_mappings;
--      DELETE FROM endpoint_registry;
--    After emptying the tables, re-run rollback_004.sql to cleanly drop tables and revert version.

-- 1. Fail-closed safeguard: abort transaction if any identity table contains data
CREATE TEMPORARY TABLE IF NOT EXISTS _rollback_guard (row_count INT CHECK (row_count = 0));
INSERT INTO _rollback_guard 
    SELECT (SELECT COUNT(*) FROM endpoint_registry)
         + (SELECT COUNT(*) FROM endpoint_source_mappings)
         + (SELECT COUNT(*) FROM endpoint_network_observations)
         + (SELECT COUNT(*) FROM endpoint_hostname_history)
         + (SELECT COUNT(*) FROM endpoint_identity_conflicts);
DROP TABLE _rollback_guard;

-- 2. Drop active indices and tables (only reached if all identity tables are empty)
DROP INDEX IF EXISTS idx_endpoint_conflicts;
DROP TABLE IF EXISTS endpoint_identity_conflicts;
DROP INDEX IF EXISTS idx_endpoint_hostname_hist;
DROP TABLE IF EXISTS endpoint_hostname_history;
DROP INDEX IF EXISTS idx_endpoint_network_ip;
DROP INDEX IF EXISTS idx_endpoint_network_obs;
DROP TABLE IF EXISTS endpoint_network_observations;
DROP INDEX IF EXISTS idx_endpoint_mappings_lookup;
DROP TABLE IF EXISTS endpoint_source_mappings;
DROP INDEX IF EXISTS idx_endpoint_registry_serial;
DROP INDEX IF EXISTS idx_endpoint_registry_hostname;
DROP INDEX IF EXISTS idx_endpoint_registry_search;
DROP TABLE IF EXISTS endpoint_registry;

-- 3. Revert schema migration version
DELETE FROM schema_migrations WHERE version = 4;
