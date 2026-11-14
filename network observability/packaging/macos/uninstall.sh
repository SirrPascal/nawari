#!/bin/sh
set -eu

netdata_bin="${NETDATA_BIN:-}"
for candidate in "$netdata_bin" /opt/netdata/sbin/netdata /usr/local/sbin/netdata /opt/homebrew/sbin/netdata /usr/local/opt/netdata/sbin/netdata; do
  if [ -n "$candidate" ] && [ -x "$candidate" ]; then netdata_bin="$candidate"; break; fi
done
[ -n "$netdata_bin" ] || { printf 'Netdata installation not found; nothing removed.\n' >&2; exit 1; }
plugin_dir="$("$netdata_bin" -W pluginsdir 2>/dev/null || true)"
[ -n "$plugin_dir" ] || plugin_dir="$(dirname "$netdata_bin")/../libexec/netdata/plugins.d"
plugin="$plugin_dir/nawari.plugin"
if [ -f "$plugin" ]; then rm "$plugin"; fi
printf 'Removed Nawari plugin. Configuration and rollback copies were preserved beside the Netdata configuration.\n'

