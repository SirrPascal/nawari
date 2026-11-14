#!/bin/sh
set -eu

base="${NETDATA_URL:-http://127.0.0.1:19999}"
command -v curl >/dev/null || { printf 'curl is required.\n' >&2; exit 2; }
charts="$(curl --fail --silent --show-error --max-time 5 "$base/api/v1/charts")"
printf '%s' "$charts" | grep -q '"nawari\.' || {
  printf 'No Nawari charts are available; supervision alone is not telemetry proof.\n' >&2
  exit 1
}
charts_seen=0
charts_live=0
for chart in $(printf '%s' "$charts" | grep -o '"nawari\.[^"]*"' | tr -d '"' | sort -u); do
  charts_seen=$((charts_seen + 1))
  data="$(curl --fail --silent --show-error --max-time 5 --get \
    --data-urlencode "chart=$chart" --data-urlencode 'after=-600' \
    --data-urlencode 'points=20' --data-urlencode 'format=json' "$base/api/v1/data" || true)"
  if printf '%s' "$data" | grep -Eq '\[[[:space:]]*[0-9]+,[[:space:]]*-?[0-9]'; then
    charts_live=$((charts_live + 1))
  fi
done
[ "$charts_seen" -gt 0 ] && [ "$charts_live" -gt 0 ] || {
  printf 'Nawari charts exist but have no numeric recent samples.\n' >&2
  exit 1
}
printf 'Verified %s of %s Nawari charts with numeric recent samples.\n' "$charts_live" "$charts_seen"
