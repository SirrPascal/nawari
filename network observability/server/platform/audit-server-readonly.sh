#!/bin/sh
set -eu

echo "[host]"
hostname
uname -srmo
test -r /etc/os-release && awk -F= '$1=="PRETTY_NAME"||$1=="VERSION_ID"{print}' /etc/os-release
date -u '+%Y-%m-%dT%H:%M:%SZ'
uptime
command -v timedatectl >/dev/null 2>&1 && timedatectl show --property=NTPSynchronized --property=Timezone || true

echo "[capacity]"
getconf _NPROCESSORS_ONLN
free -h
swapon --show --noheadings || true
df -hT
command -v lsblk >/dev/null 2>&1 && lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINTS || true
command -v vmstat >/dev/null 2>&1 && vmstat 1 2 | tail -2 || true

echo "[runtime]"
if command -v docker >/dev/null 2>&1; then
    docker version --format 'client={{.Client.Version}} server={{.Server.Version}}' || true
    docker compose version || true
    docker compose ls --format json || true
    docker ps --format '{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}'
    for container in $(docker ps -q); do
        docker inspect --format 'container={{.Name}} image={{.Image}} restart={{.HostConfig.RestartPolicy.Name}} memory={{.HostConfig.Memory}} nano_cpus={{.HostConfig.NanoCpus}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}not-configured{{end}} compose_project={{index .Config.Labels "com.docker.compose.project"}} compose_files={{index .Config.Labels "com.docker.compose.project.config_files"}}' "$container"
        docker inspect --format '{{range .Mounts}}mount container={{$.Name}} type={{.Type}} source={{.Source}} destination={{.Destination}} rw={{.RW}}{{println}}{{end}}' "$container"
    done
    docker image ls --digests --format '{{.Repository}}:{{.Tag}}|{{.Digest}}|{{.ID}}|{{.Size}}'
    docker volume ls --format '{{.Name}}|{{.Driver}}'
    docker system df || true
fi

echo "[listeners]"
ss -lntup 2>/dev/null || ss -lntp

echo "[source]"
for candidate in /opt/nawari /srv/nawari /home/admin.comms/nawari /home/admin.comms/nawari-network-pilot; do
    if [ -d "$candidate" ]; then
        printf '%s|' "$candidate"
        if git -C "$candidate" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
            git -C "$candidate" rev-parse HEAD
            git -C "$candidate" status --short
        else
            echo "not-a-git-worktree"
        fi
        find "$candidate" -maxdepth 3 -type f \( -name 'compose.yaml' -o -name 'docker-compose*.yml' -o -name 'docker-compose*.yaml' \) -print
    fi
done

echo "[firewall-and-proxy]"
command -v ufw >/dev/null 2>&1 && (sudo -n ufw status verbose 2>/dev/null || ufw status verbose 2>/dev/null || true)
command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state 2>/dev/null && firewall-cmd --list-all 2>/dev/null || true
for service in nginx caddy apache2 httpd traefik; do
    systemctl is-active "$service" 2>/dev/null && systemctl show "$service" --property=FragmentPath --property=ActiveEnterTimestamp 2>/dev/null || true
done

echo "[certificate-metadata]"
if command -v openssl >/dev/null 2>&1 && [ -d /etc/letsencrypt/live ]; then
    find /etc/letsencrypt/live -maxdepth 2 -type l -name fullchain.pem -print 2>/dev/null | while read -r certificate; do
        printf 'certificate=%s\n' "$certificate"
        openssl x509 -in "$certificate" -noout -subject -issuer -dates -ext subjectAltName 2>/dev/null || true
    done
fi

echo "[monitoring-and-parent]"
for binary in netdata zabbix_server zabbix_agent2 grafana-server; do
    command -v "$binary" >/dev/null 2>&1 && "$binary" --version 2>&1 | head -2 || true
done
curl --fail --silent --show-error --max-time 3 http://127.0.0.1:19999/api/v1/info 2>/dev/null | head -c 4096 || true
printf '\n'
curl --fail --silent --show-error --max-time 3 http://127.0.0.1:19999/api/v3/stream_info 2>/dev/null | head -c 8192 || true
printf '\n'

echo "[backup-and-log-storage]"
systemctl list-timers --all --no-pager 2>/dev/null | grep -Ei 'backup|snapshot|dump|restic|borg' || true
crontab -l 2>/dev/null | grep -Ei 'backup|snapshot|dump|restic|borg' || true
command -v journalctl >/dev/null 2>&1 && journalctl --disk-usage 2>/dev/null || true
for directory in /var/backups /opt/backups /srv/backups; do
    [ -d "$directory" ] && du -sh "$directory" 2>/dev/null || true
done

echo "[restart-and-logs]"
systemctl is-enabled docker 2>/dev/null || true
systemctl is-active docker 2>/dev/null || true
test -f /etc/docker/daemon.json && stat -c '%n mode=%a owner=%U:%G' /etc/docker/daemon.json || true
find /etc/logrotate.d -maxdepth 1 -type f -printf '%f\n' 2>/dev/null | sort
