#!/bin/sh
set -eu

install -d -o netdata -g netdata -m 0750 /etc/netdata/ssl
install -o netdata -g netdata -m 0600 /run/pilot/netdata.conf /etc/netdata/netdata.conf
install -o netdata -g netdata -m 0600 /run/pilot/stream.conf /etc/netdata/stream.conf
install -o netdata -g netdata -m 0600 /run/pilot/server-key.pem /etc/netdata/ssl/key.pem
install -o netdata -g netdata -m 0644 /run/pilot/server-cert.pem /etc/netdata/ssl/cert.pem

exec /usr/sbin/run.sh
