# Nawari Platform — Operator Credential Governance and Lifecycle Standard

## 1. Security Architecture & Threat Model

Privileged access to the Nawari administrative API (`/api/v1/assurance/*`, `/api/v1/inventory/*`, `/api/v1/investigation`) is governed by cryptographic token digests stored in the `operators` table:

```
Token String (32 bytes entropy) ──► SHA-256 Digest ──► operators.token_hash (PostgreSQL)
  └─ Stored in persistent secrets                       └─ Salted/Hashed, no plaintext
```

### Constraints & Security Invariants
1. **Zero Secret Persistence in Chat / Git:** Plaintext tokens, passphrases, and private keys must never be committed to Git or echoed into prompt responses.
2. **Strict Filesystem Permissions:** Secret files are stored exclusively in `/home/admin.comms/nawari-network-core/persistent/secrets/` with POSIX permissions `0600` (`-rw-------`), owned by `admin.comms:admin.comms`.
3. **Bounded Expiration:** Administrative tokens must enforce a non-null `expires_at` timestamp (default: 30 days / 2,592,000 seconds). Permanent or indefinite tokens (`expires_at = NULL`) are prohibited.
4. **Immediate Revocation:** Compromised or unneeded tokens must be immediately revoked by setting `revoked_at = NOW()` or deleting the record from `operators`.

---

## 2. Active Operator Credentials

| Token Identifier | Tenant Scope | Role | Expiration Policy | Storage Location | Provisioned At |
| :--- | :---: | :---: | :---: | :--- | :--- |
| `pilot-commissioning-admin` | `pilot` | `admin` | Bounded (30 days) | `persistent/secrets/pilot_operator_token` | 2026-11-24 |

---

## 3. Rotation & Revocation Protocol

### Standard 30-Day Rotation Procedure
```bash
# On mon-grafana01 as admin.comms:
python3 -c '
import secrets, hashlib, time, subprocess

token = secrets.token_hex(32)
token_hash = hashlib.sha256(token.encode()).hexdigest()
expires_at = time.time() + (30 * 86400)

secret_file = "/home/admin.comms/nawari-network-core/persistent/secrets/pilot_operator_token"
with open(secret_file, "w") as f:
    f.write(token + "\n")
subprocess.run(["chmod", "0600", secret_file], check=True)

sql = f"INSERT INTO operators (token_hash, tenant, role, expires_at) VALUES (\x27{token_hash}\x27, \x27pilot\x27, \x27admin\x27, {expires_at});"
subprocess.run(["docker", "exec", "nawari-network-core-postgres-1", "psql", "-U", "nawari_owner", "-d", "nawari", "-c", sql], check=True)
'
```

### Emergency Revocation Procedure
```bash
docker exec nawari-network-core-postgres-1 psql -U nawari_owner -d nawari -c \
  "UPDATE operators SET revoked_at = EXTRACT(EPOCH FROM NOW()) WHERE tenant = 'pilot' AND revoked_at IS NULL;"
```
