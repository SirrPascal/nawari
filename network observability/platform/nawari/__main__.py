"""Local and container entry points. Secrets are read from private files."""

import argparse
import json
import os
from pathlib import Path
import sys
import time
import urllib.request

from .fixtures import seed
from .netdata import NetdataAdapter
from .server import make_server
from .store import Store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["migrate", "fixture", "serve", "worker", "purge", "revoke", "provision", "operator", "operation", "discover-netdata"])
    parser.add_argument("--database", default=os.environ.get("NAWARI_DATABASE", "runtime/nawari.db"))
    parser.add_argument("--directory", default="runtime")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18090)
    parser.add_argument("--fixture-mode", action="store_true")
    parser.add_argument("--tenant")
    parser.add_argument("--enrollment")
    parser.add_argument("--asset")
    parser.add_argument("--site")
    parser.add_argument("--routing-domain")
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--definition", type=Path)
    parser.add_argument("--netdata-url", default=os.environ.get("NAWARI_NETDATA_URL"))
    parser.add_argument("--netdata-node-guid")
    args = parser.parse_args()
    configured_database = bool(os.environ.get("NAWARI_DATABASE") or os.environ.get("NAWARI_DATABASE_FILE") or "--database" in sys.argv)
    if os.environ.get("NAWARI_DATABASE_FILE"):
        args.database = Path(os.environ["NAWARI_DATABASE_FILE"]).read_text().strip()
    if args.command in {"serve", "worker"} and not args.fixture_mode:
        if not configured_database or not str(args.database).startswith(("postgresql://", "postgres://")):
            parser.error("production serve/worker requires an explicit PostgreSQL database configuration")
    auto_migrate = os.environ.get("NAWARI_AUTO_MIGRATE", "1") == "1"
    store = Store(args.database, migrate=auto_migrate)
    if args.command == "fixture":
        seed(store, args.directory)
        print("Created labeled fixture data and restricted local enrollment files.")
    elif args.command == "serve":
        adapter = NetdataAdapter(args.netdata_url) if args.netdata_url else None
        server = make_server(store, args.host, args.port, args.fixture_mode, netdata=adapter)
        print(f"Nawari listening on {args.host}:{args.port}, fixture={args.fixture_mode}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    elif args.command == "purge":
        print(json.dumps(store.purge()))
    elif args.command == "revoke":
        store.revoke(args.tenant, args.enrollment)
    elif args.command == "provision":
        if not all([args.tenant, args.enrollment, args.asset, args.site, args.routing_domain, args.token_file]):
            parser.error("provision requires tenant, enrollment, asset, site, routing-domain and token-file")
        store.provision(args.tenant, args.enrollment, "nawari-plugin", args.enrollment,
                        args.asset, args.site, args.routing_domain, args.token_file.read_text().strip())
    elif args.command == "operator":
        if not args.tenant or not args.token_file:
            parser.error("operator requires tenant and token-file")
        store.operator(args.token_file.read_text().strip(), args.tenant)
    elif args.command == "operation":
        if not args.tenant or not args.definition:
            parser.error("operation requires tenant and definition")
        store.put_operation(args.tenant, json.loads(args.definition.read_text()))
    elif args.command == "discover-netdata":
        if not args.tenant or not args.asset or not args.netdata_url:
            parser.error("discover-netdata requires tenant, asset and netdata-url")
        result = store.refresh_metric_catalogue(
            args.tenant,
            args.asset,
            NetdataAdapter(args.netdata_url, node_guid=args.netdata_node_guid),
        )
        print(json.dumps(result))
    elif args.command == "worker":
        def loki(item):
            destination = os.environ.get("NAWARI_LOKI_URL")
            if not destination:
                raise OSError("loki_unconfigured")
            if item["expires_at"] <= time.time():
                raise ValueError("expired")
            body = json.loads(item["body"])
            event = json.dumps({"record_id": item["record_id"], "payload": body["payload"]}, separators=(",", ":"))
            payload = {"streams": [{"stream": {"source": "nawari", "tenant": item["tenant"]},
                                    "values": [[str(int(item["observed_at"] * 1e9)), event]]}]}
            request = urllib.request.Request(destination, data=json.dumps(payload).encode(),
                                             headers={"Content-Type": "application/json", "X-Scope-OrgID": item["tenant"]})
            with urllib.request.urlopen(request, timeout=5) as response:
                if response.status != 204:
                    raise OSError("loki_rejected")
        while True:
            if not store.process_one(loki):
                time.sleep(1)


if __name__ == "__main__":
    main()
