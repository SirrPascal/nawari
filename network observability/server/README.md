# Netdata Parent pilot deployment

The local project builds a deployment archive and uploads it through SSH. The server runs an isolated Compose project named `nawari-network-pilot` with persistent identity and metric volumes, a 768 MiB memory limit and a half-CPU limit. The Parent receives metrics from the Mac agent. The initial service uses a 1 GiB soft storage target and seven-day metric retention. Both limits require runtime capacity verification. Raw-log centralization and fleet Grafana integration are later pilot stages.

## Deployment boundary

The approved endpoint-telemetry deployment target is the dedicated `nawari-network-pilot` Compose project under the remote user's home directory. Do not deploy this pilot or the prepared platform into `/opt/nawari`: the inspected `/opt/nawari` project is a separate legacy communications/Zabbix stack with its own PostgreSQL, Grafana, and Zabbix services. Do not stop, replace, or remove that stack as part of Nawari endpoint or platform deployment.

## Server requirements

Use Linux with Docker Engine, Docker Compose supporting `up --wait`, Python 3 and OpenSSL supporting `req -addext`. The deployment account needs Docker access or passwordless `sudo docker` for `--sudo-docker`. Open TCP 19999 on the server's approved network/VPN path to the Mac. The script leaves firewall policy to the existing server administration process.

The server address for this pilot is `10.2.1.58`. A DNS record is optional because the generated server certificate includes that IP as a subject alternative name. Certificate verification stays enabled on the Mac. Pilot certificates expire after 30 days. Prepare managed replacement certificates before that deadline.

## Deploy from the Mac

Run from the `network observability` directory in a local Terminal that can authenticate to the server. SSH password/passphrase prompts remain in that Terminal. Default SSH host-key verification remains enabled.

```sh
python3 scripts/deploy_server.py \
  --target admin.comms@10.2.1.58 \
  --address 10.2.1.58 \
  --allow-from 10.2.5.21
```

The default remote directory is `~/nawari-network-pilot`. Set `--remote-dir` to a different dedicated path if needed. Add `--identity /absolute/path/to/key` for a specific SSH key. Add `--sudo-docker` only when that account has passwordless sudo permission for Docker. Automated callers can add `--batch` to fail instead of prompting.

The deployment checks prerequisites, packages a fixed list of source files, uploads/extracts the archive, generates enrollment/TLS files on the server, validates Compose, starts the Parent and checks its read API. The readiness report explicitly leaves Mac streaming unverified until enrollment is tested. The deployment archive excludes local evidence and generated secrets.

Existing enrollment files are reused when address, bind address and source allowlist match. Changed settings or incomplete/expiring runtime files stop deployment for review. A failed container startup retains volumes and configuration for diagnosis. The code upload updates this pilot's files. Keep an earlier archive for code rollback.

The default streaming source rule is `*`, with authentication through the unique pilot UUID and TLS. Restrict `--allow-from` to the Mac's actual source as observed at the server where practical, allowing for VPN/NAT address changes. Incoming streaming and the read API use separate ports. Docker publishes streaming on `10.2.1.58:19999` and the dashboard/API only on `127.0.0.1:19998`.

## Manual server commands

After transferring and extracting the archive in the dedicated deployment directory, run these commands in the existing authenticated server shell.

```sh
python3 scripts/prepare_server.py --address 10.2.1.58 --bind-address 10.2.1.58 --allow-from 10.2.5.21
cd server
docker compose --env-file runtime/.env -f compose.yaml config --quiet
docker compose --env-file runtime/.env -f compose.yaml up -d --wait --wait-timeout 90
python3 ../scripts/verify_parent.py
```

`server/runtime/` contains enrollment secrets, a private pilot CA key, server TLS material, configuration and the generated Mac streaming template. It is created with restricted permissions and ignored by Git. The container copies only its required configuration and server key into its service account's protected paths before starting the stock Netdata entrypoint. It receives no host filesystem, host PID namespace or Docker socket mounts.

## Enroll the Mac after the Parent is healthy

Retrieve these two files through authenticated SSH/SCP into a protected local directory.

```sh
mkdir -p evidence/enrollment
chmod 700 evidence/enrollment
scp admin.comms@10.2.1.58:nawari-network-pilot/server/runtime/ca-cert.pem evidence/enrollment/pilot-ca-cert.pem
scp admin.comms@10.2.1.58:nawari-network-pilot/server/runtime/macos-stream.conf evidence/enrollment/stream.conf
chmod 600 evidence/enrollment/*
```

In the copied `stream.conf`, replace the `CAfile` placeholder with the absolute path to `pilot-ca-cert.pem` on this Mac. Verify the file contains `destination = 10.2.1.58:19999:SSL` and `ssl skip certificate verification = no`. Preserve any existing Homebrew Netdata `stream.conf` before merging the generated `[stream]` settings into `$(brew --prefix)/etc/netdata/stream.conf`. Then run `brew services restart netdata`.

For dashboard inspection, open a local SSH tunnel in a separate Terminal.

```sh
ssh -N -L 19998:127.0.0.1:19998 admin.comms@10.2.1.58
```

Open `http://127.0.0.1:19998` on the Mac and confirm the Mac's node appears with fresh charts. Run controlled HTTP fixture checks from the project README, compare their results on the Parent, and test disconnect/reconnect. Netdata's free dashboard limit is sufficient for the initial Mac and Parent pilot. Fleet visualization needs the planned external metric export and Grafana path.

For repeatable ingestion verification, run this on the server from the deployment directory. The wait interval accommodates child reconnection and chart replication after a restart.

```sh
python3 scripts/verify_parent.py --require-child --verify-fixtures --wait-seconds 90
```

## Operations

Run lifecycle commands inside the remote `server` directory with the same environment file.

```sh
docker compose --env-file runtime/.env -f compose.yaml ps
docker compose --env-file runtime/.env -f compose.yaml logs --tail 60 netdata-parent
docker compose --env-file runtime/.env -f compose.yaml stop
```

Resume with `up -d --wait`. Stopping preserves both volumes. Back up permitted enrollment/CA state through the approved secret backup process. A seven-day metric setting and size-based Docker log rotation do not demonstrate seven-day deletion of raw logs and their copies. Central log storage, queue expiry and restore tests need their own implementation before log collection expands.

The image is pinned to `netdata/netdata:v2.12.3`. Use an approved digest in `server/runtime/.env` after validating the deployment image. The container startup wrapper follows the image's stock `/usr/sbin/run.sh` entrypoint. Docker Engine must be available to verify runtime behavior.

Vendor references are the [Docker guide](https://learn.netdata.cloud/docs/netdata-agent/installation/docker), [streaming reference](https://learn.netdata.cloud/docs/netdata-parents/parent-child-configuration-reference), [TLS settings](https://learn.netdata.cloud/docs/netdata-agent/configuration/securing-agents/web-server-reference) and [metric database retention](https://learn.netdata.cloud/docs/netdata-agent/configuration/database).

## Verified deployment on 11 November 2026

The Parent is running at `/home/admin.comms/nawari-network-pilot` on `10.2.1.58` with Netdata `v2.12.3`. The Mac has been enrolled using the generated CA with certificate verification enabled. Its streaming filter selects network, DNS, ping, HTTP and uptime charts. The currently observed source address is `10.2.5.21`. A VPN/NAT address change may require an allowlist update before the agent reconnects.

Verification found two hosts, one reachable child and 123 child charts, including 70 fresh network charts. Controlled service checks reached the Parent with healthy response around 3 ms, delayed response around 1,007 ms and HTTP 503 represented as `bad_status`. Parent restart and subsequent child reconnection were verified. A startup readiness check can pass before the child reconnects, so the ingestion check waits separately.

The pilot certificate expires on 11 December 2026 at 12:08 EAT. The CA certificate is installed at `/opt/homebrew/etc/netdata/pilot-ca-cert.pem`, with streaming settings in the adjacent `stream.conf`. The three local HTTP fixture jobs are enabled in `go.d/httpcheck.conf`. The fixture process listens on Mac loopback port 18080. Keep it running for these controlled checks or remove the pilot jobs when stopping it.

The local `evidence/` folder contains the deployment summary, TLS identity verification, initial streaming verification and restart verification. Enrollment secrets are stored separately in the ignored `evidence/enrollment/` directory. DNS/ping targets, centralized logs and fleet Grafana export remain subsequent pilot work.
