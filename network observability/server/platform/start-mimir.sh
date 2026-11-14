#!/bin/sh
set -eu
MINIO_ACCESS_KEY="$(cat /run/secrets/minio_root_user)"
MINIO_SECRET_KEY="$(cat /run/secrets/minio_root_password)"
export MINIO_ACCESS_KEY MINIO_SECRET_KEY
exec /bin/mimir -config.file=/etc/mimir/mimir.yaml -config.expand-env=true
