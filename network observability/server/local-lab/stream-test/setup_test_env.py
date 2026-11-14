#!/usr/bin/env python3
"""
setup_test_env.py

Reproducibly generates the isolated Netdata streaming test certificates,
API keys, and configuration files from templates into runtime/.

Guarantees:
- Strict SAN inclusion (DNS:netdata-stream-test-parent, DNS:nawari-stream-test-parent, DNS:localhost, IP:127.0.0.1)
- Fresh UUIDv4 streaming API key (stored in git-ignored .stream-key.env)
- Correct file permissions (0700 dir, 0600 keys/confs, 0644 certs)
- Idempotent unless --rotate is passed
"""

import argparse
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
RUNTIME_DIR = BASE_DIR / "runtime"


def run_cmd(cmd: list[str], cwd: Path | None = None) -> str:
    res = subprocess.run(
        cmd,
        cwd=cwd or BASE_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if res.returncode != 0:
        raise RuntimeError(f"Command failed ({res.returncode}): {' '.join(cmd)}\n{res.stderr}")
    return res.stdout


def setup_environment(rotate: bool = False) -> None:
    RUNTIME_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(RUNTIME_DIR, 0o700)

    # 1. API Key Generation / Loading
    key_file = RUNTIME_DIR / ".stream-key.env"
    if rotate or not key_file.exists():
        api_key = str(uuid.uuid4())
        key_file.write_text(f"STREAMING_API_KEY={api_key}\n")
        key_file.chmod(0o600)
    else:
        content = key_file.read_text()
        for line in content.splitlines():
            if line.startswith("STREAMING_API_KEY="):
                api_key = line.split("=", 1)[1].strip()
                break
        else:
            api_key = str(uuid.uuid4())
            key_file.write_text(f"STREAMING_API_KEY={api_key}\n")
            key_file.chmod(0o600)

    # 2. Extensions config
    ext_src = TEMPLATES_DIR / "extensions.conf.template"
    ext_dst = RUNTIME_DIR / "extensions.conf"
    shutil.copy2(ext_src, ext_dst)
    ext_dst.chmod(0o644)

    # 3. CA Certificate & Key
    ca_key = RUNTIME_DIR / "ca-key.pem"
    ca_cert = RUNTIME_DIR / "ca-cert.pem"
    if rotate or not (ca_key.exists() and ca_cert.exists()):
        run_cmd([
            "openssl", "req", "-new", "-x509", "-nodes",
            "-newkey", "rsa:2048",
            "-keyout", str(ca_key),
            "-out", str(ca_cert),
            "-days", "365",
            "-subj", "/CN=Nawari Stream Test CA/O=Nawari Lab"
        ])
        ca_key.chmod(0o600)
        ca_cert.chmod(0o644)

    # 4. Server Certificate & Key
    server_key = RUNTIME_DIR / "server-key.pem"
    server_csr = RUNTIME_DIR / "server.csr"
    server_cert = RUNTIME_DIR / "server-cert.pem"
    if rotate or not (server_key.exists() and server_cert.exists()):
        run_cmd([
            "openssl", "req", "-new", "-nodes",
            "-newkey", "rsa:2048",
            "-keyout", str(server_key),
            "-out", str(server_csr),
            "-subj", "/CN=netdata-stream-test-parent/O=Nawari Lab"
        ])
        server_key.chmod(0o600)
        server_csr.chmod(0o644)

        run_cmd([
            "openssl", "x509", "-req",
            "-in", str(server_csr),
            "-CA", str(ca_cert),
            "-CAkey", str(ca_key),
            "-CAcreateserial",
            "-out", str(server_cert),
            "-days", "365",
            "-extfile", str(ext_dst)
        ])
        server_cert.chmod(0o644)

    # 5. Verify Certificate
    verify_out = run_cmd(["openssl", "verify", "-CAfile", str(ca_cert), str(server_cert)])
    if "OK" not in verify_out:
        raise RuntimeError(f"Certificate verification failed: {verify_out}")

    # 6. Render stream.conf templates
    child_tpl = (TEMPLATES_DIR / "child-stream.conf.template").read_text()
    parent_tpl = (TEMPLATES_DIR / "parent-stream.conf.template").read_text()

    child_conf = RUNTIME_DIR / "child-stream.conf"
    parent_conf = RUNTIME_DIR / "parent-stream.conf"

    child_conf.write_text(child_tpl.replace("{{STREAMING_API_KEY}}", api_key))
    parent_conf.write_text(parent_tpl.replace("{{STREAMING_API_KEY}}", api_key))
    child_conf.chmod(0o600)
    parent_conf.chmod(0o600)

    # 7. Copy netdata.conf files
    for name in ["child-netdata.conf", "parent-netdata.conf"]:
        src = TEMPLATES_DIR / name
        dst = RUNTIME_DIR / name
        shutil.copy2(src, dst)
        dst.chmod(0o644)

    print("Successfully configured isolated test environment in runtime/.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Setup isolated Netdata stream-test environment")
    parser.add_argument("--rotate", action="store_true", help="Rotate all certificates and keys")
    args = parser.parse_args()
    setup_environment(rotate=args.rotate)

