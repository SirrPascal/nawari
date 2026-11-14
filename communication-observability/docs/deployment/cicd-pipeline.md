# Nawari CI/CD Pipeline — Architecture & Operations Guide

**Repository:** `SirrPascal/nawari`  
**Deployment Target:** `mon-grafana01` (`10.2.1.58`, Ubuntu Server 24.04.4 LTS)  
**Deployment execution:** Manual administrator operation on `mon-grafana01`; GitHub Actions uses only GitHub-hosted runners  
**Container Registry:** GitHub Container Registry (`ghcr.io/sirrpascal/nawari/nawari-core`)  
**Date:** 2026-11-09  

---

## 1. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        GitHub Actions                                   │
│                                                                          │
│   ┌──────────────────────────────────────────┐                          │
│   │  Stage A: CI Validation (ubuntu-latest)  │                          │
│   │  • Lint (ruff), Type Check (mypy)        │                          │
│   │  • 479 Unit Tests + Safe Integration     │                          │
│   │  • Compose/Dockerfile Validation         │                          │
│   │  • HARD_PRODUCTION_DENY Gate Test        │                          │
│   │  • Dependency Security Audit (pip-audit) │                          │
│   └─────────────────────┬────────────────────┘                          │
│                         │ on: push to main                              │
│   ┌─────────────────────▼────────────────────┐                          │
│   │  Stage B: Build & Publish (ubuntu-latest)│                          │
│   │  • Docker Buildx (linux/amd64)           │                          │
│   │  • GHCR Push (immutable SHA digest)      │                          │
│   │  • SBOM + Provenance Attestation         │                          │
│   │  • GitHub Actions Cache                  │                          │
│   └─────────────────────┬────────────────────┘                          │
│                         │                                                │
│   ┌─────────────────────▼────────────────────┐                          │
│   │  Stage C: Safety Gate (ubuntu-latest)    │                          │
│   │  • Profile Eligibility Check             │                          │
│   │  • HARD_PRODUCTION_DENY Enforcement      │                          │
│   │  • Phase 8.2 Commissioning Verification  │                          │
│   └─────────────────────┬────────────────────┘                          │
│                         │ requires approval                              │
│   ┌─────────────────────▼────────────────────┐                          │
│   │  Stage D-F: Manual Administrator Handoff │                          │
│   │  • Immutable digest and exact command    │                          │
│   │  • Server-side restricted deployment     │                          │
│   │  • Health/monitoring verification        │                          │
│   └──────────────────────────────────────────┘                          │
└──────────────────────────────────────────────────────────────────────────┘

                              │ deploys only
                              ▼
┌──────────────────────────────────────────────────────────────────────────┐
│               mon-grafana01 (10.2.1.58)                                 │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────┐     │
│  │  PROTECTED MONITORING INFRASTRUCTURE (Never touched by CI/CD)  │     │
│  │  • nawari-postgres    (PostgreSQL 17-alpine, port 5432)        │     │
│  │  • nawari-zabbix-server (Zabbix 7.4, port 10051)              │     │
│  │  • nawari-zabbix-web    (Nginx/PHP-FPM, 127.0.0.1:8080)       │     │
│  │  • nawari-grafana       (Grafana 11.6, 127.0.0.1:3000)        │     │
│  │  • nawari-snmptraps     (SNMP Traps, 0.0.0.0:162/udp)         │     │
│  └────────────────────────────────────────────────────────────────┘     │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────┐     │
│  │  APPLICATION SERVICE (Deployed by CI/CD pipeline)              │     │
│  │  • nawari-core  (ghcr.io/sirrpascal/nawari/nawari-core@sha256) │     │
│  │    Port: 127.0.0.1:8443                                        │     │
│  │    Health: /api/v1/health, /health                              │     │
│  │    Limit: 280M RAM, 0.50 CPU                                   │     │
│  └────────────────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Workflow Files

| File | Purpose | Trigger |
|------|---------|---------|
| `.github/workflows/ci.yml` | Stage A: Lint, test, validate, security audit | Push to `main`, `feat/**`, `release/**`; PR to `main` |
| `.github/workflows/deploy.yml` | Stages B–F: Build, gate, deploy, verify, rollback | Push to `main`; `workflow_dispatch` |

---

## 3. Application Service Boundaries

The CI/CD pipeline deploys **only** `nawari-core`:

| Component | Managed by CI/CD | Image Source |
|-----------|:---:|---|
| `nawari-core` | ✅ | `ghcr.io/sirrpascal/nawari/nawari-core` |
| `nawari-postgres` | ❌ | `postgres:17-alpine` (upstream) |
| `nawari-zabbix-server` | ❌ | `zabbix/zabbix-server-pgsql:alpine-7.4.0` (upstream) |
| `nawari-zabbix-web` | ❌ | `zabbix/zabbix-web-nginx-pgsql:alpine-7.4.0` (upstream) |
| `nawari-grafana` | ❌ | `nawari-grafana:11.6.0-zabbix-6.10.2` (custom Dockerfile build) |
| `nawari-snmptraps` | ❌ | `zabbix/zabbix-snmptraps:alpine-7.4.0` (upstream) |

The deployment script uses `docker compose up -d --no-deps nawari-core` to ensure monitoring services are **never** restarted.

---

## 4. Deployment Flow

### 4.1 Standard Deployment (Staging)

```bash
# Triggered by push to main or workflow_dispatch with profile=staging
# No Phase 8.2 certification required

Stage B → Build nawari-core → Push to GHCR with immutable SHA digest
Stage C → check_gating.py --profile staging → APPROVED_FOR_DEPLOYMENT
Stage D → Workflow summary provides the exact administrator command
Stage E → Administrator runs server-side health and monitoring verification
         Monitoring integrity check → all containers untouched
```

### 4.2 Production Deployment

```bash
# Requires workflow_dispatch with:
#   environment: production
#   profile: single-site-production
#   phase_8_2_certified: true

Stage C → check_gating.py --profile single-site-production --phase-8-2-certified
  ├── Certified: APPROVED_FOR_DEPLOYMENT → proceed
  └── Not certified: HARD_PRODUCTION_DENY → pipeline halts fail-closed
```

### 4.3 Rollback

```bash
# workflow_dispatch with action: rollback validates the request and publishes
# an administrator handoff; it does not execute on the deployment server.

sudo /usr/local/bin/nawari-rollback [--digest sha256:...]
# If no digest provided, uses /opt/nawari/state/last_known_good_digest
```

---

## 5. HARD_PRODUCTION_DENY Enforcement

The pipeline enforces `HARD_PRODUCTION_DENY` at two levels:

1. **`scripts/deploy/check_gating.py`** — Python script invoking `services.multisite.packaging.DeploymentProfileManager.validate_deployment_eligibility()`. Returns exit code 2 when production profile lacks Phase 8.2 certification.

2. **`scripts/deploy/restricted_deploy.sh`** — Calls `check_gating.py` before any container operation. If exit code ≠ 0, the deployment halts immediately.

Production profiles (`single-site-production`, `multi-site-production`) require `phase_8_2_commissioning_required: true` in their YAML definitions.

---

## 6. GitHub Secrets & Variables Required

### Build permissions and server-side registry access

| Secret | Purpose | Notes |
|--------|---------|-------|
| `GITHUB_TOKEN` | GHCR push authentication for the GitHub-hosted build job | Automatically provided by GitHub; never copied to the deployment host |

The deployment host must have a root-owned Docker credential for `ghcr.io` configured by a
server administrator. The restricted root deployment controller performs the immutable digest
pull; the GitHub token is not transferred to the deployment server.

No additional long-lived secrets are required. `GITHUB_TOKEN` provides GHCR push access.

### Repository Variables (optional)

| Variable | Purpose | Default |
|----------|---------|---------|
| `NAWARI_PROFILE` | Default deployment profile | `staging` |
| `NAWARI_ENV` | Environment designation | `staging` |

---

## 7. GitHub Environment Configuration

### Environment: `staging`

- No approval required
- Deployment from `main` branch only

### Environment: `production`

- **Required reviewers:** At least 1 designated approver
- **Wait timer:** Consider 5-minute cool-off
- **Deployment branches:** `main` only
- **Concurrency:** `nawari-deploy-production` (no cancel-in-progress)

These are repository settings, not workflow documentation. Until the environment has a
required reviewer and `main` branch restriction configured, production deployment is not
considered ready.

---

## 8. Server-Side Deployment Security Model

### Server-Side Installation (one-time, as root on `mon-grafana01`)

```bash
# Run as root:
cd /opt/nawari
sudo bash scripts/deploy/install_runner_hardening.sh
```

This installs:

| File | Owner | Mode | Purpose |
|------|-------|------|---------|
| `/usr/local/bin/nawari-deploy` | `root:root` | `0750` | Restricted deployment script |
| `/usr/local/bin/nawari-rollback` | `root:root` | `0750` | Restricted rollback script |
| `/etc/sudoers.d/nawari-deploy` | `root:root` | `0440` | Least-privilege sudo policy |

### Sudoers Policy

```
nawari-runner ALL=(root) NOPASSWD: /usr/local/bin/nawari-deploy [a-zA-Z0-9_.:@/-]*
nawari-runner ALL=(root) NOPASSWD: /usr/local/bin/nawari-rollback [a-zA-Z0-9_.:@/-]*
```

The runner **cannot**:
- Execute arbitrary sudo commands
- Access the Docker socket directly
- Join the `docker` group
- Modify monitoring containers

---

## 9. Branch Protection Requirements

Configure in GitHub → Settings → Branches → `main`:

- [x] Require a pull request before merging
- [x] Require at least 1 approval
- [x] Require status checks to pass before merging
  - Required checks: `lint-and-validate`, `test-suite`
- [x] Require branches to be up to date before merging
- [x] Do not allow bypassing the above settings
- [x] Restrict who can push to matching branches

---

## 10. Health Endpoints

| Endpoint | Method | Expected Response |
|----------|--------|-------------------|
| `http://127.0.0.1:8443/health` | GET | `{"status": "HEALTHY", ...}` (HTTP 200) |
| `http://127.0.0.1:8443/api/v1/health` | GET | `{"status": "HEALTHY", "environment": "...", ...}` (HTTP 200) |

The deployment script polls `/api/v1/health` up to 10 times with 3s intervals. On failure, automatic rollback triggers.

---

## 11. Rollback Procedure

### Automatic (triggered by failed health check)

1. Deployment script detects health failure
2. Reads `/opt/nawari/state/last_known_good_digest`
3. Pulls previous image by digest
4. Executes `docker compose up -d --no-deps nawari-core` with previous image
5. Verifies health of rolled-back container
6. Writes rollback audit entry to `/opt/nawari/state/deployment_history.jsonl`

### Manual (via workflow_dispatch)

```
Workflow dispatch → action: rollback → optionally provide digest
```

### Emergency Manual (SSH to server)

```bash
sudo /usr/local/bin/nawari-rollback --digest sha256:<known_good>
```

---

## 12. Audit & Evidence

All deployments write to:

| File | Format | Content |
|------|--------|---------|
| `/var/log/nawari/deployments.log` | Text | Timestamped deployment log |
| `/opt/nawari/state/deployment_history.jsonl` | JSONL | `{"timestamp", "digest", "profile", "status", "image"}` |
| `/opt/nawari/state/last_known_good_digest` | Text | Most recent successful deployment digest |

---

## 13. Troubleshooting

### CI Failures

| Symptom | Cause | Resolution |
|---------|-------|------------|
| `ruff check` fails | Lint violations | Fix reported issues, push |
| `mypy` fails | Type annotation issues | Review and fix type errors |
| Unit tests fail | Code regression | Debug failing test, fix code |
| Compose validation fails | Invalid YAML | Check syntax of compose files |

### Deployment Failures

| Symptom | Cause | Resolution |
|---------|-------|------------|
| `HARD_PRODUCTION_DENY` | Phase 8.2 not certified | Obtain Phase 8.2 certification |
| Image pull fails | GHCR auth or digest issue | Verify image exists in GHCR |
| Health check fails | Application crash | Check `docker logs nawari-core` |
| Monitoring impacted | Deployment bug | Should never happen (--no-deps) |
| Rollback fails | Missing last_known_good | Provide explicit digest via workflow_dispatch |

---

## 14. Server-Side Actions Still Required

> [!IMPORTANT]
> These actions must be completed by a server administrator on `mon-grafana01` before the pipeline can execute deployments.

1. **Install deployment scripts** (as root):
   ```bash
   cd /opt/nawari
   sudo bash scripts/deploy/install_runner_hardening.sh
   ```

2. **Configure root-owned GHCR pull credentials** on the server:
   ```bash
   # As root, using an approved package-read token; do not place the token in GitHub workflow files.
   sudo docker login ghcr.io
   sudo chmod 0600 /root/.docker/config.json
   ```

3. **Create log and state directories**:
   ```bash
   sudo mkdir -p /var/log/nawari /opt/nawari/state
   sudo chown root:nawari-runner /var/log/nawari /opt/nawari/state
   sudo chmod 770 /var/log/nawari /opt/nawari/state
   ```

4. **Configure GitHub Environments** in repository settings:
   - Create `staging` environment (no restrictions)
   - Create `production` environment (required reviewers, branch restrictions)

5. **Configure Branch Protection** for `main`:
   - Require PR, status checks, and reviews as documented above
