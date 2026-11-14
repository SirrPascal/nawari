#!/bin/sh
set -eu

base_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
compose_file="$base_dir/compose.yaml"

docker compose -f "$compose_file" ps

curl -fsS http://127.0.0.1:19009/ready >/dev/null
curl -fsS http://127.0.0.1:13100/ready >/dev/null
curl -fsS http://127.0.0.1:12345/-/ready >/dev/null
curl -fsS http://127.0.0.1:19115/-/healthy >/dev/null
curl -fsS 'http://127.0.0.1:19009/prometheus/api/v1/query?query=up' \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); r=d["data"]["result"]; assert len(r) >= 2 and all(x["value"][1] == "1" for x in r); print(f"Mimir up series: {len(r)}")'
curl -fsS 'http://127.0.0.1:19009/prometheus/api/v1/query?query=probe_success' \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); r=d["data"]["result"]; assert r and all(x["value"][1] == "1" for x in r); print(f"Successful probe series: {len(r)}")'

openssl s_client \
  -connect 127.0.0.1:19997 \
  -servername 127.0.0.1 \
  -tls1_3 \
  -CAfile "$base_dir/runtime/ca-cert.pem" \
  </dev/null 2>/dev/null \
  | grep -q 'Verify return code: 0 (ok)'

echo 'Local observability lab validation passed.'
