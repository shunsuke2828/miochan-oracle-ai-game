#!/usr/bin/env python3
from __future__ import annotations

import argparse
import array
import json
import os
import tempfile
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

import oracledb


TABLES = (
    "MIO_DEMO_BUSINESS_METRICS",
    "MIO_DEMO_CUSTOMERS",
    "MIO_DEMO_SESSIONS",
    "MIO_DEMO_MESSAGES",
    "MIO_DEMO_METRICS",
    "MIO_PLAYERS",
    "MIO_GAME_SESSIONS",
    "MIO_TURNS",
    "MIO_IDEAL_ANSWERS",
    "MIO_SCORE_EVENTS",
    "MIO_ANSWER_TEMPLATES",
)


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return {"$datetime": value.isoformat()}
    if isinstance(value, array.array):
        return {"$vector": list(value)}
    if hasattr(value, "read"):
        return value.read()
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    wallet_zip = Path(os.environ["MIO_ADB_WALLET_ZIP"])
    client_lib = Path(os.environ["MIO_ORACLE_CLIENT_LIB"])
    with tempfile.TemporaryDirectory(prefix="mio-source-wallet-") as wallet_dir:
        with zipfile.ZipFile(wallet_zip) as archive:
            archive.extractall(wallet_dir)
        if oracledb.is_thin_mode():
            os.environ["ORACLE_HOME"] = str(client_lib.parent)
            oracledb.init_oracle_client(lib_dir=str(client_lib), config_dir=wallet_dir)
        connection = oracledb.connect(
            user=os.getenv("MIO_ADB_USER", "admin"),
            password=os.environ["MIO_ADB_PASSWORD"],
            dsn=os.environ["MIO_ADB_DSN"],
        )
        payload: dict[str, Any] = {"format": 1, "tables": {}}
        try:
            with connection.cursor() as cursor:
                cursor.execute("select table_name from user_tables where table_name like 'MIO_%'")
                existing = {row[0] for row in cursor}
                for table in TABLES:
                    if table not in existing:
                        continue
                    cursor.execute(f"select * from {table}")
                    columns = [item[0] for item in cursor.description]
                    rows = [[_json_value(value) for value in row] for row in cursor]
                    payload["tables"][table] = {"columns": columns, "rows": rows}
                    print(f"exported {table}: {len(rows)} rows")
        finally:
            connection.close()
    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    args.output.chmod(0o600)


if __name__ == "__main__":
    main()
