#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def text(value: object) -> str:
    if value is None:
        return ""
    if hasattr(value, "read"):
        return str(value.read())
    return str(value)


def main() -> None:
    os.environ["MIO_DATA_MODE"] = "adb"
    from app.config import Settings
    from app.database import AdbRepository
    from app.rescue import final_score, rank_for, result_message, title_for

    repository = AdbRepository(Settings())
    updated = 0
    try:
        with repository.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select session_id, cleared_flag
                    from mio_game_sessions
                    where status = 'finished'
                    """
                )
                sessions = cursor.fetchall()
                for session_id, cleared_flag in sessions:
                    cursor.execute(
                        """
                        select turn_score, valid_flag, empathy_score, action_score,
                               speed_score, penalty_score,
                               dbms_lob.substr(score_detail_json,4000,1), answer_type
                        from mio_turns
                        where session_id = :session_id
                        order by turn_no
                        """,
                        session_id=session_id,
                    )
                    turns = []
                    for row in cursor.fetchall():
                        detail_text = text(row[6])
                        try:
                            detail = json.loads(detail_text) if detail_text else {}
                        except json.JSONDecodeError:
                            detail = {}
                        turns.append(
                            {
                                "turn_score": int(row[0]),
                                "valid": bool(row[1]),
                                "empathy": int(row[2]),
                                "action": int(row[3]),
                                "speed": int(row[4]),
                                "penalty": int(row[5]),
                                "answer_type": row[7],
                                **(
                                    {"choice_quality": detail["choice_quality"]}
                                    if "choice_quality" in detail else {}
                                ),
                            }
                        )
                    cleared = bool(cleared_flag)
                    score = final_score(turns, cleared)
                    rank = rank_for(score)
                    title = title_for(score, turns)
                    cursor.execute(
                        """
                        update mio_game_sessions
                        set final_score = :score,
                            coins = :coins,
                            rank_label = :rank_label,
                            title_label = :title_label,
                            result_message = :result_message
                        where session_id = :session_id
                        """,
                        score=score,
                        coins=score // 5,
                        rank_label=rank,
                        title_label=title,
                        result_message=result_message(rank, cleared),
                        session_id=session_id,
                    )
                    updated += 1
            connection.commit()
        print(f"Mio rank migration complete — updated={updated} scale=0-100 ranks=A-E")
    finally:
        repository.close()


if __name__ == "__main__":
    main()
