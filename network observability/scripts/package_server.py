"""Build a server deployment archive containing code and configuration templates."""

import argparse
import tarfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
FILES = (
    "server/compose.yaml",
    "server/start-parent.sh",
    "server/README.md",
    "scripts/prepare_server.py",
    "scripts/verify_parent.py",
)


def build_archive(output):
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w:gz") as archive:
        for name in FILES:
            source = PROJECT / name
            if not source.is_file() or source.is_symlink():
                raise ValueError(f"Missing deployment source {name}")
            archive.add(source, arcname=name, recursive=False)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=PROJECT / "dist/network-pilot.tar.gz")
    args = parser.parse_args()
    print(build_archive(args.output))


if __name__ == "__main__":
    main()
