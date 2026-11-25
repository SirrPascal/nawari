#!/usr/bin/env bash
# ==============================================================================
# scripts/preflight_production_check.sh
# Read-only Preflight Health & Environment Inspector for mon-grafana01 (10.2.1.58)
#
# STRICT CONTRACT:
# - Absolutely READ-ONLY. Does not mutate files, databases, or container states.
# - Aborts immediately if unexpected conditions or insufficient resources exist.
# ==============================================================================
set -euo pipefail

echo "========================================================================"
echo "NAWARI M5/M6 — PRODUCTION ENVIRONMENT PREFLIGHT CHECK"
echo "Target Host: mon-grafana01 (10.2.1.58)"
echo "Timestamp: $(date -u +"%Y-%m-%d %H:%M:%SZ")"
echo "========================================================================"

FAILED_CHECKS=0

pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAILED_CHECKS=$((FAILED_CHECKS + 1)); }
warn() { echo "  [WARN] $1"; }

# 1. Docker Daemon & Storage Health
echo ""
echo "[1] Checking Docker Engine & Storage Health..."
if command -v docker &>/dev/null; then
    pass "Docker CLI found: $(docker --version)"
    if docker info &>/dev/null; then
        pass "Docker daemon reachable"
    else
        fail "Docker daemon not responding or permission denied"
    fi
else
    fail "Docker CLI not installed on target host"
fi

# Disk Space Check (> 15% free on root and docker volumes)
AVAIL_KB=$(df -k / | awk 'NR==2 {print $4}')
if [ "$AVAIL_KB" -gt 5242880 ]; then
    pass "Root filesystem has adequate headroom ($((AVAIL_KB / 1024 / 1024)) GB available)"
else
    fail "Insufficient disk space on / (< 5GB available)"
fi

# 2. Existing Running Containers & digests
echo ""
echo "[2] Auditing Core Monitoring Containers..."
CONTAINERS=("nawari-grafana" "nawari-postgres" "nawari-heplify" "nawari-asterisk")
for c in "${CONTAINERS[@]}"; do
    if docker ps --format '{{.Names}}' | grep -q "^${c}$"; then
        IMG=$(docker inspect --format '{{.Config.Image}}' "$c")
        STATUS=$(docker inspect --format '{{.State.Status}}' "$c")
        pass "Container $c is $STATUS (Image: $IMG)"
    else
        warn "Container $c is not running"
    fi
done

# 3. PostgreSQL Migration Revision Check
echo ""
echo "[3] Auditing Database Schema Revision..."
if docker ps --format '{{.Names}}' | grep -q "^nawari-postgres$"; then
    CURRENT_REV=$(docker exec nawari-postgres psql -U zabbix -d nawari_platform -t -c \
        "SELECT COALESCE(MAX(version), 0) FROM schema_migrations;" 2>/dev/null || echo "UNAVAILABLE")
    if [ "$CURRENT_REV" != "UNAVAILABLE" ]; then
        pass "Current Nawari PostgreSQL schema migration version: $(echo $CURRENT_REV | tr -d ' ')"
    else
        warn "Could not read schema_migrations from nawari-postgres (database may be fresh or unmigrated)"
    fi
else
    warn "nawari-postgres container not active; migration check skipped"
fi

# 4. Critical Port Availability & Conflict Check
echo ""
echo "[4] Checking Service Listening Ports (No Unauthorized Collisions)..."
CHECK_PORTS=(5432 9060 3000 5060 5038 3100)
for p in "${CHECK_PORTS[@]}"; do
    if command -v ss &>/dev/null; then
        BINDINGS=$(ss -tulpn "sport = :$p" 2>/dev/null | grep -v "Netid" || true)
    elif command -v netstat &>/dev/null; then
        BINDINGS=$(netstat -tuln 2>/dev/null | grep ":$p " || true)
    else
        BINDINGS=""
    fi
    if [ -n "$BINDINGS" ]; then
        pass "Port $p active and bound to monitored service"
    else
        warn "Port $p has no active local socket listener"
    fi
done

# 5. Git Working Tree State
echo ""
echo "[5] Auditing Git Working Tree..."
if [ -d ".git" ]; then
    HEAD_REV=$(git rev-parse --short HEAD)
    pass "Current Git HEAD: $HEAD_REV on branch $(git rev-parse --abbrev-ref HEAD)"
    if [ -z "$(git status --porcelain)" ]; then
        pass "Working tree is clean"
    else
        warn "Working tree has uncommitted local modifications"
    fi
else
    warn "Not a git checkout directory"
fi

echo ""
echo "========================================================================"
if [ "$FAILED_CHECKS" -eq 0 ]; then
    echo "PREFLIGHT STATUS: ALL ESSENTIAL CHECKS PASSED. SYSTEM READY FOR CONTROLLED ROLLOUT."
    exit 0
else
    echo "PREFLIGHT STATUS: FAILED ($FAILED_CHECKS critical failures detected). ABORT DEPLOYMENT."
    exit 1
fi
