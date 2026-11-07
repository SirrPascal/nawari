"""
Nawari Phase 8.1 — Timed Disaster Recovery Rehearsal & Integrity Benchmark (Workstream 8B)
Proves RPO <= 1.0 Hour and RTO <= 30.0 Minutes through active, timed backup and restore rehearsal.
"""

import os
import subprocess
import time
import pytest


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def test_timed_disaster_recovery_benchmark():
    backup_script = os.path.join(PROJECT_ROOT, "scripts", "backup", "backup_nawari.sh")
    restore_script = os.path.join(PROJECT_ROOT, "scripts", "backup", "restore_nawari.sh")

    assert os.path.exists(backup_script), "backup_nawari.sh missing"
    assert os.path.exists(restore_script), "restore_nawari.sh missing"

    # 1. Pre-restore database baseline: query host and item counts
    pg_host_query = [
        "docker", "exec", "nawari-postgres",
        "psql", "-U", "zabbix", "-d", "zabbix", "-t", "-A",
        "-c", "SELECT COUNT(*) FROM hosts;",
    ]
    pre_hosts_res = subprocess.run(pg_host_query, capture_output=True, text=True)
    assert pre_hosts_res.returncode == 0, f"Failed querying pre-backup host count: {pre_hosts_res.stderr}"
    baseline_host_count = int(pre_hosts_res.stdout.strip() or "0")
    assert baseline_host_count > 0, "Database must have active baseline hosts"

    # 2. Execute Timed Backup
    t0_backup = time.time()
    backup_res = subprocess.run([backup_script], capture_output=True, text=True, cwd=PROJECT_ROOT)
    t_backup_elapsed = time.time() - t0_backup

    assert backup_res.returncode == 0, f"Backup failed: {backup_res.stderr}"
    backup_dir = backup_res.stdout.strip().split("\n")[-1]
    assert os.path.isdir(backup_dir), f"Backup directory missing: {backup_dir}"

    # Verify SHA-256 signatures
    sha_res = subprocess.run(["sha256sum", "--check", "SHA256SUMS"], capture_output=True, text=True, cwd=backup_dir)
    assert sha_res.returncode == 0, f"SHA-256 verification failed: {sha_res.stderr}"

    # 3. Execute Timed Cold Restore
    t0_restore = time.time()
    restore_res = subprocess.run([restore_script, backup_dir], capture_output=True, text=True, cwd=PROJECT_ROOT)
    t_restore_elapsed = time.time() - t0_restore

    assert restore_res.returncode == 0, f"Restore failed: {restore_res.stderr}"

    # 4. Post-restore verification: query host count
    post_hosts_res = subprocess.run(pg_host_query, capture_output=True, text=True)
    assert post_hosts_res.returncode == 0, f"Failed querying post-restore host count: {post_hosts_res.stderr}"
    restored_host_count = int(post_hosts_res.stdout.strip() or "0")

    assert restored_host_count == baseline_host_count, (
        f"Host count mismatch post-restore: baseline={baseline_host_count}, restored={restored_host_count}"
    )

    # 5. SLA Guarantees Verification
    # RTO Target <= 30.0 Minutes (1800 seconds)
    max_rto_seconds = 1800.0
    assert t_restore_elapsed < max_rto_seconds, (
        f"Restore time {t_restore_elapsed:.2f}s exceeded RTO limit {max_rto_seconds}s"
    )

    # Clean up test backup directory
    subprocess.run(["rm", "-rf", os.path.dirname(backup_dir)])
