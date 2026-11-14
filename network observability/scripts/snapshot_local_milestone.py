#!/usr/bin/env python3
"""Create a deterministic, secret-excluding source snapshot of the dirty milestone."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile


EXCLUDED_PARTS = {".git", "node_modules", "dist", "runtime", "artifacts", "__pycache__", ".pytest_cache"}
EXCLUDED_NAMES = {".DS_Store", ".env"}
EXCLUDED_SUFFIXES = {".key", ".pem", ".p12", ".pfx"}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def tool(root: Path, *command: str) -> str:
    try:
        return subprocess.check_output(command, cwd=root, text=True, stderr=subprocess.STDOUT, timeout=10).strip()
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def include(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    return (
        path.is_file()
        and not EXCLUDED_PARTS.intersection(relative.parts)
        and path.name not in EXCLUDED_NAMES
        and path.suffix.lower() not in EXCLUDED_SUFFIXES
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    files = sorted(path for path in root.rglob("*") if include(path, root))
    entries = [{"path": str(path.relative_to(root)), "sha256": digest(path), "bytes": path.stat().st_size} for path in files]
    manifest = {
        "schema_version": 1,
        "scope": "local_source_snapshot_without_secrets_or_runtime_data",
        "git_head": git(root, "rev-parse", "HEAD"),
        "git_branch": git(root, "branch", "--show-current"),
        "toolchain": {
            "python": tool(root, "python3.13", "--version"),
            "go": tool(root, "go", "version"),
            "node": tool(root, "node", "--version"),
            "npm": tool(root, "npm", "--version"),
            "docker": tool(root, "docker", "--version"),
            "docker_compose": tool(root, "docker", "compose", "version"),
            "netdata": tool(root, "/opt/homebrew/sbin/netdata", "-v"),
        },
        "tracked_deletions": git(root, "diff", "--name-only", "--diff-filter=D").splitlines(),
        "files": entries,
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for path in files:
                    info = archive.gettarinfo(str(path), arcname=str(path.relative_to(root)))
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    info.mtime = 0
                    with path.open("rb") as stream:
                        archive.addfile(info, stream)
                info = tarfile.TarInfo("SOURCE-MANIFEST.json")
                info.size = len(manifest_bytes)
                info.mode = 0o644
                info.mtime = 0
                archive.addfile(info, io.BytesIO(manifest_bytes))
    checksum = digest(output)
    output.with_suffix(output.suffix + ".sha256").write_text(f"{checksum}  {output.name}\n")
    print(json.dumps({"archive": str(output), "sha256": checksum, "files": len(files)}, sort_keys=True))


if __name__ == "__main__":
    main()
