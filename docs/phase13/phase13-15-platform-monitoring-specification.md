# Phase 13.15 — Platform Self-Monitoring Specification

## Overview

The monitoring platform itself must be monitored to ensure early detection of queue saturation, memory bloat, or database connection exhaustion before it affects monitoring operations.

---

## 1. Zabbix Internal Health Metrics & Thresholds

| Metric Key | Description | Normal Range | Warning Threshold | Critical Threshold |
| :--- | :--- | :--- | :--- | :--- |
| `zabbix[process,history syncer,avg,busy]` | History Syncer thread utilization | < 10% | > 40% (3m) | > 75% (5m) |
| `zabbix[process,configuration syncer,avg,busy]` | Config Syncer thread utilization | < 5% | > 30% | > 60% |
| `zabbix[process,poller,avg,busy]` | Standard SNMP/Agent poller utilization | < 20% | > 50% | > 80% |
| `zabbix[process,icmp pinger,avg,busy]` | ICMP Ping poller utilization | < 15% | > 50% | > 85% |
| `zabbix[wcache,values]` | Write cache values processed/sec | 5-50 vps | N/A | Queue drop |
| `zabbix[queue]` | Delayed items in monitoring queue | 0-10 items | > 50 items | > 200 items |

---

## 2. PostgreSQL Self-Monitoring Metrics & Thresholds

| Metric | Query / Source | Normal Range | Alert Threshold |
| :--- | :--- | :--- | :--- |
| **Database Size** | `pg_database_size('zabbix')` | 100 MB - 10 GB | > 40 GB (Disk runway alert) |
| **Active Connections** | `SELECT count(*) FROM pg_stat_activity` | 10 - 40 conns | > 80 connections (Max 100) |
| **Dead Tuples Bloat** | `n_dead_tup` in `pg_stat_user_tables` | < 5% table rows | > 20% (Autovacuum required) |
| **Transaction ID Wrap** | `age(datfrozenxid)` | < 100M txns | > 1.5 Billion (Emergency autovacuum) |
