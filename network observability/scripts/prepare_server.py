"""Prepare persistent pilot enrollment and TLS files on the deployment server."""

import argparse
import ipaddress
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


def validate_address(value):
    try:
        address = ipaddress.ip_address(value)
        if address.version != 4:
            raise ValueError("This pilot deployment uses an IPv4 server address")
        return str(address), f"IP:{address}"
    except ValueError:
        if len(value) <= 253 and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", value):
            if all(
                part and len(part) <= 63 and not part.startswith("-") and not part.endswith("-")
                for part in value.split(".")
            ):
                return value, f"DNS:{value}"
        raise ValueError("Use an IPv4 address or DNS hostname") from None


def openssl(*args):
    result = subprocess.run(["openssl", *map(str, args)], capture_output=True, text=True)
    if result.returncode:
        # OpenSSL commands operate on key files. Keep their raw output out of logs.
        raise RuntimeError("OpenSSL preparation failed")


def write_private(path, text):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(text)


def prepare(output, address, bind_address, allow_from):
    address, san = validate_address(address)
    bind_address = str(ipaddress.IPv4Address(bind_address))
    if not allow_from or not re.fullmatch(r"[A-Za-z0-9.*:/ _-]+", allow_from):
        raise ValueError("Invalid collector source allowlist")
    settings = {"address": address, "bind_address": bind_address, "allow_from": allow_from}
    if output.exists():
        if json.loads((output / "settings.json").read_text()) != settings:
            raise ValueError(
                "Existing enrollment differs from these settings. Review the existing deployment first."
            )
        for name in (
            "stream.conf",
            "netdata.conf",
            "server-key.pem",
            "server-cert.pem",
            "ca-cert.pem",
            "macos-stream.conf",
        ):
            if not (output / name).is_file():
                raise ValueError("Existing runtime is incomplete")
        openssl("x509", "-in", output / "server-cert.pem", "-checkend", "86400", "-noout")
        return False
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".netdata-prepare-", dir=output.parent))
    try:
        key = str(uuid.uuid4())
        openssl(
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "365",
            "-subj",
            "/CN=Nawari Network Pilot CA",
            "-keyout",
            temporary / "ca-key.pem",
            "-out",
            temporary / "ca-cert.pem",
            "-addext",
            "basicConstraints=critical,CA:TRUE",
            "-addext",
            "keyUsage=critical,keyCertSign,cRLSign",
        )
        openssl(
            "req",
            "-new",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-subj",
            f"/CN={address}",
            "-keyout",
            temporary / "server-key.pem",
            "-out",
            temporary / "server.csr",
        )
        write_private(
            temporary / "extensions.conf",
            f"subjectAltName={san}\nbasicConstraints=critical,CA:FALSE\nextendedKeyUsage=serverAuth\nkeyUsage=critical,digitalSignature,keyEncipherment\n",
        )
        openssl(
            "x509",
            "-req",
            "-in",
            temporary / "server.csr",
            "-CA",
            temporary / "ca-cert.pem",
            "-CAkey",
            temporary / "ca-key.pem",
            "-CAcreateserial",
            "-days",
            "30",
            "-extfile",
            temporary / "extensions.conf",
            "-out",
            temporary / "server-cert.pem",
        )
        write_private(
            temporary / "stream.conf",
            f"[{key}]\n    type = api\n    enabled = yes\n    allow from = {allow_from}\n    db = dbengine\n    health enabled = yes\n",
        )
        write_private(
            temporary / "netdata.conf",
            """[global]
    hostname = nawari-network-parent
    update every = 15
[db]
    db = dbengine
    storage tiers = 1
    dbengine tier 0 retention time = 7d
    dbengine tier 0 retention size = 1GiB
[plugins]
    proc = no
    diskspace = no
    cgroups = no
    apps = no
    ebpf = no
    go.d = no
[web]
    bind to = *:19999=streaming^SSL=force *:20000=dashboard^SSL=optional
    ssl key = /etc/netdata/ssl/key.pem
    ssl certificate = /etc/netdata/ssl/cert.pem
[health]
    enabled = yes
""",
        )
        write_private(
            temporary / "macos-stream.conf",
            f"[stream]\n    enabled = yes\n    destination = {address}:19999:SSL\n    api key = {key}\n    ssl skip certificate verification = no\n    send charts matching = net.* ipv4.* dns_query.* ping.* httpcheck.* system.uptime\n    CAfile = /REPLACE_WITH_ABSOLUTE_PATH/pilot-ca-cert.pem\n",
        )
        write_private(temporary / "settings.json", json.dumps(settings, indent=2) + "\n")
        write_private(
            temporary / ".env",
            f"NETDATA_BIND_ADDRESS={bind_address}\nNETDATA_IMAGE=netdata/netdata:v2.12.3\nNETDATA_DASHBOARD_PORT=19998\n",
        )
        for path in temporary.iterdir():
            path.chmod(0o600)
        temporary.rename(output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", required=True)
    parser.add_argument("--bind-address", default="127.0.0.1")
    parser.add_argument("--allow-from", default="*")
    parser.add_argument("--output", type=Path, default=PROJECT / "server/runtime")
    args = parser.parse_args()
    try:
        created = prepare(args.output, args.address, args.bind_address, args.allow_from)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"Preparation failed: {exc}\n")
    print(
        "Created pilot enrollment and TLS files."
        if created
        else "Reused existing enrollment and TLS files."
    )
    print(f"Runtime directory: {args.output}")


if __name__ == "__main__":
    main()
