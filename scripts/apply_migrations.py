#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import tempfile
import zipfile
from pathlib import Path

import oracledb


ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = ROOT / "db" / "migrations"


def _clean_sqlplus_lines(text: str) -> str:
    return "\n".join(
        line
        for line in text.splitlines()
        if not re.match(
            r"^\s*(?:set\s+(?:define|serveroutput)|whenever|prompt)\b",
            line,
            re.IGNORECASE,
        )
    )


def _statements(path: Path) -> list[str]:
    text = _clean_sqlplus_lines(path.read_text(encoding="utf-8"))
    statements: list[str] = []
    buffer: list[str] = []
    for line in text.splitlines():
        if line.strip() == "/":
            statement = "\n".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer = []
        else:
            buffer.append(line)
    tail = "\n".join(buffer).strip()
    if tail:
        statements.extend(part.strip() for part in tail.split(";") if part.strip())
    return statements


def main() -> None:
    wallet_zip = Path(os.environ["MIO_ADB_WALLET_ZIP"])
    wallet_password = os.environ["MIO_ADB_WALLET_PASSWORD"]
    with tempfile.TemporaryDirectory(prefix="mio-wallet-") as wallet_dir:
        with zipfile.ZipFile(wallet_zip) as archive:
            archive.extractall(wallet_dir)
        connection = oracledb.connect(
            user=os.getenv("MIO_ADB_USER", "admin"),
            password=os.environ["MIO_ADB_PASSWORD"],
            dsn=os.environ["MIO_ADB_DSN"],
            config_dir=wallet_dir,
            wallet_location=wallet_dir,
            wallet_password=wallet_password,
        )
        try:
            with connection.cursor() as cursor:
                for migration in sorted(MIGRATIONS.glob("*.sql")):
                    for statement in _statements(migration):
                        cursor.execute(statement)
                    connection.commit()
                    print(f"applied {migration.name}")
        finally:
            connection.close()


if __name__ == "__main__":
    main()
