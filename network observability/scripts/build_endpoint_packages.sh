#!/bin/sh
set -eu

version="${1:-0.1.0-local}"
project="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
output="$project/artifacts/packages/$version"
work="$(mktemp -d /tmp/nawari-package.XXXXXX)"
trap 'rm -rf "$work"' EXIT INT TERM
mkdir -p "$output" "$work/macos" "$work/windows"

cd "$project/collectors/nawari"
go test ./...
GOOS=darwin GOARCH=arm64 go build -trimpath -ldflags "-s -w" -o "$work/macos/nawari.plugin" .
GOOS=windows GOARCH=amd64 go build -trimpath -ldflags "-s -w" -o "$work/windows/nawari.plugin.exe" .
cp "$project/packaging/macos/install.sh" "$project/packaging/macos/uninstall.sh" "$project/packaging/macos/rollback.sh" "$project/packaging/macos/health-check.sh" "$work/macos/"
cp "$project/packaging/nawari-collector.example.json" "$work/macos/"
cp "$project/packaging/nawari-collector.example.json" "$work/windows/"
cp "$project/packaging/windows/Install-NetdataNawari.ps1" "$project/packaging/windows/Detect-NetdataNawari.ps1" "$project/packaging/windows/Uninstall-NetdataNawari.ps1" "$project/packaging/windows/README.md" "$work/windows/"
printf '%s\n' 'Windows binary is build-only evidence. Netdata service integration and install/rollback require a Windows runtime acceptance host.' > "$work/windows/ACCEPTANCE-STATUS.txt"
chmod 0755 "$work/macos/install.sh" "$work/macos/uninstall.sh" "$work/macos/rollback.sh" "$work/macos/health-check.sh" "$work/macos/nawari.plugin"

tar -C "$work/macos" -czf "$output/nawari-endpoint-macos-arm64-$version.tar.gz" .
(cd "$work/windows" && zip -q "$output/nawari-endpoint-windows-amd64-$version.zip" ./*)
(cd "$output" && shasum -a 256 nawari-endpoint-*) > "$output/SHA256SUMS"
printf 'Packages written to %s\n' "$output"
