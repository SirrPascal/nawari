# Local investigation slice

## Prerequisites

- Python 3.13
- Go 1.25 or newer for the compiled collector
- Node 24 and npm
- Google Chrome for browser tests

## Build and verify

```sh
cd "/Users/madeira/Desktop/Projects/nawari/network observability/platform"
python3.13 -m unittest discover -s tests -v

cd web
npm ci
npm run build

cd "../../collectors/nawari"
go test -race ./...
go vet ./...
go build -trimpath -o ../../platform/runtime/nawari.plugin .
```

On macOS, opt in to a read-only live default-route and resolver check. It runs local system queries and does not send a service request to the test address.

```sh
NAWARI_LIVE_CONTEXT_TEST=1 go test -run TestLiveDefaultRouteContext -v
```

## Run the controlled slice

Use a disposable directory so tokens and fixture evidence remain outside the source tree.

```sh
cd "/Users/madeira/Desktop/Projects/nawari/network observability/platform"
NAWARI_SLICE_TMP="$(mktemp -d /tmp/nawari-slice.XXXXXX)"
python3.13 -m nawari fixture \
  --database "$NAWARI_SLICE_TMP/nawari.db" \
  --directory "$NAWARI_SLICE_TMP"
python3.13 -m nawari serve \
  --database "$NAWARI_SLICE_TMP/nawari.db" \
  --host 127.0.0.1 --port 18090 --fixture-mode
```

Open `http://127.0.0.1:18090`. The yellow banner identifies the controlled fixture workspace. Stop the process with Ctrl+C. Delete only the explicitly printed disposable directory after inspection.

Run browser acceptance while the fixture server is active.

```sh
cd "/Users/madeira/Desktop/Projects/nawari/network observability/platform/web"
npm test
```

## Local collector execution

Start the existing loopback fixture service in a separate terminal. Use the private collector configuration created by the fixture seed command.

```sh
cd "/Users/madeira/Desktop/Projects/nawari/network observability"
python3 scripts/fixture_service.py
```

Then run one bounded collector cycle.

```sh
"/Users/madeira/Desktop/Projects/nawari/network observability/platform/runtime/nawari.plugin" \
  --config "$NAWARI_SLICE_TMP/collector.json" --once
```

The plugin writes the Netdata external-plugin protocol to standard output. The fixture build has also completed a local Homebrew Netdata lifecycle test; repeat that test for every signed release and supported OS.

## Reproduce packages and source snapshot

Build checksum-addressed macOS and Windows artifacts. The Windows artifact is build-only evidence until exercised on Windows.

```sh
cd "/Users/madeira/Desktop/Projects/nawari"
"network observability/scripts/build_endpoint_packages.sh" 0.1.0-local
```

Create a deterministic snapshot that includes relocated and currently untracked source but excludes runtime state, credentials, keys and generated packages.

```sh
"network observability/scripts/snapshot_local_milestone.py" \
  --output "network observability/artifacts/snapshots/nawari-local-milestone-0.1.0.tar.gz"
```

The macOS installer refuses a Netdata version other than `2.12.3`, backs up an existing plugin/configuration, and never overwrites an existing configuration. Review and replace every placeholder before restarting Netdata.
