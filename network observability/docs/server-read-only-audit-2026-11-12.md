# Server read-only audit

Status: blocked before observation. No server mutation performed.

Target: `admin.comms@10.2.1.58`

## Access evidence

| Item | Status | Evidence |
| --- | --- | --- |
| Network/SSH service | Verified now | SSH reached the target and returned an authentication decision. |
| Host-key handling | Verified now | Existing ED25519, RSA and ECDSA entries are present in the Mac known-hosts file; strict checking remains `ask`, not disabled. |
| Authentication | Blocked | Non-interactive access was rejected. No password or private key was requested or transmitted. |
| Server facts | Not observed | Hostname, OS, resources, services, repositories, listeners, firewall and storage have not been inspected in this workstream. |

Safe owner action: load the established private key into the macOS SSH agent or add its path as the host-specific `IdentityFile`. Do not send the key or passphrase through chat.

## Audit command

After access is available, run the source-controlled read-only script first:

```sh
ssh admin.comms@10.2.1.58 'sh -s' < "network observability/server/platform/audit-server-readonly.sh"
```

Review the script before execution. Its output must be stored as sanitized evidence; it deliberately avoids container environments, secret contents and private keys. Targeted follow-up inspection remains necessary for Compose file order, bind mounts, certificates, repository state, backups and monitoring health.

## Local/server comparison

| Component | Local verified version | Server version |
| --- | --- | --- |
| Netdata | 2.12.3 | Inaccessible; historical reports are not current evidence |
| Nawari platform | Local source snapshot pending final checksum | Not deployed |
| PostgreSQL target | 17.6 isolated validation passed | Inaccessible |
| Docker/Compose | Docker 29.8.0 engine; Compose v5.5.1 client | Inaccessible |
| Grafana-Loki, Alloy, Mimir, Kafka | Configuration prepared only | Inaccessible |

