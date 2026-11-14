#!/bin/sh
set -eu

version="${1:-0.1.0}"
arch="${NAWARI_ARCH:-$(uname -m)}"
[ "$arch" = "x86_64" ] && arch="amd64"
[ "$arch" = "aarch64" ] && arch="arm64"
case "$arch" in arm64|amd64) ;; *) printf 'Unsupported architecture: %s\n' "$arch" >&2; exit 2 ;; esac

root="$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)"
out="$root/artifacts/packages/$version"
work="$(mktemp -d "${TMPDIR:-/tmp}/nawari-macos.XXXXXX")"
trap 'rm -rf "$work"' EXIT INT TERM
payload="$work/payload/usr/local/libexec/nawari"
scripts="$work/scripts"
mkdir -p "$payload" "$scripts" "$out"

(cd "$root/collectors/nawari" && go test ./...)
(cd "$root/collectors/nawari" && GOOS=darwin GOARCH="$arch" go build -trimpath -ldflags "-s -w" -o "$work/nawari.plugin" .)
cp -X "$work/nawari.plugin" "$payload/nawari.plugin"
cp -X "$root/packaging/nawari-collector.example.json" "$payload/"
cp -X "$root/packaging/macos/install.sh" "$scripts/postinstall"
cp -X "$root/packaging/macos/uninstall.sh" "$payload/"
chmod 0755 "$payload/nawari.plugin" "$scripts/postinstall" "$payload/uninstall.sh"
find "$work/payload" -name '._*' -type f -delete
xattr -cr "$work/payload" 2>/dev/null || true

application_status="unsigned-development"
installer_status="unsigned-development"
if [ -n "${APPLICATION_IDENTITY:-}" ]; then
  codesign --force --options runtime --timestamp --sign "$APPLICATION_IDENTITY" "$payload/nawari.plugin"
  application_status="signed"
fi

pkg="$out/Nawari-Netdata-macOS-$arch-$version.pkg"
COPYFILE_DISABLE=1 pkgbuild --root "$work/payload" --scripts "$scripts" --identifier com.nawari.netdata \
  --version "$version" --install-location / --ownership recommended "$pkg"
if [ -n "${INSTALLER_IDENTITY:-}" ]; then
  signed="$work/signed.pkg"
  productsign --sign "$INSTALLER_IDENTITY" "$pkg" "$signed"
  mv "$signed" "$pkg"
  installer_status="signed"
fi
notarization_status="not-submitted"
if [ -n "${NOTARY_PROFILE:-}" ]; then
  xcrun notarytool submit "$pkg" --keychain-profile "$NOTARY_PROFILE" --wait
  xcrun stapler staple "$pkg"
  xcrun stapler validate "$pkg"
  notarization_status="stapled"
fi
if [ "${REQUIRE_SIGNING:-0}" = "1" ] && { [ "$application_status" != "signed" ] || [ "$installer_status" != "signed" ] || [ "$notarization_status" != "stapled" ]; }; then
  printf 'Production release blocked: Developer ID application/installer signing and notarization are required.\n' >&2
  exit 1
fi

(cd "$out" && shasum -a 256 "$(basename "$pkg")" > "$(basename "$pkg").sha256")
cat > "$out/$(basename "$pkg").manifest.json" <<EOF
{"package":"$(basename "$pkg")","version":"$version","architecture":"$arch","netdata_version":"2.12.3","collector_application_signing":"$application_status","installer_signing":"$installer_status","notarization":"$notarization_status"}
EOF
printf 'Created %s (application=%s installer=%s notarization=%s)\n' "$pkg" "$application_status" "$installer_status" "$notarization_status"
