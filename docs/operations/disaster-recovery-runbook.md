# Nawari Disaster Recovery & Cold Restore Runbook

**Document Version:** 1.0.0  
**Target Host:** `mon-grafana01` (Ubuntu 24.04 LTS, 2 vCPU, 7.8 GiB RAM, ~17 GB Free Disk)  
**Applicability:** Total host failure, storage volume loss, database corruption, or ransomware recovery.  
**Classification:** Kenya Airways IT Operations / Mission-Critical Observability  

---

## 1. Recovery Objectives & SLA Guarantees

| Metric | Guaranteed Objective | Description |
| :--- | :---: | :--- |
| **Recovery Point Objective (RPO)** | **$\le 1.0$ Hour** | Maximum acceptable data loss window for historical metrics, active triggers, and configuration state. |
| **Recovery Time Objective (RTO)** | **$\le 30.0$ Minutes** | Maximum allowable elapsed time from disaster declaration to full platform operational availability. |

---

## 2. Backup Inventory & Storage Matrix

Nawari executes automated backups via `scripts/backup/backup_nawari.sh` scheduled via cron every 6 hours:

```cron
# /etc/cron.d/nawari-backup
0 */6 * * * nawari /opt/nawari/scripts/backup/backup_nawari.sh >> /var/log/nawari/backup.log 2>&1
```

Each backup bundle is archived with cryptographic integrity digests:

| File Pattern | Description | Restoration Method |
| :--- | :--- | :--- |
| `nawari_db_<TIMESTAMP>.sql.gz` | Complete PostgreSQL database dump (Zabbix schema, metrics, users). | `psql` or `pg_restore` |
| `nawari_grafana_<TIMESTAMP>.tar.gz` | Grafana provisioned datasources, dashboards, and plugins. | Tarball extraction |
| `nawari_config_<TIMESTAMP>.tar.gz` | Compose files, security configs, and templates. | Tarball extraction |
| `SHA256SUMS` | Cryptographic SHA-256 signatures for archive verification. | `sha256sum --check` |

---

## 3. Step-by-Step Cold Disaster Recovery Procedure

### Step 1: Target Host Preparation (0–5 minutes)
1. Provision or re-image Ubuntu 24.04 LTS host with hostname `mon-grafana01` and IP `10.2.1.58`.
2. Install Docker Engine and Docker Compose v2:
   ```bash
   sudo apt-get update && sudo apt-get install -y ca-certificates curl gnupg ufw
   # Install Docker v26+
   ```
3. Apply kernel hardening:
   ```bash
   sudo cp docker/security/sysctl-hardening.conf /etc/sysctl.d/99-nawari.conf
   sudo sysctl --system
   ```
4. Apply UFW firewall baseline:
   ```bash
   sudo ./docker/security/ufw-rules.sh
   sudo ufw enable
   ```

### Step 2: Retrieve & Verify Backup Bundle (5–10 minutes)
1. Fetch latest verified backup bundle from secondary network storage:
   ```bash
   rsync -avz backup-server:/backups/nawari/latest/ /opt/nawari/backups/latest/
   cd /opt/nawari/backups/latest/
   ```
2. Verify SHA-256 integrity:
   ```bash
   sha256sum --check SHA256SUMS
   # MUST output: nawari_db_*.sql.gz: OK
   ```

### Step 3: Launch PostgreSQL Core & Restore Database (10–18 minutes)
1. Start PostgreSQL storage container:
   ```bash
   cd /opt/nawari
   docker compose -f docker/compose.yaml -f docker/compose.prod.yaml up -d postgres
   ```
2. Wait for PostgreSQL healthcheck:
   ```bash
   docker compose ps postgres
   # Verify status is "(healthy)"
   ```
3. Execute automated database restore:
   ```bash
   ./scripts/backup/restore_nawari.sh /opt/nawari/backups/latest
   ```

### Step 4: Launch Platform Services (18–24 minutes)
1. Launch Zabbix server, trap daemon, web frontend, and Grafana:
   ```bash
   docker compose -f docker/compose.yaml -f docker/compose.prod.yaml up -d
   ```
2. Check container health:
   ```bash
   docker compose ps
   # All services must indicate Up (healthy)
   ```

### Step 5: Post-Restore Operational Verification (24–30 minutes)
Execute the verification suite:
```bash
./scripts/verify_phase8.sh
```
Verify the following operational health signals:
* [x] **Zabbix API Responsive:** `curl -s -X POST -H 'Content-Type: application-json' -d '{"jsonrpc":"2.0","method":"apiinfo.version","params":[],"id":1}' http://127.0.0.1:8080/api_jsonrpc.php`
* [x] **Grafana UI Accessible:** `curl -s http://127.0.0.1:3000/api/health`
* [x] **SNMP Traps Listening:** `nc -z -u 127.0.0.1 162`
* [x] **Active Hosts Present:** PostgreSQL `SELECT COUNT(*) FROM hosts WHERE status=0;` > 0
* [x] **Endpoint Gateway Healthy:** Ingestion gateway resumes receiving agent heartbeats.

---

## 4. Emergency Contacts & Escalation Matrix

* **Primary Infrastructure Owner:** Kenya Airways IT Network Operations Center (`noc@kenya-airways.com`)
* **Telephony & PBX Systems:** Voice Engineering Team (`voice-ops@kenya-airways.com`)
* **Security & Compliance:** Kenya Airways SecOps (`secops@kenya-airways.com`)
