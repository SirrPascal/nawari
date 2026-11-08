# Phase 13.15 — Capacity, Sizing & Growth Runway Model

## Sizing Model Overview

Based on the authoritative inventory of 12 monitored hosts and 422 metrics established across the Nawari monitoring templates, this model projects data generation rates, database table growth, and disk storage requirements.

---

## 1. Workload Parameters

- **Monitored Items ($N$)**: 422 items
- **Average Polling Frequency ($T$)**: 60.0 seconds
- **Values Per Second ($VPS = \frac{N}{T}$)**: $7.03\text{ values/second}$
- **Values Per Day ($VPD = VPS \times 86,400$)**: $607,680\text{ values/day}$
- **Raw History Row Size ($S_{hist}$)**: $\approx 50\text{ bytes}$ (PostgreSQL `history` and `history_uint`)
- **Hourly Trend Row Size ($S_{trend}$)**: $\approx 128\text{ bytes}$ (min, max, avg, count)

---

## 2. Storage Growth Projections

### A. Raw History Storage (7-Day Retention)
$$\text{Daily History Growth} = \frac{607,680 \times 50\text{ bytes}}{1,048,576} \approx 29.0\text{ MB/day}$$
$$\text{7-Day Active History Buffer} = 29.0\text{ MB/day} \times 7\text{ days} \approx \mathbf{203\text{ MB}}$$
$$\text{30-Day Active History Buffer} = 29.0\text{ MB/day} \times 30\text{ days} \approx \mathbf{870\text{ MB}}$$

### B. Consolidated Trends Storage (365-Day Retention)
Each item generates 24 trend records per day:
$$\text{Daily Trend Records} = 422 \times 24 = 10,128\text{ records/day}$$
$$\text{Daily Trend Growth} = \frac{10,128 \times 128\text{ bytes}}{1,048,576} \approx 1.24\text{ MB/day}$$
$$\text{365-Day Annual Trends Buffer} = 1.24\text{ MB/day} \times 365\text{ days} \approx \mathbf{451\text{ MB/year}}$$

### C. Total Annual Database Footprint
$$\text{Total DB Size} = \text{Base Config (100 MB)} + \text{7d History (203 MB)} + \text{365d Trends (451 MB)} + \text{PostgreSQL Indexes (800 MB)} \approx \mathbf{1.6\text{ GB/year}}$$

---

## 3. Storage Runway on `mon-grafana01`

With a standard 50 GB NVMe partition dedicated to PostgreSQL and Docker volumes:
$$\text{Storage Runway} = \frac{50\text{ GB}}{1.6\text{ GB/year}} > \mathbf{30\text{ Years}}$$

The platform has zero storage risk under the current 422-item workload and can safely scale to 5,000+ monitored items without requiring additional disk provisioning.

