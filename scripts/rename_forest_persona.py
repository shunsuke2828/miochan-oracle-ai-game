#!/usr/bin/env python3
"""Rename the former forest-explorer persona without changing user answers."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OLD_NAME = "森の探検家タイプ"
NEW_NAME = "クマタイプ"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    os.environ["MIO_DATA_MODE"] = "adb"
    from app.config import Settings
    from app.database import AdbRepository

    repository = AdbRepository(Settings())
    try:
        with repository.connection() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        select
                          sum(case when persona_name = :old_name then 1 else 0 end),
                          sum(case when persona_name = :new_name then 1 else 0 end)
                        from mio_demo_sessions
                        """,
                        old_name=OLD_NAME,
                        new_name=NEW_NAME,
                    )
                    old_count, existing_new_count = cursor.fetchone()
                    old_count = int(old_count or 0)
                    existing_new_count = int(existing_new_count or 0)
                    print(
                        f"validated old={old_count} existing_new={existing_new_count} "
                        f"mode={'apply' if args.apply else 'dry-run'}"
                    )
                    if not args.apply:
                        connection.rollback()
                        return

                    cursor.execute(
                        """
                        update mio_demo_sessions
                        set persona_name = :new_name
                        where persona_name = :old_name
                        """,
                        new_name=NEW_NAME,
                        old_name=OLD_NAME,
                    )
                    updated = int(cursor.rowcount)
                    if updated != old_count:
                        raise RuntimeError(
                            f"expected to update {old_count} rows, updated {updated}"
                        )
                    cursor.execute(
                        "select count(*) from mio_demo_sessions where persona_name = :old_name",
                        old_name=OLD_NAME,
                    )
                    remaining = int(cursor.fetchone()[0])
                    if remaining:
                        raise RuntimeError(f"old persona remains on {remaining} rows")
                connection.commit()
                print(f"rename committed: updated={updated} new_name={NEW_NAME}")
            except Exception:
                connection.rollback()
                raise
    finally:
        repository.close()


if __name__ == "__main__":
    main()
