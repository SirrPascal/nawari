#!/bin/sh
set -eu

grafana_container=${GRAFANA_CONTAINER:-nawari-grafana}

docker exec "$grafana_container" sh -c '
set -eu
base=http://127.0.0.1:3000
auth=$GF_SECURITY_ADMIN_USER:$GF_SECURITY_ADMIN_PASSWORD

ensure_datasource() {
  uid=$1
  payload=$2
  code=$(curl -sS -o /dev/null -w "%{http_code}" -u "$auth" "$base/api/datasources/uid/$uid")
  if [ "$code" = 200 ]; then
    echo "$uid already present"
    return
  fi
  curl -fsS -u "$auth" -H "Content-Type: application/json" -d "$payload" \
    "$base/api/datasources" >/dev/null
  echo "$uid created"
}

ensure_datasource nawari-local-mimir \
  "{\"name\":\"Nawari Local Mimir\",\"uid\":\"nawari-local-mimir\",\"type\":\"prometheus\",\"access\":\"proxy\",\"url\":\"http://host.docker.internal:19009/prometheus\",\"isDefault\":false,\"jsonData\":{\"httpMethod\":\"POST\"}}"
ensure_datasource nawari-local-loki \
  "{\"name\":\"Nawari Local Loki\",\"uid\":\"nawari-local-loki\",\"type\":\"loki\",\"access\":\"proxy\",\"url\":\"http://host.docker.internal:13100\",\"isDefault\":false}"

for uid in nawari-local-mimir nawari-local-loki; do
  curl -fsS -u "$auth" "$base/api/datasources/uid/$uid/health"
  echo
done
'
