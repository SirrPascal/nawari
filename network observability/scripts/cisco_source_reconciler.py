#!/usr/bin/env python3
"""Automated Continuous Cisco Syslog Source Reconciler for Nawari.

Reads newly appended raw syslog messages forwarded from SolarWinds, resolves
originating switches and interfaces with explicit attribution provenance (verified,
candidate, ambiguous, unresolved), and persists structured events into PostgreSQL.

Robustness guarantees:
- Atomic file-backed offset and inode/device tracking to handle logrotate and truncation.
- Strict 120-hour (5 days) retention enforcement in PostgreSQL canonical_telemetry_events.
- Idempotent upsert via sha256-derived event_id.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional

sys.path.insert(0, "/app")

from nawari.cisco_source_resolver import AttributionStatus, CiscoSourceResolver
from nawari.store import Store

LOG_FILE = "/data/rsyslog/solarwinds_raw.log"
CURSOR_FILE = "/data/rsyslog/.reconciler.cursor"
LOCK_FILE = "/data/rsyslog/.reconciler.lock"
RETENTION_HOURS = 120

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cisco_reconciler")


def run_reconciliation() -> None:
    db_file = os.getenv("NAWARI_DATABASE_FILE", "/run/app-secrets/database-runtime-url")
    if not os.path.exists(db_file):
        logger.error("Database secret not accessible: %s", db_file)
        return

    with open(db_file) as f:
        dsn = f.read().strip()

    store = Store(dsn, migrate=False)
    resolver = CiscoSourceResolver()
    now = time.time()

    if not os.path.exists(LOG_FILE):
        logger.info("Log file does not exist yet: %s", LOG_FILE)
        return

    # Stat the log file for inode and size tracking
    try:
        st = os.stat(LOG_FILE)
        file_size = st.st_size
        file_ino = st.st_ino
        file_dev = st.st_dev
    except OSError as e:
        logger.error("Failed to stat %s: %s", LOG_FILE, e)
        return

    # 1. Read cursor with inode/device validation
    cursor_offset = 0
    if os.path.exists(CURSOR_FILE):
        try:
            with open(CURSOR_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content.startswith("{"):
                    cursor_data = json.loads(content)
                    saved_ino = cursor_data.get("inode")
                    saved_dev = cursor_data.get("dev")
                    saved_offset = cursor_data.get("offset", 0)
                    if saved_ino == file_ino and saved_dev == file_dev:
                        cursor_offset = int(saved_offset)
                    else:
                        logger.warning(
                            "Log file inode or dev changed (saved: dev=%s, ino=%s vs current: dev=%s, ino=%s). "
                            "Log rotation detected; resetting offset to 0.",
                            saved_dev, saved_ino, file_dev, file_ino,
                        )
                        cursor_offset = 0
                else:
                    # Legacy plain-integer offset
                    cursor_offset = int(content)
        except Exception as e:
            logger.warning("Could not read cursor file: %s. Resetting to 0.", e)
            cursor_offset = 0

    if file_size < cursor_offset:
        logger.warning(
            "Log file truncated (current size %d < cursor offset %d). Resetting offset to 0.",
            file_size, cursor_offset,
        )
        cursor_offset = 0

    if file_size == cursor_offset:
        logger.debug("No new logs to process (offset=%d).", cursor_offset)
        # Even if no new logs, enforce retention prune
        _enforce_retention(store, now)
        return

    # 2. Fetch canonical devices for correlation
    with store.db.transaction() as session:
        canonical_devices = session.all(
            "SELECT canonical_id, name, management_ip, source_system, source_id, authoritative_source, trust_score FROM canonical_devices"
        )

    # 3. Read up to 2000 new lines
    new_lines: List[str] = []
    new_offset = cursor_offset
    with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
        f.seek(cursor_offset)
        for _ in range(2000):
            line = f.readline()
            if not line:
                break
            new_lines.append(line)
        new_offset = f.tell()

    if not new_lines:
        return

    logger.info(
        "Processing %d new log lines (bytes %d -> %d, inode=%d)...",
        len(new_lines), cursor_offset, new_offset, file_ino,
    )

    reconciled = 0
    with store.db.transaction() as session:
        for line in new_lines:
            line_str = line.strip()
            if not line_str:
                continue
            rec = resolver.parse_syslog(line_str)
            res = resolver.resolve_source(rec, canonical_devices=canonical_devices)

            sev_num = int(rec.cisco_severity) if rec.cisco_severity and rec.cisco_severity.isdigit() else 6
            if sev_num <= 3:
                can_sev = "critical"
            elif sev_num <= 5:
                can_sev = "warning"
            else:
                can_sev = "info"

            event_id = "evt-" + hashlib.sha256(line_str.encode("utf-8")).hexdigest()[:24]

            attrs = {
                "attribution_status": res.attribution_status,
                "originating_device": res.originating_device,
                "device_name": res.device_name,
                "management_ip": res.management_ip,
                "zabbix_hostid": res.zabbix_hostid,
                "solarwinds_nodeid": res.solarwinds_nodeid,
                "resolved_interface": res.resolved_interface,
                "cisco_facility": rec.cisco_facility,
                "cisco_severity": rec.cisco_severity,
                "cisco_mnemonic": rec.cisco_mnemonic,
                "client_mac": rec.client_mac,
                "audit_session_id": rec.audit_session_id,
                "forwarder_ip": res.forwarder_ip,
                "forwarder_system": res.forwarder_system,
                "evidence_trail": res.evidence_trail,
                "raw_message": rec.raw_message,
            }

            session.execute(
                """
                INSERT INTO canonical_telemetry_events (
                    event_id, event_timestamp, observed_timestamp, ingestion_timestamp,
                    source_system, source_id, entity_id, domain, severity, event_type,
                    message, attributes_json, is_delayed, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, FALSE, ?)
                ON CONFLICT (event_id) DO NOTHING
                """,
                (
                    event_id,
                    rec.received_timestamp,
                    rec.received_timestamp,
                    now,
                    "solarwinds_forwarded_syslog",
                    rec.sequence_number or event_id,
                    res.originating_device,
                    "network_infrastructure",
                    can_sev,
                    "cisco_syslog",
                    line_str,
                    json.dumps(attrs),
                    now,
                ),
            )
            reconciled += 1

            # Continuous candidate discovery: upsert observed switch IP into discovery registry
            if res.management_ip and "." in res.management_ip:
                cand_ip = res.management_ip
                cand_role = "candidate_access_switch"
                if cand_ip.startswith("10.20."):
                    cand_role = "candidate_core_switch"
                elif cand_ip.startswith("10.12."):
                    cand_role = "candidate_distribution_switch"
                cand_name = f"Candidate Cisco Switch ({cand_ip})"
                cand_port = res.resolved_interface or ""
                cand_event = rec.cisco_mnemonic or "MAB/DOT1X"
                cand_evidence = (
                    f"Discovered by continuous syslog reconciler; event {cand_event}; "
                    f"ICMP pending; SNMP unavailable — cause unconfirmed; SWIS pending auth"
                )
                session.execute(
                    """
                    INSERT INTO network_discovery_candidates (
                        ip_address, inferred_name, inferred_role, discovery_source,
                        observed_log_count, sample_ports, dominant_events, sample_log,
                        icmp_status, snmp_status, solarwinds_status, zabbix_status,
                        verification_status, evidence_trail, last_seen_at, created_at, updated_at
                    ) VALUES (
                        ?, ?, ?, 'cisco_syslog_auditsessionid',
                        1, ?, ?, ?,
                        'untested', 'unavailable_unconfirmed', 'swis_auth_forbidden_403', 'unregistered',
                        'pending_verification', ?, ?, ?, ?
                    )
                    ON CONFLICT (ip_address) DO UPDATE SET
                        observed_log_count = network_discovery_candidates.observed_log_count + 1,
                        last_seen_at = EXCLUDED.last_seen_at,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        cand_ip,
                        cand_name,
                        cand_role,
                        cand_port,
                        cand_event,
                        line_str[:255],
                        cand_evidence,
                        now,
                        now,
                        now,
                    ),
                )

        # Enforce strict 120-hour (5 days) retention inside PostgreSQL
        retention_cutoff = now - (RETENTION_HOURS * 3600)
        session.execute(
            """
            DELETE FROM canonical_telemetry_events
            WHERE source_system = 'solarwinds_forwarded_syslog'
              AND event_timestamp < ?
            """,
            (retention_cutoff,),
        )

    # 4. Save new cursor with inode/device metadata
    cursor_payload = {
        "inode": file_ino,
        "dev": file_dev,
        "offset": new_offset,
        "updated_at": now,
        "reconciled_events": reconciled,
    }
    tmp_cursor = f"{CURSOR_FILE}.tmp"
    with open(tmp_cursor, "w", encoding="utf-8") as f:
        json.dump(cursor_payload, f)
    os.replace(tmp_cursor, CURSOR_FILE)

    logger.info(
        "Successfully reconciled %d events into PostgreSQL. New cursor: %d (inode: %d)",
        reconciled, new_offset, file_ino,
    )


def _enforce_retention(store: Store, now: float) -> None:
    try:
        retention_cutoff = now - (RETENTION_HOURS * 3600)
        with store.db.transaction() as session:
            session.execute(
                """
                DELETE FROM canonical_telemetry_events
                WHERE source_system = 'solarwinds_forwarded_syslog'
                  AND event_timestamp < ?
                """,
                (retention_cutoff,),
            )
    except Exception as e:
        logger.error("Failed to prune old telemetry events: %s", e)


if __name__ == "__main__":
    run_reconciliation()
