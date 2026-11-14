#!/usr/bin/env python3
"""Create the bounded runtime role without exposing credentials in command output."""

import argparse
from pathlib import Path
from urllib.parse import quote

import psycopg
from psycopg import sql


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner-password-file", type=Path, required=True)
    parser.add_argument("--runtime-password-file", type=Path, required=True)
    parser.add_argument("--owner-url-file", type=Path, required=True)
    parser.add_argument("--runtime-url-file", type=Path, required=True)
    args = parser.parse_args()
    owner = args.owner_password_file.read_text().strip()
    runtime = args.runtime_password_file.read_text().strip()
    owner_url = f"postgresql://nawari_owner:{quote(owner, safe='')}@postgres/nawari"
    args.owner_url_file.write_text(owner_url + "\n")
    args.owner_url_file.chmod(0o600)
    with psycopg.connect(owner_url) as connection:
        connection.execute("DO $$ BEGIN CREATE ROLE nawari_runtime LOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$")
        connection.execute(sql.SQL("ALTER ROLE nawari_runtime PASSWORD {}").format(sql.Literal(runtime)))
        connection.execute("GRANT CONNECT ON DATABASE nawari TO nawari_runtime")
        connection.execute("GRANT USAGE ON SCHEMA public TO nawari_runtime")
        connection.execute("REVOKE CREATE ON SCHEMA public FROM nawari_runtime")
        connection.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO nawari_runtime")
        connection.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO nawari_runtime")
        connection.execute("ALTER DEFAULT PRIVILEGES FOR ROLE nawari_owner IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO nawari_runtime")
        connection.execute("ALTER DEFAULT PRIVILEGES FOR ROLE nawari_owner IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO nawari_runtime")
    args.runtime_url_file.write_text(
        f"postgresql://nawari_runtime:{quote(runtime, safe='')}@postgres/nawari\n"
    )
    args.runtime_url_file.chmod(0o600)


if __name__ == "__main__":
    main()
