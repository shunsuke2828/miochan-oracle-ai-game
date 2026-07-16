#!/usr/bin/env python3
"""Align stored rescue titles with the current A–E rank title map."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.rescue import RANK_TITLES


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
                        select rank_label, title_label, count(*)
                        from mio_game_sessions
                        where rank_label in ('A', 'B', 'C', 'D', 'E')
                        group by rank_label, title_label
                        order by rank_label, title_label
                        """
                    )
                    before = cursor.fetchall()
                    print("current title distribution:")
                    for rank_label, title_label, count in before:
                        print(f"  {rank_label}: {title_label or '(null)'} = {int(count)}")
                    print(f"mode={'apply' if args.apply else 'dry-run'}")
                    if not args.apply:
                        connection.rollback()
                        return

                    updated = 0
                    for rank_label, title_label in RANK_TITLES.items():
                        cursor.execute(
                            """
                            update mio_game_sessions
                            set title_label = :title_label
                            where rank_label = :rank_label
                              and (title_label is null or title_label <> :title_label)
                            """,
                            title_label=title_label,
                            rank_label=rank_label,
                        )
                        updated += int(cursor.rowcount)

                    cursor.execute(
                        """
                        select count(*)
                        from mio_game_sessions
                        where rank_label in ('A', 'B', 'C', 'D', 'E')
                          and title_label <> case rank_label
                            when 'A' then 'みおちゃんの親友'
                            when 'B' then '頼れるレスキュー隊長'
                            when 'C' then '聞き上手レスキュー隊'
                            when 'D' then '見習いレスキュー隊'
                            when 'E' then 'はじめの一歩サポーター'
                          end
                        """
                    )
                    remaining = int(cursor.fetchone()[0])
                    if remaining:
                        raise RuntimeError(f"rank/title mismatches remain: {remaining}")
                connection.commit()
                print(f"rank title migration committed: updated={updated}")
            except Exception:
                connection.rollback()
                raise
    finally:
        repository.close()


if __name__ == "__main__":
    main()
