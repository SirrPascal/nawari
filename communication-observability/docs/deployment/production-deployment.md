# Nawari Production Deployment Guide

**Target Environment:** `mon-grafana01` (`10.2.1.58`)  
**Operating System:** Ubuntu Server 24.04.4 LTS (x86_64)  
**Host Resources:** 2 vCPU, 7.8 GiB RAM, 4 GiB Swap, ~17 GB Free Disk Space  
**Date:** 2026-11-07

---

## 1. Production Architecture Principles

1. **Strict Resource Quotas**: Production Compose enforces `mem_limit` and `cpus` on every container to guarantee that Zabbix, PostgreSQL, and Grafana combined never exceed 2.2 GiB, leaving >5 GiB free for the host OS.
2. **Fail-Closed Safety**: Asterisk synthetic dialing (`profile: voice`) is disabled by default until firewall verification, CA certificates, and destination sign-offs are complete.
3. **Loopback Binding**: Administrative ports (Zabbix Web on `8080`, Grafana on `3001`, Nawari API on `8000`) bind exclusively to `127.0.0.1` and are accessed via SSH tunnel or reverse proxy.
4. **Shared Trap Spooling**: UDP 162 binds to the host to accept traps from `10.2.156.0/24` into the isolated `snmptrap-spool` volume.

---

## 2. Server Preflight Verification

Before initiating deployment on `mon-grafana01`, execute the preflight checks:

```bash
# 1. Verify OS and Kernel
uname -a
lsb_release -a

# 2. Check Disk Free Space (Must have >= 12 GB free)
df -h /

# 3. Check Available RAM and Swap
free -m

# 4. Verify System Clock Synchronization (< 50ms offset)
chronyc tracking || timedatectl status

# 5. Check for Port Conflicts (Ensure 162, 10051, 8080, 3001 are free)
sudo ss -tulpn | grep -E ':(162|10051|8080|3001|5432)'

# 6. Verify Physical Route to Pride Subnet
ip route get 10.2.156.131
```

---

## 3. Production Deployment Execution

### Step 1: Transfer Repository & Set File Permissions
```bash
cd /opt/nawari
sudo chown -R nawari:nawari /opt/nawari
chmod 700 /opt/nawari
```

### Step 2: Configure Production Secrets
```bash
cp .env.example .env
chmod 600 .env
```
Populate `.env` with:
- Strong random database passwords (`POSTGRES_PASSWORD`).
- Strong Zabbix admin password (`ZBX_API_PASSWORD`).
- Strong Grafana admin credentials (`GRAFANA_ADMIN_PASSWORD`).
- Verified SNMPv3 auth and privacy credentials for Avaya SBCE (`AVAYA_SBCE_SNMP_AUTH_PASS`, `AVAYA_SBCE_SNMP_PRIV_PASS`).
- Set `NAWARI_ENV=production`.

### Step 3: Launch with Production Profile
```bash
docker compose -f docker/compose.yaml -f docker/compose.prod.yaml up -d
```

### Step 4: Verify Container Startup & Health
```bash
docker compose -f docker/compose.yaml -f docker/compose.prod.yaml ps
```
Monitor logs for database initialization and Zabbix server startup:
```bash
docker compose -f docker/compose.yaml logs -f zabbix-server
```

---

## 4. Automated Database Backup & Housekeeping

Install a daily cron job to back up the Zabbix PostgreSQL database:

```bash
# /etc/cron.d/nawari-backup
0 2 * * * nawari /opt/nawari/scripts/backup/backup_postgres.sh >> /var/log/nawari/backup.log 2>&1
```

The backup script:
1. Runs `pg_dump -U zabbix zabbix | gzip > /opt/nawari/backups/zabbix_$(date +%Y%m%d).sql.gz`.
2. Verifies non-empty archive integrity.
3. Automatically prunes backups older than 7 days to preserve disk space.

---

## 5. Rollback Procedure

If a failure occurs during deployment or database migration:

```bash
# 1. Stop current containers
docker compose -f docker/compose.yaml -f docker/compose.prod.yaml down

# 2. Restore PostgreSQL data volume from latest backup
gunzip -c /opt/nawari/backups/zabbix_PREVIOUS_STABLE.sql.gz | docker exec -i nawari-postgres-1 psql -U zabbix zabbix

# 3. Re-launch previous stable version
docker compose -f docker/compose.yaml -f docker/compose.prod.yaml up -d
```

