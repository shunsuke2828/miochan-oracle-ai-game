#!/usr/bin/env python3
"""Replace the former fictional venue seeds with approved completed sessions."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OLD_SEED_IDS = tuple(f"seed-{index:02d}" for index in range(1, 7))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="commit the replacement; without this option only validation is run",
    )
    args = parser.parse_args()

    os.environ["MIO_DATA_MODE"] = "adb"
    from app.config import Settings
    from app.database import AdbRepository
    from app.personas import SEED_PARTICIPANTS

    expected = {
        session_id: (nickname, answer, persona)
        for session_id, nickname, answer, persona in SEED_PARTICIPANTS
    }
    all_ids = (*OLD_SEED_IDS, *expected)
    placeholders = ",".join(f":id{index}" for index in range(len(all_ids)))
    parameters = {f"id{index}": value for index, value in enumerate(all_ids)}

    repository = AdbRepository(Settings())
    try:
        with repository.connection() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"""
                        select session_id, nickname, persona_name, is_seed
                        from mio_demo_sessions
                        where session_id in ({placeholders})
                        """,
                        parameters,
                    )
                    rows = {
                        row[0]: {
                            "nickname": row[1],
                            "persona": row[2],
                            "is_seed": bool(row[3]),
                        }
                        for row in cursor.fetchall()
                    }

                    missing = sorted(set(expected) - set(rows))
                    mismatched = [
                        session_id
                        for session_id, (nickname, _answer, persona) in expected.items()
                        if session_id in rows
                        and (
                            rows[session_id]["nickname"] != nickname
                            or rows[session_id]["persona"] != persona
                        )
                    ]
                    if missing or mismatched:
                        raise RuntimeError(
                            f"seed validation failed: missing={missing} mismatched={mismatched}"
                        )

                    old_present = [session_id for session_id in OLD_SEED_IDS if session_id in rows]
                    print(
                        f"validated targets={len(expected)} old_seeds={len(old_present)} "
                        f"mode={'apply' if args.apply else 'dry-run'}"
                    )
                    if not args.apply:
                        connection.rollback()
                        return

                    target_parameters = {
                        f"target{index}": session_id
                        for index, session_id in enumerate(expected)
                    }
                    target_placeholders = ",".join(
                        f":{name}" for name in target_parameters
                    )
                    cursor.execute(
                        f"""
                        update mio_demo_sessions
                        set is_seed = 1, expires_at = null
                        where session_id in ({target_placeholders})
                        """,
                        target_parameters,
                    )
                    if cursor.rowcount != len(expected):
                        raise RuntimeError(
                            f"expected to promote {len(expected)} rows, promoted {cursor.rowcount}"
                        )

                    if old_present:
                        old_parameters = {
                            f"old{index}": session_id
                            for index, session_id in enumerate(old_present)
                        }
                        old_placeholders = ",".join(
                            f":{name}" for name in old_parameters
                        )
                        cursor.execute(
                            f"delete from mio_demo_metrics where session_id in ({old_placeholders})",
                            old_parameters,
                        )
                        cursor.execute(
                            f"delete from mio_demo_messages where session_id in ({old_placeholders})",
                            old_parameters,
                        )
                        cursor.execute(
                            f"delete from mio_demo_sessions where session_id in ({old_placeholders})",
                            old_parameters,
                        )
                        if cursor.rowcount != len(old_present):
                            raise RuntimeError(
                                f"expected to delete {len(old_present)} rows, deleted {cursor.rowcount}"
                            )

                    verify_parameters = {
                        f"verify{index}": session_id
                        for index, session_id in enumerate(expected)
                    }
                    verify_placeholders = ",".join(
                        f":{name}" for name in verify_parameters
                    )
                    cursor.execute(
                        f"""
                        select count(*) from mio_demo_sessions
                        where is_seed = 1 and session_id in ({verify_placeholders})
                        """,
                        verify_parameters,
                    )
                    promoted = int(cursor.fetchone()[0])
                    if promoted != len(expected):
                        raise RuntimeError(
                            f"post-check failed: promoted={promoted} expected={len(expected)}"
                        )
                connection.commit()
                print(f"replacement committed: promoted={promoted} deleted={len(old_present)}")
            except Exception:
                connection.rollback()
                raise
    finally:
        repository.close()


if __name__ == "__main__":
    main()
