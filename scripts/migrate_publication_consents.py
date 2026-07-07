#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    os.environ["MIO_DATA_MODE"] = "adb"
    from app.config import Settings
    from app.database import AdbRepository

    repository = AdbRepository(Settings())
    try:
        with repository.connection() as connection:
            with connection.cursor() as cursor:
                try:
                    cursor.execute(
                        "alter table mio_demo_sessions "
                        "add (ranking_consent number(1) default 0 not null)"
                    )
                except Exception as exc:
                    if getattr(exc, "args", None) and getattr(exc.args[0], "code", None) != 1430:
                        raise
                cursor.execute(
                    "update mio_demo_sessions set ranking_consent = 0 "
                    "where ranking_consent is null"
                )
            connection.commit()
        print("Publication consent migration complete — existing ranking consent disabled")
    finally:
        repository.close()


if __name__ == "__main__":
    main()
