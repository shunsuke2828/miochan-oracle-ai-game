from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import oracledb

from .database import db_embedding_parameters
from .rescue import (
    CHALLENGES,
    EMBEDDING_MODEL,
    SELECT_AI_PROFILE,
    TIME_LIMIT_SEC,
    challenge_for_turn,
    choices_for,
    choose_challenge,
    contains_unsafe_content,
    fallback_quality,
    final_score,
    json_text,
    mask_personal_information,
    normalized_quality,
    rank_for,
    result_message,
    score_turn,
    title_for,
)


LOGGER = logging.getLogger(__name__)


class RescueNotFound(KeyError):
    pass


class RescueConflict(ValueError):
    pass


class RescueNotReady(ValueError):
    pass


def _text(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "read"):
        return str(value.read())
    return str(value)


def _json_object(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    cleaned = _text(text).strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I)
    try:
        value = json.loads(cleaned)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, character in enumerate(cleaned):
            if character != "{":
                continue
            try:
                value, _ = decoder.raw_decode(cleaned[index:])
                if isinstance(value, dict):
                    return value
            except json.JSONDecodeError:
                continue
        return None


def _valid_quality_payload(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict) or not isinstance(payload.get("reason"), str):
        return False
    for key in ("empathy", "relevance", "actionability", "safety", "progress"):
        value = payload.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        if value < 0 or value > 5:
            return False
    return True


def _valid_dialogue_payload(
    payload: dict[str, Any] | None, *, initial: bool = False
) -> bool:
    if not isinstance(payload, dict):
        return False
    message = payload.get("mio_message")
    if not isinstance(message, str) or not message.strip() or len(message) > 500:
        return False
    if payload.get("emotion") not in {"anxious", "relieved", "confused", "happy", "cleared"}:
        return False
    if payload.get("next_state") not in {"hearing", "thinking", "solving", "cleared"}:
        return False
    if not initial and not isinstance(payload.get("safety_flag"), bool):
        return False
    return True


class AdbRescueService:
    mode = "adb-select-ai"

    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def _generate(
        self,
        cursor: oracledb.Cursor,
        prompt: str,
        conversation_id: str | None = None,
    ) -> dict[str, Any] | None:
        try:
            if conversation_id:
                cursor.execute(
                    """
                    select dbms_cloud_ai.generate(
                      prompt => :prompt,
                      profile_name => :profile_name,
                      action => 'chat',
                      params => json_object(
                        'conversation_id' value :conversation_id returning clob
                      )
                    )
                    from dual
                    """,
                    prompt=prompt,
                    profile_name=SELECT_AI_PROFILE,
                    conversation_id=conversation_id,
                )
            else:
                cursor.execute(
                    """
                    select dbms_cloud_ai.generate(
                      prompt => :prompt,
                      profile_name => :profile_name,
                      action => 'chat'
                    )
                    from dual
                    """,
                    prompt=prompt,
                    profile_name=SELECT_AI_PROFILE,
                )
            raw_response = _text(cursor.fetchone()[0])
            parsed = _json_object(raw_response)
            if parsed is None:
                LOGGER.warning(
                    "Select AI returned non-JSON output: %s",
                    raw_response[:240].replace("\n", " "),
                )
            return parsed
        except Exception as exc:
            LOGGER.warning("Select AI fallback: %s: %s", type(exc).__name__, exc)
            return None

    def _create_conversation(self, cursor: oracledb.Cursor) -> str | None:
        try:
            cursor.execute(
                """
                select dbms_cloud_ai.create_conversation(
                  attributes => :attributes
                )
                from dual
                """,
                attributes=json_text(
                    {
                        "title": "Mio Rescue 60sec",
                        "description": "みおちゃんレスキューの会話",
                        "retention_days": 30,
                        "conversation_length": 6,
                    }
                ),
            )
            return _text(cursor.fetchone()[0]) or None
        except Exception as exc:
            LOGGER.warning("Select AI conversation fallback: %s", type(exc).__name__)
            return None

    def start(
        self,
        nickname: str,
        consent: bool,
        public_consent: bool,
        session_id: str | None = None,
        ranking_consent: bool | None = None,
    ) -> dict[str, Any]:
        if not consent:
            raise RescueConflict("consent_required")
        if ranking_consent is None:
            ranking_consent = public_consent
        reuse_session = bool(session_id)
        session_id = session_id or uuid.uuid4().hex
        challenge_type = choose_challenge()
        challenge = CHALLENGES[challenge_type]
        choices = choices_for(challenge_type)
        with self.repository.connection() as connection:
            try:
                with connection.cursor() as cursor:
                    if reuse_session:
                        cursor.execute(
                            """
                            select nickname, is_seed
                            from mio_demo_sessions
                            where session_id = :session_id
                            for update
                            """,
                            session_id=session_id,
                        )
                        existing = cursor.fetchone()
                        if not existing or bool(existing[1]):
                            raise RescueConflict("session_not_available")
                        if str(existing[0]) != nickname:
                            raise RescueConflict("nickname_mismatch")
                        cursor.execute(
                            "select count(*) from mio_game_sessions where session_id = :session_id",
                            session_id=session_id,
                        )
                        if int(cursor.fetchone()[0]) > 0:
                            raise RescueConflict("game_already_started")
                        cursor.execute(
                            """
                            update mio_demo_sessions
                            set public_consent = :public_consent,
                                ranking_consent = :ranking_consent,
                                expires_at = systimestamp + interval '30' day
                            where session_id = :session_id
                            """,
                            public_consent=1 if public_consent else 0,
                            ranking_consent=1 if ranking_consent else 0,
                            session_id=session_id,
                        )
                    conversation_id = self._create_conversation(cursor)
                    # The countdown must lead straight into the game. Initial
                    # prompts therefore use the curated category text; AI
                    # quality evaluation remains deferred to final scoring.
                    mio_message = str(challenge["message"])
                    player_id = cursor.var(oracledb.NUMBER)
                    if not reuse_session:
                        cursor.execute(
                            """
                            insert into mio_demo_sessions (
                              session_id, nickname, public_consent, ranking_consent,
                              is_seed, expires_at
                            ) values (
                              :session_id, :nickname, :public_consent,
                              :ranking_consent, 0,
                              systimestamp + interval '30' day
                            )
                            """,
                            session_id=session_id,
                            nickname=nickname,
                            public_consent=1 if public_consent else 0,
                            ranking_consent=1 if ranking_consent else 0,
                        )
                    cursor.execute(
                        """
                        insert into mio_players (nickname)
                        values (:nickname)
                        returning player_id into :player_id
                        """,
                        nickname=nickname,
                        player_id=player_id,
                    )
                    returned = player_id.getvalue()
                    if isinstance(returned, list):
                        returned = returned[0]
                    cursor.execute(
                        """
                        insert into mio_game_sessions (
                          session_id, player_id, conversation_id,
                          challenge_type, current_state, mio_message,
                          difficulty, turn_no, current_score, coins,
                          combo_count, valid_turn_count, total_turn_count,
                          choices_json, status, started_at, deadline_at,
                          turn_started_at, time_limit_sec
                        ) values (
                          :session_id, :player_id, :conversation_id,
                          :challenge_type, 'hearing', :mio_message,
                          100, 1, 0, 0, 0, 0, 0,
                          :choices_json, 'playing', systimestamp,
                          systimestamp + numtodsinterval(:time_limit_sec, 'SECOND'),
                          systimestamp, :time_limit_sec
                        )
                        """,
                        session_id=session_id,
                        player_id=returned,
                        conversation_id=conversation_id,
                        challenge_type=challenge_type,
                        mio_message=mio_message,
                        choices_json=json_text(choices),
                        time_limit_sec=TIME_LIMIT_SEC,
                    )
                    cursor.execute(
                        """
                        select started_at, deadline_at
                        from mio_game_sessions where session_id = :session_id
                        """,
                        session_id=session_id,
                    )
                    started_at, deadline_at = cursor.fetchone()
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return {
            "session_id": session_id,
            "time_limit_sec": TIME_LIMIT_SEC,
            "started_at": self._iso(started_at),
            "deadline_at": self._iso(deadline_at),
            "turn_no": 1,
            "challenge_type": challenge_type,
            "challenge_label": challenge["label"],
            "difficulty": 100,
            "score": 0,
            "coins": 0,
            "combo": 0,
            "mio_message": mio_message,
            "emotion": "anxious",
            "choices": choices,
            "game_finished": False,
        }

    def submit_turn(
        self,
        session_id: str,
        turn_no: int,
        answer_type: str,
        user_answer: str,
    ) -> dict[str, Any]:
        masked_answer = mask_personal_information(user_answer.strip())
        with self.repository.connection() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        select status, deadline_at, turn_no, difficulty,
                               current_score, coins, combo_count,
                               valid_turn_count, total_turn_count,
                               challenge_type, current_state,
                               dbms_lob.substr(mio_message,4000,1),
                               turn_started_at
                        from mio_game_sessions
                        where session_id = :session_id
                        for update
                        """,
                        session_id=session_id,
                    )
                    session = cursor.fetchone()
                    if not session:
                        raise RescueNotFound("session_not_found")
                    (
                        status, deadline_at, expected_turn, difficulty_before,
                        current_score, coins, combo_before, valid_count,
                        total_count, challenge_type, current_state,
                        mio_message, turn_started_at,
                    ) = session
                    if int(turn_no) < int(expected_turn):
                        stored = self._stored_turn(
                            cursor, session_id, turn_no, masked_answer
                        )
                        connection.rollback()
                        return stored
                    if int(turn_no) != int(expected_turn):
                        raise RescueConflict("stale_turn")
                    if status == "scoring":
                        connection.rollback()
                        return {
                            "accepted": False,
                            "session_id": session_id,
                            "status": "scoring",
                            "scoring_pending": True,
                            "game_finished": False,
                        }
                    if status != "playing":
                        result = self._result_row(cursor, session_id)
                        connection.rollback()
                        return {
                            "accepted": False,
                            "game_finished": True,
                            "result": result,
                        }

                    cursor.execute("select systimestamp from dual")
                    received_at = cursor.fetchone()[0]
                    if received_at > deadline_at:
                        result = self._queue_finalization_locked(
                            cursor, session_id
                        )
                        connection.commit()
                        return {
                            "accepted": False,
                            "time_remaining_sec": 0,
                            **result,
                        }

                    elapsed_sec = max(
                        0.0, (received_at - turn_started_at).total_seconds()
                    )
                    unsafe = contains_unsafe_content(masked_answer)
                    turn_id = cursor.var(oracledb.NUMBER)
                    cursor.execute(
                        """
                        insert into mio_turns (
                          session_id, turn_no, challenge_type, current_state,
                          mio_message, user_answer, answer_type,
                          embedding_model, difficulty_before,
                          elapsed_sec, received_at
                        ) values (
                          :session_id, :turn_no, :challenge_type, :current_state,
                          :mio_message, :user_answer, :answer_type,
                          :embedding_model, :difficulty_before,
                          :elapsed_sec, :received_at
                        ) returning turn_id into :turn_id
                        """,
                        session_id=session_id,
                        turn_no=turn_no,
                        challenge_type=challenge_type,
                        current_state=current_state,
                        mio_message=mio_message,
                        user_answer=masked_answer,
                        answer_type=answer_type,
                        embedding_model=EMBEDDING_MODEL,
                        difficulty_before=difficulty_before,
                        elapsed_sec=elapsed_sec,
                        received_at=received_at,
                        turn_id=turn_id,
                    )
                    returned_turn_id = turn_id.getvalue()
                    if isinstance(returned_turn_id, list):
                        returned_turn_id = returned_turn_id[0]
                    if unsafe:
                        next_challenge_type = challenge_type
                        next_message = "その内容はこのゲームでは扱えないよ。安全な方法で、もう一度一緒に考えてね。"
                        emotion = "confused"
                        next_state = current_state
                    else:
                        next_challenge_type = challenge_for_turn(int(turn_no) + 1)
                        next_challenge = CHALLENGES[next_challenge_type]
                        next_message = str(next_challenge["message"])
                        emotion = "relieved"
                        next_state = "solving"

                    next_choices = choices_for(next_challenge_type)
                    new_total = int(total_count) + 1
                    cursor.execute("select systimestamp from dual")
                    processed_at = cursor.fetchone()[0]
                    cursor.execute(
                        """
                        update mio_game_sessions
                        set total_turn_count = :total_turn_count,
                            challenge_type = :challenge_type,
                            current_state = :current_state,
                            mio_message = :mio_message,
                            choices_json = :choices_json,
                            turn_no = turn_no + 1,
                            turn_started_at = systimestamp
                        where session_id = :session_id
                        """,
                        total_turn_count=new_total,
                        challenge_type=next_challenge_type,
                        current_state=next_state,
                        mio_message=next_message,
                        choices_json=json_text(next_choices),
                        session_id=session_id,
                    )
                    remaining = max(
                        0, int((deadline_at - processed_at).total_seconds())
                    )
                    response = {
                        "accepted": True,
                        "turn_no": int(turn_no),
                        "time_remaining_sec": remaining,
                        "turn_score": None,
                        "score_detail": None,
                        "total_score": max(0, int(current_score)),
                        "coins": int(coins),
                        "difficulty": int(difficulty_before),
                        "combo": int(combo_before),
                        "challenge_type": next_challenge_type,
                        "mio_message": next_message,
                        "emotion": emotion,
                        "choices": next_choices,
                        "game_finished": False,
                        "scoring_pending": True,
                    }
                    cursor.execute(
                        """
                        update mio_turns
                        set next_mio_message = :next_mio_message,
                            response_json = :response_json,
                            embedding_failed = 0,
                            llm_eval_failed = 0
                        where turn_id = :turn_id
                        """,
                        next_mio_message=next_message,
                        response_json=json_text(response),
                        turn_id=returned_turn_id,
                    )
                    cursor.execute(
                        """
                        insert into mio_score_events (
                          session_id, turn_id, event_type, point_delta, reason
                        ) values (
                          :session_id, :turn_id, 'turn_queued', 0,
                          'natural language saved; deferred embedding'
                        )
                        """,
                        session_id=session_id,
                        turn_id=returned_turn_id,
                    )
                connection.commit()
                return response
            except Exception:
                connection.rollback()
                raise

    def state(self, session_id: str) -> dict[str, Any]:
        with self.repository.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select s.status, s.started_at, s.deadline_at, s.turn_no,
                           s.challenge_type, s.difficulty, s.current_score,
                           s.coins, s.combo_count,
                           dbms_lob.substr(s.mio_message,4000,1),
                           dbms_lob.substr(s.choices_json,4000,1), p.nickname,
                           (select count(*) from mio_turns t
                            where t.session_id = s.session_id
                              and (t.score_detail_json is null
                                   or t.answer_vector is null)) pending_turns
                    from mio_game_sessions s
                    join mio_players p on p.player_id = s.player_id
                    where s.session_id = :session_id
                    """,
                    session_id=session_id,
                )
                row = cursor.fetchone()
                if not row:
                    raise RescueNotFound("session_not_found")
                cursor.execute("select systimestamp from dual")
                now = cursor.fetchone()[0]
        return {
            "session_id": session_id,
            "status": row[0],
            "started_at": self._iso(row[1]),
            "deadline_at": self._iso(row[2]),
            "turn_no": int(row[3]),
            "challenge_type": row[4],
            "challenge_label": CHALLENGES.get(row[4], {}).get("label", row[4]),
            "difficulty": int(row[5]),
            "score": max(0, int(row[6])),
            "coins": int(row[7]),
            "combo": int(row[8]),
            "mio_message": _text(row[9]),
            "choices": json.loads(_text(row[10]) or "[]"),
            "nickname": row[11],
            "pending_turns": int(row[12]),
            "scoring_pending": row[0] == "scoring" or int(row[12]) > 0,
            "time_remaining_sec": max(0, int((row[2] - now).total_seconds())),
            "expired": now >= row[2],
            "game_ended": row[0] in {"scoring", "finished"},
            "game_finished": row[0] == "finished",
        }

    def finish(self, session_id: str) -> dict[str, Any]:
        with self.repository.connection() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        select status, deadline_at, difficulty
                        from mio_game_sessions
                        where session_id = :session_id
                        for update
                        """,
                        session_id=session_id,
                    )
                    row = cursor.fetchone()
                    if not row:
                        raise RescueNotFound("session_not_found")
                    if row[0] == "finished":
                        result = self._result_row(cursor, session_id)
                        connection.rollback()
                        return result
                    if row[0] == "scoring":
                        connection.rollback()
                        return self._scoring_payload(session_id)
                    if row[0] != "playing":
                        raise RescueConflict("invalid_game_status")
                    cursor.execute("select systimestamp from dual")
                    now = cursor.fetchone()[0]
                    if now < row[1] and int(row[2]) > 0:
                        raise RescueNotReady("game_is_still_running")
                    result = self._queue_finalization_locked(cursor, session_id)
                connection.commit()
                return result
            except Exception:
                connection.rollback()
                raise

    def result(self, session_id: str) -> dict[str, Any]:
        with self.repository.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select status from mio_game_sessions where session_id = :session_id",
                    session_id=session_id,
                )
                row = cursor.fetchone()
                if not row:
                    raise RescueNotFound("session_not_found")
                if row[0] == "scoring":
                    return self._scoring_payload(session_id)
                if row[0] != "finished":
                    raise RescueNotReady("game_is_still_running")
                return self._result_row(cursor, session_id)

    def process_next_finalization(self) -> bool:
        """Claim and finish one queued game across all web/worker instances."""
        with self.repository.connection() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        select session_id
                        from mio_game_sessions
                        where status = 'scoring'
                        order by created_at
                        for update skip locked
                        """
                    )
                    row = cursor.fetchone()
                    if not row:
                        connection.rollback()
                        return False
                    session_id = str(row[0])
                    cleared = self._prepare_final_scores(
                        cursor, session_id, final=True
                    )
                    self._finish_locked(cursor, session_id, cleared)
                connection.commit()
                LOGGER.info("rescue final scoring completed: session=%s", session_id)
                return True
            except Exception:
                connection.rollback()
                raise

    def process_next_pending_turn(self) -> bool:
        """Enrich one in-game turn when no final result is waiting."""
        with self.repository.connection() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        select t.session_id, t.turn_no
                        from mio_turns t
                        join mio_game_sessions s on s.session_id = t.session_id
                        where s.status = 'playing'
                          and (t.score_detail_json is null
                               or t.answer_vector is null)
                        order by t.received_at
                        for update of t.score_detail_json skip locked
                        """
                    )
                    row = cursor.fetchone()
                    if not row:
                        connection.rollback()
                        return False
                    session_id, turn_no = str(row[0]), int(row[1])
                    self._enrich_pending_turn(cursor, session_id, turn_no)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        self._reconcile_scored_session(session_id)
        return True

    def _queue_finalization_locked(
        self, cursor: oracledb.Cursor, session_id: str
    ) -> dict[str, Any]:
        cursor.execute(
            """
            update mio_game_sessions
            set status = 'scoring', current_state = 'scoring',
                choices_json = '[]',
                mio_message = 'アドバイスをまとめて採点しているよ！'
            where session_id = :session_id and status = 'playing'
            """,
            session_id=session_id,
        )
        if cursor.rowcount:
            cursor.execute(
                """
                insert into mio_score_events (
                  session_id, event_type, point_delta, reason
                ) values (
                  :session_id, 'game_scoring_queued', 0,
                  'final scoring claimed by dedicated worker'
                )
                """,
                session_id=session_id,
            )
        return self._scoring_payload(session_id)

    @staticmethod
    def _scoring_payload(session_id: str) -> dict[str, Any]:
        return {
            "session_id": session_id,
            "status": "scoring",
            "accepted": True,
            "scoring_pending": True,
            "game_ended": True,
            "game_finished": False,
        }

    def scoreboard(self) -> dict[str, Any]:
        with self.repository.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select p.nickname, s.final_score, s.rank_label, s.ended_at,
                           s.session_id
                    from mio_game_sessions s
                    join mio_players p on p.player_id = s.player_id
                    join mio_demo_sessions d on d.session_id = s.session_id
                    where s.status = 'finished'
                      and d.ranking_consent = 1
                      and (d.expires_at is null or d.expires_at > systimestamp)
                    order by s.final_score desc, s.ended_at asc
                    fetch first 5 rows only
                    """
                )
                ranking_rows = cursor.fetchall()
                cursor.execute(
                    """
                    select p.nickname, s.final_score, s.rank_label, s.session_id
                    from mio_game_sessions s
                    join mio_players p on p.player_id = s.player_id
                    join mio_demo_sessions d on d.session_id = s.session_id
                    where s.status = 'finished'
                      and d.ranking_consent = 1
                      and (d.expires_at is null or d.expires_at > systimestamp)
                    order by s.ended_at desc
                    fetch first 1 row only
                    """
                )
                latest = cursor.fetchone()
                cursor.execute(
                    """
                    select count(*)
                    from mio_game_sessions s
                    join mio_demo_sessions d on d.session_id = s.session_id
                    where s.status = 'finished'
                      and d.ranking_consent = 1
                      and (d.expires_at is null or d.expires_at > systimestamp)
                    """
                )
                completed = int(cursor.fetchone()[0])
        ranking = [
            {
                "rank": index,
                "nickname": row[0],
                "score": int(row[1]),
                "rank_label": row[2],
                "session_id": row[4],
            }
            for index, row in enumerate(ranking_rows, start=1)
        ]
        return {
            "top_score": ranking[0]["score"] if ranking else 0,
            "latest": (
                {
                    "nickname": latest[0],
                    "score": int(latest[1]),
                    "rank_label": latest[2],
                    "session_id": latest[3],
                }
                if latest else None
            ),
            "ranking": ranking,
            "completed_games": completed,
        }

    def standing(self, session_id: str) -> dict[str, Any] | None:
        """Return one participant's position in the public rescue ranking."""
        with self.repository.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select ranking_position, final_score, rank_label
                    from (
                      select s.session_id, s.final_score, s.rank_label,
                             row_number() over (
                               order by s.final_score desc, s.ended_at asc
                             ) as ranking_position
                      from mio_game_sessions s
                      join mio_demo_sessions d on d.session_id = s.session_id
                      where s.status = 'finished'
                        and d.ranking_consent = 1
                        and (d.expires_at is null or d.expires_at > systimestamp)
                    )
                    where session_id = :session_id
                    """,
                    session_id=session_id,
                )
                row = cursor.fetchone()
        if not row:
            return None
        return {
            "position": int(row[0]),
            "score": int(row[1]),
            "rank_label": row[2],
        }

    def detail(self, session_id: str) -> dict[str, Any] | None:
        with self.repository.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select status, final_score, coins, rank_label, title_label,
                           difficulty, started_at, ended_at,
                           dbms_lob.substr(result_message,4000,1)
                    from mio_game_sessions where session_id = :session_id
                    """,
                    session_id=session_id,
                )
                session = cursor.fetchone()
                if not session:
                    return None
                cursor.execute(
                    """
                    select turn_no, challenge_type, dbms_lob.substr(mio_message,4000,1),
                           dbms_lob.substr(user_answer,4000,1), answer_type,
                           ideal_similarity, turn_score, difficulty_before,
                           difficulty_after,
                           dbms_lob.substr(score_detail_json,4000,1),
                           embedding_model,
                           vector_dimension_count(answer_vector)
                    from mio_turns
                    where session_id = :session_id
                    order by turn_no
                    """,
                    session_id=session_id,
                )
                turns = cursor.fetchall()
        return {
            "status": session[0],
            "final_score": int(session[1]),
            "coins": int(session[2]),
            "rank_label": session[3],
            "title_label": session[4],
            "difficulty": int(session[5]),
            "started_at": self._iso(session[6]),
            "ended_at": self._iso(session[7]) if session[7] else None,
            "result_message": _text(session[8]),
            "turns": [
                {
                    "turn_no": int(row[0]),
                    "challenge_type": row[1],
                    "mio_message": _text(row[2]),
                    "user_answer": _text(row[3]),
                    "answer_type": row[4],
                    "ideal_similarity": float(row[5]) if row[5] is not None else None,
                    "turn_score": int(row[6]),
                    "difficulty_before": int(row[7]),
                    "difficulty_after": int(row[8]) if row[8] is not None else None,
                    "score_detail": json.loads(_text(row[9]) or "{}"),
                    "scoring_pending": row[9] is None,
                    "embedding_model": row[10],
                    "embedding_dimension": int(row[11]) if row[11] else 0,
                }
                for row in turns
            ],
        }

    def process_pending_turn(self, session_id: str, turn_no: int) -> None:
        """Complete expensive scoring after the HTTP response has been sent."""
        try:
            with self.repository.connection() as connection:
                try:
                    with connection.cursor() as cursor:
                        self._enrich_pending_turn(cursor, session_id, turn_no)
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
            self._reconcile_scored_session(session_id)
        except Exception:
            LOGGER.exception(
                "deferred rescue scoring failed: session=%s turn=%s",
                session_id,
                turn_no,
            )

    def _enrich_pending_turn(
        self,
        cursor: oracledb.Cursor,
        session_id: str,
        turn_no: int,
        *,
        force: bool = False,
    ) -> None:
        cursor.execute(
            """
            select turn_id, challenge_type, current_state,
                   dbms_lob.substr(mio_message,4000,1),
                   dbms_lob.substr(user_answer,4000,1), answer_type,
                   elapsed_sec, case when answer_vector is null then 1 else 0 end,
                   dbms_lob.substr(score_detail_json,4000,1)
            from mio_turns
            where session_id = :session_id and turn_no = :turn_no
            for update
            """,
            session_id=session_id,
            turn_no=turn_no,
        )
        row = cursor.fetchone()
        if not row or (_text(row[8]) and not force):
            return
        (
            turn_id, challenge_type, current_state, mio_message,
            answer, answer_type, elapsed_sec, vector_missing, _score_detail,
        ) = row
        embedding_failed = False
        if bool(vector_missing):
            try:
                cursor.execute(
                    """
                    update mio_turns
                    set answer_vector = dbms_vector_chain.utl_to_embedding(
                          to_clob(user_answer), json(:embedding_parameters)
                        ),
                        embedding_model = :embedding_model,
                        embedding_failed = 0
                    where turn_id = :turn_id
                    """,
                    embedding_parameters=db_embedding_parameters(),
                    embedding_model=EMBEDDING_MODEL,
                    turn_id=turn_id,
                )
            except Exception as exc:
                LOGGER.warning(
                    "deferred rescue embedding fallback: turn=%s %s",
                    turn_no,
                    type(exc).__name__,
                )
                embedding_failed = True
                cursor.execute(
                    "update mio_turns set embedding_failed = 1 where turn_id = :turn_id",
                    turn_id=turn_id,
                )

        cosine, repeat_similarity = self._similarities(
            cursor, int(turn_id), session_id, int(turn_no), challenge_type
        )
        unsafe = contains_unsafe_content(answer)
        fallback = fallback_quality(answer, challenge_type, unsafe)
        # Keep the background worker lightweight so it cannot exhaust the
        # small ADB pool while the player is answering. Gemini evaluates all
        # turns in one call when the final result is requested.
        quality = fallback
        provisional = score_turn(
            answer=answer,
            answer_type=answer_type,
            cosine=cosine,
            repeat_similarity=repeat_similarity,
            quality=quality,
            elapsed_sec=float(elapsed_sec or 0),
            combo_before=0,
            difficulty_before=100,
            embedding_failed=embedding_failed,
        )
        provisional_detail = provisional.as_dict()
        if fallback.get("curated_choice"):
            provisional_detail["choice_quality"] = fallback["choice_quality"]
        penalty = (
            provisional.unsafe_penalty + provisional.offtopic_penalty
            + provisional.repeat_penalty
        )
        cursor.execute(
            """
            update mio_turns
            set ideal_similarity = :ideal_similarity,
                repeat_similarity = :repeat_similarity,
                llm_quality_json = :llm_quality_json,
                quality_score = :quality_score,
                empathy_score = :empathy_score,
                action_score = :action_score,
                speed_score = :speed_score,
                turn_score = :turn_score,
                penalty_score = :penalty_score,
                valid_flag = :valid_flag,
                score_detail_json = :score_detail_json,
                difficulty_after = :difficulty_after,
                embedding_failed = :embedding_failed,
                llm_eval_failed = :llm_eval_failed
            where turn_id = :turn_id
            """,
            ideal_similarity=cosine,
            repeat_similarity=repeat_similarity,
            llm_quality_json=json_text(quality),
            quality_score=(
                provisional.context + provisional.empathy
                + provisional.action + provisional.progress
            ),
            empathy_score=provisional.empathy,
            action_score=provisional.action,
            speed_score=provisional.speed,
            turn_score=provisional.total,
            penalty_score=penalty,
            valid_flag=1 if provisional.valid else 0,
            score_detail_json=json_text(provisional_detail),
            difficulty_after=provisional.difficulty_after,
            embedding_failed=1 if embedding_failed else 0,
            llm_eval_failed=1 if quality.get("llm_eval_failed") else 0,
            turn_id=turn_id,
        )
        cursor.execute(
            """
            update mio_score_events
            set point_delta = :point_delta, reason = :reason
            where session_id = :session_id and turn_id = :turn_id
              and event_type = 'turn_scored'
            """,
            session_id=session_id,
            turn_id=turn_id,
            point_delta=provisional.total,
            reason=str(quality.get("reason", ""))[:500],
        )
        if cursor.rowcount == 0:
            cursor.execute(
                """
                insert into mio_score_events (
                  session_id, turn_id, event_type, point_delta, reason
                ) values (
                  :session_id, :turn_id, 'turn_scored', :point_delta, :reason
                )
                """,
                session_id=session_id,
                turn_id=turn_id,
                point_delta=provisional.total,
                reason=str(quality.get("reason", ""))[:500],
            )

    def _prepare_final_scores(
        self,
        cursor: oracledb.Cursor,
        session_id: str,
        *,
        final: bool = False,
    ) -> bool:
        pending_filter = (
            "and (score_detail_json is null or answer_vector is null)"
            if final else "and score_detail_json is null"
        )
        cursor.execute(
            f"""
            select turn_no from mio_turns
            where session_id = :session_id {pending_filter}
            order by turn_no
            """,
            session_id=session_id,
        )
        for (pending_turn_no,) in cursor.fetchall():
            self._enrich_pending_turn(
                cursor,
                session_id,
                int(pending_turn_no),
                force=final,
            )

        if final:
            self._apply_batch_quality(cursor, session_id)

        cursor.execute(
            """
            select turn_id, turn_no, dbms_lob.substr(user_answer,4000,1),
                   answer_type, ideal_similarity, repeat_similarity,
                   dbms_lob.substr(llm_quality_json,4000,1), elapsed_sec,
                   embedding_failed, challenge_type
            from mio_turns
            where session_id = :session_id
            order by turn_no
            """,
            session_id=session_id,
        )
        rows = cursor.fetchall()
        combo = 0
        difficulty = 100
        running_score = 0
        normalized_turns: list[dict[str, Any]] = []
        valid_count = 0
        cleared = False
        for row in rows:
            (
                turn_id, _turn_no, answer, answer_type, cosine,
                repeat_similarity, quality_json, elapsed_sec,
                embedding_failed, challenge_type,
            ) = row
            fallback = fallback_quality(
                answer, challenge_type, contains_unsafe_content(answer)
            )
            if answer_type == "choice" and fallback.get("curated_choice"):
                quality = fallback
            else:
                try:
                    quality = json.loads(_text(quality_json)) if quality_json else fallback
                except json.JSONDecodeError:
                    quality = fallback
            difficulty_before = difficulty
            scored = score_turn(
                answer=answer,
                answer_type=answer_type,
                cosine=float(cosine) if cosine is not None else None,
                repeat_similarity=(
                    float(repeat_similarity)
                    if repeat_similarity is not None else None
                ),
                quality=quality,
                elapsed_sec=float(elapsed_sec or 0),
                combo_before=combo,
                difficulty_before=difficulty_before,
                embedding_failed=bool(embedding_failed),
            )
            combo = scored.combo
            difficulty = 0 if cleared else scored.difficulty_after
            cleared = cleared or difficulty == 0
            running_score += scored.total
            valid_count += 1 if scored.valid else 0
            score_detail = scored.as_dict()
            score_detail["difficulty_after"] = difficulty
            if fallback.get("curated_choice"):
                score_detail["choice_quality"] = fallback["choice_quality"]
            normalized_turns.append(
                {
                    **score_detail,
                    "answer_type": answer_type,
                    "penalty": (
                        scored.unsafe_penalty + scored.offtopic_penalty
                        + scored.repeat_penalty
                    ),
                }
            )
            penalty = (
                scored.unsafe_penalty + scored.offtopic_penalty
                + scored.repeat_penalty
            )
            cursor.execute(
                """
                update mio_turns
                set quality_score = :quality_score,
                    empathy_score = :empathy_score,
                    action_score = :action_score,
                    speed_score = :speed_score,
                    turn_score = :turn_score,
                    penalty_score = :penalty_score,
                    valid_flag = :valid_flag,
                    score_detail_json = :score_detail_json,
                    difficulty_before = :difficulty_before,
                    difficulty_after = :difficulty_after
                where turn_id = :turn_id
                """,
                quality_score=(
                    scored.context + scored.empathy
                    + scored.action + scored.progress
                ),
                empathy_score=scored.empathy,
                action_score=scored.action,
                speed_score=scored.speed,
                turn_score=scored.total,
                penalty_score=penalty,
                valid_flag=1 if scored.valid else 0,
                score_detail_json=json_text(score_detail),
                difficulty_before=difficulty_before,
                difficulty_after=difficulty,
                turn_id=turn_id,
            )
            cursor.execute(
                """
                update mio_score_events
                set point_delta = :point_delta
                where session_id = :session_id and turn_id = :turn_id
                  and event_type = 'turn_scored'
                """,
                point_delta=scored.total,
                session_id=session_id,
                turn_id=turn_id,
            )
        cursor.execute(
            """
            update mio_game_sessions
            set difficulty = :difficulty,
                current_score = :current_score,
                coins = :coins,
                combo_count = :combo_count,
                valid_turn_count = :valid_turn_count,
                total_turn_count = :total_turn_count
            where session_id = :session_id
            """,
            difficulty=difficulty,
            current_score=final_score(normalized_turns, cleared),
            coins=final_score(normalized_turns, cleared) // 5,
            combo_count=combo,
            valid_turn_count=valid_count,
            total_turn_count=len(rows),
            session_id=session_id,
        )
        return cleared

    def _apply_batch_quality(
        self, cursor: oracledb.Cursor, session_id: str
    ) -> None:
        cursor.execute(
            """
            select turn_no, challenge_type, current_state,
                   dbms_lob.substr(mio_message,4000,1),
                   dbms_lob.substr(user_answer,4000,1)
            from mio_turns
            where session_id = :session_id
            order by turn_no
            """,
            session_id=session_id,
        )
        rows = cursor.fetchall()
        if not rows:
            return
        turn_payload = [
            {
                "turn_no": int(row[0]),
                "category": CHALLENGES.get(row[1], {}).get("label", row[1]),
                "state": row[2],
                "mio_message": _text(row[3])[:300],
                "user_answer": _text(row[4])[:500],
            }
            for row in rows
            if not contains_unsafe_content(_text(row[4]))
        ]
        if not turn_payload:
            return
        payload = self._generate(
            cursor, self._batch_quality_prompt(turn_payload)
        )
        items = payload.get("turns") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            return
        allowed_turns = {item["turn_no"] for item in turn_payload}
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                item_turn_no = int(item.get("turn_no"))
            except (TypeError, ValueError):
                continue
            scores = item.get("scores")
            if isinstance(scores, list) and len(scores) == 5:
                quality = {
                    "empathy": scores[0],
                    "relevance": scores[1],
                    "actionability": scores[2],
                    "safety": scores[3],
                    "progress": scores[4],
                    "reason": "Gemini一括評価",
                }
            else:
                quality = {
                    key: value for key, value in item.items()
                    if key != "turn_no"
                }
            if item_turn_no not in allowed_turns or not _valid_quality_payload(quality):
                continue
            normalized = normalized_quality(quality, quality)
            cursor.execute(
                """
                update mio_turns
                set llm_quality_json = :llm_quality_json,
                    llm_eval_failed = 0
                where session_id = :session_id and turn_no = :turn_no
                """,
                llm_quality_json=json_text(normalized),
                session_id=session_id,
                turn_no=item_turn_no,
            )

    def _reconcile_scored_session(self, session_id: str) -> None:
        with self.repository.connection() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        select status from mio_game_sessions
                        where session_id = :session_id
                        for update
                        """,
                        session_id=session_id,
                    )
                    row = cursor.fetchone()
                    if row and row[0] == "playing":
                        cursor.execute(
                            """
                            select count(*) from mio_turns
                            where session_id = :session_id
                              and score_detail_json is null
                            """,
                            session_id=session_id,
                        )
                        if int(cursor.fetchone()[0]) == 0:
                            self._prepare_final_scores(cursor, session_id)
                            # The browser observes difficulty=0 and calls the
                            # normal finish endpoint, which performs the final
                            # one-shot Gemini evaluation before publishing.
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def _similarities(
        self,
        cursor: oracledb.Cursor,
        turn_id: int,
        session_id: str,
        turn_no: int,
        challenge_type: str,
    ) -> tuple[float | None, float | None]:
        cursor.execute(
            """
            select max(greatest(0, 1 - vector_distance(
                     t.answer_vector, i.ideal_vector, cosine)))
            from mio_turns t
            join mio_ideal_answers i
              on i.challenge_type = :challenge_type
             and i.embedding_model = t.embedding_model
            where t.turn_id = :turn_id
              and t.answer_vector is not null
              and i.ideal_vector is not null
            """,
            challenge_type=challenge_type,
            turn_id=turn_id,
        )
        cosine = cursor.fetchone()[0]
        cursor.execute(
            """
            select max(1 - vector_distance(current_turn.answer_vector,
                                            previous_turn.answer_vector, cosine))
            from mio_turns current_turn
            join mio_turns previous_turn
              on previous_turn.session_id = current_turn.session_id
             and previous_turn.turn_no < :turn_no
             and previous_turn.answer_vector is not null
            where current_turn.turn_id = :turn_id
              and current_turn.session_id = :session_id
              and current_turn.answer_vector is not null
            """,
            turn_no=turn_no,
            turn_id=turn_id,
            session_id=session_id,
        )
        repeat = cursor.fetchone()[0]
        return (
            float(cosine) if cosine is not None else None,
            float(repeat) if repeat is not None else None,
        )

    def _stored_turn(
        self,
        cursor: oracledb.Cursor,
        session_id: str,
        turn_no: int,
        answer: str,
    ) -> dict[str, Any]:
        cursor.execute(
            """
            select dbms_lob.substr(user_answer,4000,1), response_json
            from mio_turns
            where session_id = :session_id and turn_no = :turn_no
            """,
            session_id=session_id,
            turn_no=turn_no,
        )
        row = cursor.fetchone()
        if not row or _text(row[0]) != answer:
            raise RescueConflict("turn_already_answered")
        return json.loads(_text(row[1]))

    def _finish_locked(
        self, cursor: oracledb.Cursor, session_id: str, cleared: bool
    ) -> dict[str, Any]:
        cursor.execute(
            """
            select turn_score, valid_flag, empathy_score, action_score,
                   speed_score, penalty_score,
                   dbms_lob.substr(score_detail_json,4000,1), answer_type
            from mio_turns where session_id = :session_id order by turn_no
            """,
            session_id=session_id,
        )
        turns = [
            {
                "turn_score": int(row[0]),
                "valid": bool(row[1]),
                "empathy": int(row[2]),
                "action": int(row[3]),
                "speed": int(row[4]),
                "penalty": int(row[5]),
                "answer_type": row[7],
                **(
                    {"choice_quality": json.loads(_text(row[6])).get("choice_quality")}
                    if _text(row[6]) else {}
                ),
            }
            for row in cursor.fetchall()
        ]
        score = final_score(turns, cleared)
        rank = rank_for(score)
        title = title_for(score, turns)
        message = result_message(rank, cleared)
        cursor.execute(
            """
            update mio_game_sessions
            set status = 'finished', ended_at = systimestamp,
                final_score = :final_score, coins = :coins,
                rank_label = :rank_label, title_label = :title_label,
                result_message = :result_message, cleared_flag = :cleared_flag,
                difficulty = case when :cleared_flag = 1 then 0 else difficulty end
            where session_id = :session_id
            """,
            final_score=score,
            coins=score // 5,
            rank_label=rank,
            title_label=title,
            result_message=message,
            cleared_flag=1 if cleared else 0,
            session_id=session_id,
        )
        cursor.execute(
            """
            insert into mio_score_events (
              session_id, event_type, point_delta, reason
            ) values (
              :session_id, 'game_finished', :point_delta, :reason
            )
            """,
            session_id=session_id,
            point_delta=score,
            reason=f"rank={rank};title={title}",
        )
        return self._result_row(cursor, session_id)

    def _result_row(
        self, cursor: oracledb.Cursor, session_id: str
    ) -> dict[str, Any]:
        cursor.execute(
            """
            select p.nickname, s.final_score, s.coins, s.rank_label,
                   s.title_label, s.result_message, s.status,
                   s.cleared_flag, s.ended_at
            from mio_game_sessions s
            join mio_players p on p.player_id = s.player_id
            where s.session_id = :session_id
            """,
            session_id=session_id,
        )
        row = cursor.fetchone()
        if not row:
            raise RescueNotFound("session_not_found")
        return {
            "nickname": row[0],
            "final_score": int(row[1]),
            "coins": int(row[2]),
            "rank_label": row[3],
            "title_label": row[4],
            "mio_message": _text(row[5]),
            "status": row[6],
            "cleared": bool(row[7]),
            "ended_at": self._iso(row[8]) if row[8] else None,
        }

    @staticmethod
    def _iso(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _initial_prompt(challenge_type: str, fallback: str) -> str:
        return f"""
あなたは『みおちゃんレスキュー60秒チャレンジ』の進行役です。
カテゴリは{CHALLENGES[challenge_type]['label']}です。個人情報を質問せず、
医療・法律・危険行為を扱わない、短く親しみやすい困りごとを日本語で話してください。
必ず次のJSONだけを返してください。
{{"mio_message":"{fallback}","emotion":"anxious","next_state":"hearing"}}
""".strip()

    @staticmethod
    def _quality_prompt(
        challenge_type: str,
        current_state: str,
        mio_message: str,
        answer: str,
    ) -> str:
        return f"""
次の回答を、みおちゃんを助ける回答として0〜5で評価してください。
必ずJSONだけを返してください。
{{"empathy":0,"relevance":0,"actionability":0,"safety":0,"progress":0,"reason":"短い理由"}}
カテゴリ: {CHALLENGES[challenge_type]['label']}
状態: {current_state}
みおちゃん: {mio_message}
回答: {answer}
""".strip()

    @staticmethod
    def _batch_quality_prompt(turns: list[dict[str, Any]]) -> str:
        return f"""
みおちゃんレスキューの各回答をまとめて0〜5で評価してください。
説明やMarkdownを付けず、必ず次の短いJSONだけを返してください。
{{"turns":[{{"turn_no":1,"scores":[0,0,0,0,0]}}]}}
scoresの順番は、共感、関連性、具体的行動、安全性、会話進行です。
入力: {json_text(turns)}
""".strip()

    @staticmethod
    def _dialogue_prompt(
        challenge_type: str,
        current_state: str,
        difficulty: int,
        mio_message: str,
        answer: str,
        score_detail: dict[str, Any],
    ) -> str:
        return f"""
あなたは『みおちゃんレスキュー60秒チャレンジ』の進行役です。
ユーザの助けに反応して、次の短い発話を日本語で生成してください。
個人情報を聞かず、医療・法律・危険行為は安全な案内へ切り替えてください。
必ず次のJSONだけを返してください。
{{"mio_message":"次の発話","emotion":"anxious|relieved|confused|happy","safety_flag":false,"next_state":"hearing|thinking|solving|cleared"}}
カテゴリ: {CHALLENGES[challenge_type]['label']}
現在状態: {current_state}
困り度: {difficulty}
直前の発話: {mio_message}
ユーザ回答: {answer}
採点: {json_text(score_detail)}
""".strip()

    @staticmethod
    def _fallback_next_message(score: int) -> str:
        if score >= 65:
            return "ありがとう！少し整理できたよ。次は何から始めればいいかな？"
        if score >= 0:
            return "聞いてくれてありがとう。もう少しだけ一緒に考えてくれる？"
        return "うまく言葉にできないけど、安全な方法でもう一度考えてくれる？"

    @staticmethod
    def _queued_next_message(turn_no: int) -> str:
        messages = (
            "受け取ったよ！次は、最初にできる小さな一歩を教えてくれる？",
            "ありがとう。今度は、何を優先するとよさそうかな？",
            "少し整理できてきたよ。もう一つ、具体的な方法を教えて？",
        )
        return messages[(turn_no - 1) % len(messages)]


class MemoryRescueService:
    mode = "memory-fallback"

    def __init__(self, repository: Any) -> None:
        self.repository = repository
        self._lock = threading.Lock()
        self._games: dict[str, dict[str, Any]] = {}

    def start(
        self,
        nickname: str,
        consent: bool,
        public_consent: bool,
        session_id: str | None = None,
        ranking_consent: bool | None = None,
    ) -> dict[str, Any]:
        if not consent:
            raise RescueConflict("consent_required")
        if ranking_consent is None:
            ranking_consent = public_consent
        session = (
            {"session_id": session_id}
            if session_id else self.repository.create_session(
                nickname, public_consent, ranking_consent
            )
        )
        now = datetime.now(timezone.utc)
        challenge_type = choose_challenge()
        game = {
            "session_id": session["session_id"], "nickname": nickname,
            "started_at": now, "deadline_at": now + timedelta(seconds=TIME_LIMIT_SEC),
            "turn_no": 1, "challenge_type": challenge_type, "difficulty": 100,
            "score": 0, "coins": 0, "combo": 0, "turns": [], "status": "playing",
            "mio_message": CHALLENGES[challenge_type]["message"],
            "choices": choices_for(challenge_type),
            "ranking_consent": ranking_consent,
        }
        with self._lock:
            self._games[session["session_id"]] = game
        return self._state_payload(game)

    def submit_turn(self, session_id: str, turn_no: int, answer_type: str, user_answer: str) -> dict[str, Any]:
        masked_answer = mask_personal_information(user_answer.strip())
        with self._lock:
            game = self._games.get(session_id)
            if not game:
                raise RescueNotFound("session_not_found")
            if turn_no < game["turn_no"]:
                stored = next(
                    (item for item in game["turns"] if item["turn_no"] == turn_no),
                    None,
                )
                if not stored or stored["user_answer"] != masked_answer:
                    raise RescueConflict("turn_already_answered")
                return stored["response"]
            if turn_no != game["turn_no"]:
                raise RescueConflict("stale_turn")
            if game["status"] != "playing":
                return {
                    "accepted": False,
                    "game_finished": True,
                    "result": game["result"],
                }
            if datetime.now(timezone.utc) >= game["deadline_at"]:
                result = self._finish_game(game, False)
                return {"accepted": False, "game_finished": True, "result": result, "time_remaining_sec": 0}
            quality = fallback_quality(masked_answer, game["challenge_type"], contains_unsafe_content(masked_answer))
            scored = score_turn(
                answer=masked_answer, answer_type=answer_type, cosine=0.78,
                repeat_similarity=None, quality=quality, elapsed_sec=5,
                combo_before=game["combo"], difficulty_before=game["difficulty"],
            )
            game["combo"] = scored.combo
            game["difficulty"] = scored.difficulty_after
            game["turn_no"] += 1
            game["challenge_type"] = challenge_for_turn(game["turn_no"])
            game["mio_message"] = CHALLENGES[game["challenge_type"]]["message"]
            game["choices"] = choices_for(game["challenge_type"])
            finished = game["difficulty"] == 0
            turn_record = {
                **scored.as_dict(),
                "turn_no": turn_no,
                "user_answer": masked_answer,
                "answer_type": answer_type,
                "penalty": scored.unsafe_penalty + scored.offtopic_penalty + scored.repeat_penalty,
                "empathy": scored.empathy,
                "action": scored.action,
                "speed": scored.speed,
            }
            if quality.get("curated_choice"):
                turn_record["choice_quality"] = quality["choice_quality"]
            game["turns"].append(turn_record)
            game["score"] = final_score(game["turns"], finished)
            game["coins"] = game["score"] // 5
            response = {
                "accepted": True, "turn_no": turn_no,
                "time_remaining_sec": max(0, int((game["deadline_at"] - datetime.now(timezone.utc)).total_seconds())),
                "turn_score": scored.total, "score_detail": scored.as_dict(),
                "total_score": game["score"], "coins": game["coins"],
                "difficulty": game["difficulty"], "combo": game["combo"],
                "challenge_type": game["challenge_type"],
                "mio_message": game["mio_message"], "emotion": "relieved",
                "choices": game["choices"], "game_finished": finished,
            }
            if finished:
                response["result"] = self._finish_game(game, True)
            turn_record["response"] = response
            return response

    def state(self, session_id: str) -> dict[str, Any]:
        game = self._games.get(session_id)
        if not game:
            raise RescueNotFound("session_not_found")
        return self._state_payload(game)

    def finish(self, session_id: str) -> dict[str, Any]:
        game = self._games.get(session_id)
        if not game:
            raise RescueNotFound("session_not_found")
        if datetime.now(timezone.utc) < game["deadline_at"] and game["difficulty"] > 0:
            raise RescueNotReady("game_is_still_running")
        return self._finish_game(game, game["difficulty"] == 0)

    def result(self, session_id: str) -> dict[str, Any]:
        game = self._games.get(session_id)
        if not game:
            raise RescueNotFound("session_not_found")
        if game["status"] == "playing":
            raise RescueNotReady("game_is_still_running")
        return game["result"]

    def scoreboard(self) -> dict[str, Any]:
        finished = [
            game for game in self._games.values()
            if game["status"] == "finished" and game.get("ranking_consent", False)
        ]
        finished.sort(key=lambda item: (-item["result"]["final_score"], item["result"]["ended_at"]))
        ranking = [{"rank": index, "nickname": game["nickname"], "score": game["result"]["final_score"], "rank_label": game["result"]["rank_label"], "session_id": game["session_id"]} for index, game in enumerate(finished[:5], 1)]
        latest_game = max(finished, key=lambda item: item["result"]["ended_at"], default=None)
        latest = None
        if latest_game:
            latest = {
                "nickname": latest_game["nickname"],
                "score": latest_game["result"]["final_score"],
                "rank_label": latest_game["result"]["rank_label"],
                "session_id": latest_game["session_id"],
            }
        return {"top_score": ranking[0]["score"] if ranking else 0, "latest": latest, "ranking": ranking, "completed_games": len(finished)}

    def standing(self, session_id: str) -> dict[str, Any] | None:
        finished = [
            game for game in self._games.values()
            if game["status"] == "finished" and game.get("ranking_consent", False)
        ]
        finished.sort(key=lambda item: (-item["result"]["final_score"], item["result"]["ended_at"]))
        for position, game in enumerate(finished, start=1):
            if game["session_id"] == session_id:
                return {
                    "position": position,
                    "score": game["result"]["final_score"],
                    "rank_label": game["result"]["rank_label"],
                }
        return None

    def detail(self, session_id: str) -> dict[str, Any] | None:
        game = self._games.get(session_id)
        return game.get("result") if game else None

    def _finish_game(self, game: dict[str, Any], cleared: bool) -> dict[str, Any]:
        if game["status"] == "finished":
            return game["result"]
        score = final_score(game["turns"], cleared)
        rank = rank_for(score)
        result = {"nickname": game["nickname"], "final_score": score, "coins": score // 5, "rank_label": rank, "title_label": title_for(score, game["turns"]), "mio_message": result_message(rank, cleared), "status": "finished", "cleared": cleared, "ended_at": datetime.now(timezone.utc).isoformat()}
        game["status"] = "finished"
        game["result"] = result
        return result

    @staticmethod
    def _state_payload(game: dict[str, Any]) -> dict[str, Any]:
        return {"session_id": game["session_id"], "time_limit_sec": TIME_LIMIT_SEC, "started_at": game["started_at"].isoformat(), "deadline_at": game["deadline_at"].isoformat(), "turn_no": game["turn_no"], "challenge_type": game["challenge_type"], "challenge_label": CHALLENGES[game["challenge_type"]]["label"], "difficulty": game["difficulty"], "score": max(0, game["score"]), "coins": game["coins"], "combo": game["combo"], "mio_message": game["mio_message"], "emotion": "anxious", "choices": game["choices"], "game_finished": game["status"] != "playing", "time_remaining_sec": max(0, int((game["deadline_at"] - datetime.now(timezone.utc)).total_seconds())), "expired": datetime.now(timezone.utc) >= game["deadline_at"]}


def build_rescue_service(repository: Any) -> AdbRescueService | MemoryRescueService:
    if callable(getattr(repository, "connection", None)):
        return AdbRescueService(repository)
    return MemoryRescueService(repository)
