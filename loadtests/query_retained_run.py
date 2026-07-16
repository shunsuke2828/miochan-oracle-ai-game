#!/usr/bin/env python3
from __future__ import annotations

import json
import sys

from app.config import settings
from app.database import build_repository


def main() -> None:
    prefix = sys.argv[1]
    result: dict[str, object] = {"nickname_prefix": prefix}
    repository, warning = build_repository(settings)
    if warning:
        raise RuntimeError(warning)
    with repository.connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select s.status, count(*)
                from mio_game_sessions s
                join mio_players p on p.player_id = s.player_id
                where p.nickname like :prefix
                group by s.status
                order by s.status
                """,
                prefix=prefix + "%",
            )
            result["game_status_counts"] = {
                str(status): int(count) for status, count in cursor.fetchall()
            }
            cursor.execute(
                """
                select count(*),
                       sum(case when t.answer_vector is not null then 1 else 0 end),
                       sum(case when t.score_detail_json is not null then 1 else 0 end)
                from mio_turns t
                join mio_game_sessions s on s.session_id = t.session_id
                join mio_players p on p.player_id = s.player_id
                where p.nickname like :prefix
                """,
                prefix=prefix + "%",
            )
            turn_count, vector_count, scored_count = cursor.fetchone()
            result["turns"] = {
                "total": int(turn_count or 0),
                "embedded": int(vector_count or 0),
                "scored": int(scored_count or 0),
            }
            cursor.execute(
                """
                select min(s.ended_at), max(s.ended_at)
                from mio_game_sessions s
                join mio_players p on p.player_id = s.player_id
                where p.nickname like :prefix
                """,
                prefix=prefix + "%",
            )
            first_ended, last_ended = cursor.fetchone()
            result["first_ended_at"] = first_ended.isoformat() if first_ended else None
            result["last_ended_at"] = last_ended.isoformat() if last_ended else None
    close = getattr(repository, "close", None)
    if callable(close):
        close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
