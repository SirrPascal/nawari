-- Rollback Migration 035: Canonical Device Identity Reconciliation

DROP TABLE IF EXISTS canonical_identity_audit_log;
DROP TABLE IF EXISTS canonical_device_identities;

DELETE FROM schema_migrations WHERE version = 35;
