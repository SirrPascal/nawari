"""Upload and start the isolated Netdata Parent pilot through SSH."""

import argparse
import ipaddress
import re
import shlex
import subprocess
import uuid
from pathlib import Path

from package_server import PROJECT, build_archive
from prepare_server import validate_address


def validate_destination(target, directory):
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.@-]*", target):
        raise ValueError("Use an SSH alias or user@IPv4/hostname")
    if not re.fullmatch(r"/?[A-Za-z0-9_][A-Za-z0-9_./-]*", directory):
        raise ValueError("Use a deployment path without spaces or shell characters")
    if ".." in Path(directory).parts:
        raise ValueError("Deployment paths cannot traverse parent directories")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--address", required=True)
    parser.add_argument("--remote-dir", default="nawari-network-pilot")
    parser.add_argument("--identity", type=Path)
    parser.add_argument("--control-socket", type=Path, help="Reuse an authenticated SSH connection")
    parser.add_argument("--allow-from", default="*")
    parser.add_argument("--bind-address")
    parser.add_argument("--sudo-docker", action="store_true")
    parser.add_argument(
        "--batch", action="store_true", help="Fail instead of prompting for SSH authentication"
    )
    args = parser.parse_args()
    try:
        validate_destination(args.target, args.remote_dir)
        address, _ = validate_address(args.address)
    except ValueError as exc:
        parser.error(str(exc))
    options = ["-o", "ConnectTimeout=10"]
    if args.batch:
        options += ["-o", "BatchMode=yes"]
    if args.identity:
        options += ["-i", str(args.identity.expanduser().resolve())]
    if args.control_socket:
        options += ["-o", f"ControlPath={args.control_socket.expanduser().resolve()}"]

    def remote(command):
        subprocess.run(["ssh", *options, args.target, command], check=True)

    docker = "sudo -n docker" if args.sudo_docker else "docker"
    directory = shlex.quote(args.remote_dir)
    try:
        remote(
            f"command -v python3 && command -v openssl && {docker} info >/dev/null && {docker} compose version && mkdir -p -- {directory}"
        )
        archive = build_archive(PROJECT / "dist/network-pilot.tar.gz")
        upload = args.remote_dir.rstrip("/") + f"/.pilot-upload-{uuid.uuid4().hex}.tar.gz"
        subprocess.run(["scp", *options, str(archive), f"{args.target}:{upload}"], check=True)
        # The uploaded archive contains only the fixed allowlist in package_server.
        remote(f"tar -xzf {shlex.quote(upload)} -C {directory} && rm -- {shlex.quote(upload)}")
        bind_address = args.bind_address
        if not bind_address:
            try:
                bind_address = str(ipaddress.IPv4Address(address))
            except ValueError:
                bind_address = "0.0.0.0"
        preparation = shlex.join(
            [
                "python3",
                "scripts/prepare_server.py",
                "--address",
                address,
                "--bind-address",
                bind_address,
                "--allow-from",
                args.allow_from,
            ]
        )
        remote(f"cd {directory} && {preparation}")
        compose = f"{docker} compose --env-file runtime/.env -f compose.yaml"
        remote(
            f"cd {directory}/server && {compose} config --quiet && {compose} up -d --wait --wait-timeout 90"
        )
        remote(f"cd {directory} && python3 scripts/verify_parent.py")
    except subprocess.CalledProcessError as exc:
        parser.exit(
            1,
            f"Deployment stopped at a failed command (exit {exc.returncode}). Existing volumes were retained.\n",
        )
    print("Parent deployment is healthy. Enroll the Mac and verify streamed measurements next.")


if __name__ == "__main__":
    main()
