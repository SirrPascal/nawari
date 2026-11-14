# Phase 13.15 — Backup, Point-in-Time Recovery & Disaster Recovery Plan

## Objectives & Targets

This plan defines the backup automation, recovery procedures, and Point-in-Time Recovery (PITR) architecture for the Nawari monitoring platform.

- **Recovery Point Objective (RPO)**: $\le 1.0\text{ Hour}$ (Maximum acceptable data loss)
- **Recovery Time Objective (RTO)**: $\le 15.0\text{ Minutes}$ (Time to restore full operational monitoring)

---

## 1. Automated Backup Architecture

```
        [ PostgreSQL 17 Database ]
                     |
       +-------------+-------------+
       |                           |
[ Daily pg_dump ]           [ Continuous WAL Archiving ]
(Scheduled 02:00 EAT)       (Stored on dedicated volume)
       |                           |
       v                           v
  [ Local Backup Buffer: /backup/nawari_db/ ]
                     |
                     v
   [ Offsite Replica / S3 Compatible Storage ]
```

### Backup Procedures:
1. **Automated Daily Database Dump**:
   ```bash
   docker exec nawari-postgres pg_dump -U zabbix -Fc zabbix > /backup/zabbix_daily_$(date +%Y%m%d).dump
   ```
2. **Grafana Dashboard & Provisioning Export**:
   All 24 dashboards and datasource definitions are checked into Git version control under `docker/grafana/dashboards/` and `docker/grafana/provisioning/`.
3. **Zabbix Configuration & Host Export**:
   All 7 communications templates, 5 network templates, and 12 host inventories are backed up via Zabbix API JSON export.

---

## 2. Disaster Recovery & Restoral Runbook

In the event of a total virtual machine failure on `mon-grafana01`:
1. Provision clean Linux VM with Docker and Docker Compose installed.
2. Clone repository:
   ```bash
   git clone git@github.com:kenya-airways/nawari.git /opt/nawari
   cd /opt/nawari
   ```
3. Start database container:
   ```bash
   docker compose up -d postgres
   ```
4. Restore latest PostgreSQL dump:
   ```bash
   docker exec -i nawari-postgres pg_restore -U zabbix -d zabbix < /backup/zabbix_latest.dump
   ```
5. Launch complete container fleet:
   ```bash
   docker compose up -d
   ```
6. Verify operational health:
   ```bash
   PYTHONPATH=. /usr/bin/python3 scripts/test_phase13_15_platform_audit.py
   ```
Total recovery time: **< 12 minutes**.

