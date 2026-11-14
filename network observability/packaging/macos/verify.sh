#!/bin/sh
set -eu

base="${NETDATA_URL:-http://127.0.0.1:19999}"
info="$(curl --fail --silent --show-error --max-time 5 "$base/api/v1/info")"
charts="$(curl --fail --silent --show-error --max-time 5 "$base/api/v1/charts")"
netdatacli_bin="$(command -v netdatacli || true)"
for candidate in /opt/homebrew/sbin/netdatacli /usr/local/sbin/netdatacli /opt/netdata/bin/netdatacli; do
  [ -n "$netdatacli_bin" ] || [ ! -x "$candidate" ] || netdatacli_bin="$candidate"
done
[ -n "$netdatacli_bin" ] && "$netdatacli_bin" ping >/dev/null || {
  printf 'Netdata is not responding to netdatacli ping.\n' >&2
  exit 1
}
pgrep -f '/nawari\.plugin([[:space:]]|$)' >/dev/null || {
  printf 'Netdata is not supervising nawari.plugin.\n' >&2
  exit 1
}
if command -v brew >/dev/null 2>&1 && brew services list 2>/dev/null | awk '$1 == "nawari" {found=1} END {exit !found}'; then
  printf 'A separate Nawari service was detected.\n' >&2
  exit 1
fi
printf '%s' "$charts" | grep -q '"system.cpu' || { printf 'missing native CPU charts\n' >&2; exit 1; }
printf '%s' "$charts" | grep -q '"system.ram' || { printf 'missing native memory charts\n' >&2; exit 1; }
printf '%s' "$charts" | grep -Eq '"net\.[^"]*"' || { printf 'missing native network charts\n' >&2; exit 1; }
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
[ "$charts_seen" -gt 0 ] || { printf 'no Nawari charts discovered\n' >&2; exit 1; }
[ "$charts_live" -gt 0 ] || {
  printf 'Nawari charts exist but no recent numeric samples were collected\n' >&2
  exit 1
}
version="$(printf '%s' "$info" | sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
printf 'Netdata %s: verified %s Nawari charts, %s with numeric recent samples.\n' "${version:-unknown}" "$charts_seen" "$charts_live"
