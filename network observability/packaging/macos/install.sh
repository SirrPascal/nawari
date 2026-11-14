#!/bin/sh
set -eu

expected_netdata="${NAWARI_NETDATA_VERSION:-2.12.3}"
script_dir="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
target_volume="${1:-/}"
payload_dir="${target_volume%/}/usr/local/libexec/nawari"
[ -f "$payload_dir/nawari.plugin" ] || payload_dir="/usr/local/libexec/nawari"
[ -f "$payload_dir/nawari.plugin" ] || payload_dir="$script_dir"

find_netdata() {
  for candidate in \
    "${NETDATA_BIN:-}" \
    /opt/netdata/sbin/netdata \
    /usr/local/sbin/netdata \
    /opt/homebrew/sbin/netdata \
    /usr/local/opt/netdata/sbin/netdata; do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

netdata_bin="$(find_netdata || true)"
if [ -z "$netdata_bin" ]; then
  printf 'A compatible Netdata installation was not found. Install Netdata %s using the approved operator method, then retry.\n' "$expected_netdata" >&2
  exit 1
fi
machine_arch="$(uname -m)"
plugin_arch="$(file "$payload_dir/nawari.plugin" 2>/dev/null || true)"
if [ "$machine_arch" = "arm64" ]; then
  printf '%s' "$plugin_arch" | grep -Eiq 'arm64' || { printf 'Collector architecture does not match this Mac: %s\n' "$plugin_arch" >&2; exit 1; }
elif [ "$machine_arch" = "x86_64" ]; then
  printf '%s' "$plugin_arch" | grep -Eiq 'x86_64|x86-64' || { printf 'Collector architecture does not match this Mac: %s\n' "$plugin_arch" >&2; exit 1; }
else
  printf 'Unsupported Mac architecture: %s\n' "$machine_arch" >&2
  exit 1
fi
installed="$("$netdata_bin" -v 2>/dev/null | awk '{print $2}' | sed 's/^v//')"
if [ "$installed" != "$expected_netdata" ]; then
  printf 'Netdata %s is required; found %s. Installation stopped without changes.\n' "$expected_netdata" "${installed:-none}" >&2
  exit 1
fi

netdata_path() {
  key="$1"
  value="$("$netdata_bin" -W "$key" 2>/dev/null || true)"
  [ -n "$value" ] && printf '%s\n' "$value"
}

plugin_dir="$(netdata_path pluginsdir || true)"
config_dir="$(netdata_path userconfigdir || true)"
vardir="$(netdata_path vardir || true)"
brew_bin=""
for candidate in /opt/homebrew/bin/brew /usr/local/bin/brew; do
  if [ -x "$candidate" ]; then
    brew_bin="$candidate"
    break
  fi
done
brew_prefix=""
if [ -n "$brew_bin" ]; then
  brew_prefix="$("$brew_bin" --prefix netdata 2>/dev/null || true)"
fi
if [ -z "$plugin_dir" ] || [ -z "$config_dir" ]; then
  for prefix in "$brew_prefix" /opt/homebrew/opt/netdata /usr/local/opt/netdata /opt/netdata; do
    if [ -n "$prefix" ] && [ -d "$prefix" ]; then
      plugin_dir="${plugin_dir:-$prefix/libexec/netdata/plugins.d}"
      config_dir="${config_dir:-$prefix/etc/netdata}"
      vardir="${vardir:-$prefix/var}"
      break
    fi
  done
fi
if [ -z "$plugin_dir" ] || [ -z "$config_dir" ]; then
  prefix="$(CDPATH= cd -- "$(dirname "$netdata_bin")/.." && pwd)"
  plugin_dir="${plugin_dir:-$prefix/libexec/netdata/plugins.d}"
  config_dir="${config_dir:-$prefix/etc/netdata}"
fi
backup_dir="$config_dir/nawari-rollback"
state_dir="${vardir:-$(dirname "$config_dir")/var/lib/netdata}/nawari"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup_dir"
install -d -m 0700 "$state_dir" "$state_dir/queue"
for target in "$plugin_dir/nawari.plugin" "$config_dir/nawari-collector.json"; do
  if [ -f "$target" ]; then
    cp -p "$target" "$backup_dir/$(basename "$target").$timestamp"
  fi
done
install -d -m 0755 "$plugin_dir"
install -m 0755 "$payload_dir/nawari.plugin" "$plugin_dir/nawari.plugin"
if [ ! -f "$config_dir/nawari-collector.json" ]; then
 install -d -m 0755 "$config_dir"
 sed "s|__PREFIX__|$(dirname "$config_dir")|g" "$payload_dir/nawari-collector.example.json" > "$config_dir/nawari-collector.json.pending"
  chmod 0600 "$config_dir/nawari-collector.json.pending"
  mv "$config_dir/nawari-collector.json.pending" "$config_dir/nawari-collector.json"
  printf 'Edit %s with approved targets and credentials before restarting Netdata.\n' "$config_dir/nawari-collector.json"
else
  printf 'Preserved existing %s.\n' "$config_dir/nawari-collector.json"
fi
if command -v brew >/dev/null 2>&1 && brew services list 2>/dev/null | awk '$1 == "netdata" {found=1} END {exit !found}'; then
  brew services restart netdata
elif command -v launchctl >/dev/null 2>&1; then
  label="$(launchctl list 2>/dev/null | awk '$3 ~ /netdata/ {print $3; exit}')"
  if [ -n "$label" ]; then
    launchctl kickstart -k "system/$label" 2>/dev/null || launchctl kickstart -k "gui/$(id -u)/$label"
  else
    printf 'Netdata is installed but its launch service was not detected; restart it before verification.\n' >&2
  fi
else
  printf 'Netdata is installed but its service manager was not detected; restart it before verification.\n' >&2
fi
printf 'Netdata was treated as the pinned managed prerequisite; it was not replaced or reinstalled.\n'

