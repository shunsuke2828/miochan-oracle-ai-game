#!/usr/bin/env python3
"""Remove only the two integration-test sessions created by this repository."""

from __future__ import annotations

import getpass
import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    wallet = os.getenv(
        "MIO_ADB_WALLET_ZIP", "/home/opc/Wallet_WCDKUW08O7T8DAX7.zip"
    )
    user = os.getenv("MIO_ADB_USER", "admin")
    dsn = os.getenv("MIO_ADB_DSN", "wcdkuw08o7t8dax7_high")
    password = os.getenv("MIO_ADB_PASSWORD") or getpass.getpass("ADB password: ")
    escaped = password.replace('"', '""')
    sql = """
set heading off feedback off pagesize 0
whenever sqlerror exit sql.sqlcode rollback
delete from mio_demo_metrics
where session_id in (
  select session_id from mio_demo_sessions
  where nickname in ('ADB統合テスト', '最終動作確認')
);
delete from mio_demo_sessions
where nickname in ('ADB統合テスト', '最終動作確認');
commit;
select 'MIO_REMAINING:' || count(*) from mio_demo_sessions;
"""
    sql_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".sql", delete=False, dir="/tmp"
        ) as handle:
            sql_path = handle.name
            handle.write(sql)
        script = f'connect {user}/"{escaped}"@{dsn}\n@{sql_path}\nexit\n'
        completed = subprocess.run(
            ["sql", "-S", "-cloudconfig", wallet, "/nolog"],
            cwd=ROOT,
            input=script,
            text=True,
            check=False,
        )
        return completed.returncode
    finally:
        if sql_path:
            try:
                os.unlink(sql_path)
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())

