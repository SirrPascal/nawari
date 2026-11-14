#!/bin/sh
set -eu

prefix="$(brew --prefix)"
backup="$prefix/etc/netdata/nawari-rollback"
plugin_backup="$(find "$backup" -type f -name 'nawari.plugin.*' -print 2>/dev/null | sort | tail -1)"
config_backup="$(find "$backup" -type f -name 'nawari-collector.json.*' -print 2>/dev/null | sort | tail -1)"
if [ -z "$plugin_backup" ]; then
  printf 'No plugin rollback copy is available.\n' >&2
  exit 1
fi
install -m 0755 "$plugin_backup" "$prefix/opt/netdata/libexec/netdata/plugins.d/nawari.plugin"
if [ -n "$config_backup" ]; then
  install -m 0600 "$config_backup" "$prefix/etc/netdata/nawari-collector.json"
fi
printf 'Restored the latest preserved Nawari plugin%s. Restart Netdata after reviewing the restored configuration.\n' "${config_backup:+ and configuration}"
