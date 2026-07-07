#!/usr/bin/env python3
from __future__ import annotations

import getpass
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MIGRATION = ROOT / "db" / "migrations" / "001_mio_demo.sql"


def main() -> int:
    wallet = os.getenv(
        "MIO_ADB_WALLET_ZIP", "/home/opc/Wallet_WCDKUW08O7T8DAX7.zip"
    )
    user = os.getenv("MIO_ADB_USER", "admin")
    dsn = os.getenv("MIO_ADB_DSN", "wcdkuw08o7t8dax7_high")
    password = os.getenv("MIO_ADB_PASSWORD") or getpass.getpass("ADB password: ")
    if not Path(wallet).exists():
        print(f"Wallet not found: {wallet}", file=sys.stderr)
        return 2

    escaped_password = password.replace('"', '""')
    sql_input = (
        f'connect {user}/"{escaped_password}"@{dsn}\n'
        f'@{MIGRATION}\n'
        "exit\n"
    )
    completed = subprocess.run(
        ["sql", "-S", "-cloudconfig", wallet, "/nolog"],
        cwd=ROOT,
        input=sql_input,
        text=True,
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
