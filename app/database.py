from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import tempfile
import threading
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Protocol

import oracledb

from .config import Settings
from .embedding import (
    cosine_similarity,
    demo_embedding,
    sparse_vector_literal,
    vector_literal,
)
from .personas import PERSONAS, SEED_PARTICIPANTS


LOGGER = logging.getLogger(__name__)


SURVEY_QUESTION = "理想の上司は？ 一言と、その理由を教えてください。"

DB_EMBED_CREDENTIAL = "MIO_OCI_GENAI_CRED"
DB_EMBED_PROVIDER = "ocigenai"
DB_EMBED_MODEL = "cohere.embed-v4.0"
DB_EMBED_REGION = "us-chicago-1"
DB_EMBED_DIMENSION = 1536
DB_EMBED_URL = (
    "https://inference.generativeai.us-chicago-1.oci.oraclecloud.com/"
    "20231130/actions/embedText"
)


def db_embedding_parameters() -> str:
    """Return the minimal parameter set accepted by ADB's OCI GenAI provider."""
    return json.dumps(
        {
            "provider": DB_EMBED_PROVIDER,
            "credential_name": DB_EMBED_CREDENTIAL,
            "url": DB_EMBED_URL,
            "model": DB_EMBED_MODEL,
        }
    )


def _cosine_score(value: float) -> float:
    """Return the actual cosine similarity for user-facing percentages."""
    return round(max(0.0, min(1.0, float(value))), 4)


class Repository(Protocol):
    mode: str

    def create_session(
        self, nickname: str, public_consent: bool, ranking_consent: bool = False
    ) -> dict[str, Any]: ...

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        source_labels: list[str] | None = None,
        latency_ms: int | None = None,
    ) -> None: ...

    def save_survey(
        self,
        session_id: str,
        answer: str,
        vector: list[float],
        persona_name: str,
    ) -> None: ...

    def find_matches(
        self, session_id: str, vector: list[float], limit: int = 3
    ) -> list[dict[str, Any]]: ...

    def business_context(self, message: str) -> tuple[str, list[str]]: ...

    def record_metric(
        self,
        event_name: str,
        session_id: str | None,
        duration_ms: int | None,
        success: bool,
    ) -> None: ...

    def stats(self) -> dict[str, Any]: ...

    def network_graph(self) -> dict[str, Any]: ...

    def list_participants(self) -> list[dict[str, Any]]: ...

    def delete_participants(self, session_ids: list[str]) -> dict[str, int]: ...

    def get_participant_detail(self, session_id: str) -> dict[str, Any]: ...


class MemoryRepository:
    mode = "memory"
    driver = "memory"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, dict[str, Any]] = {}
        self._messages: list[dict[str, Any]] = []
        self._metrics: list[dict[str, Any]] = []
        self._seed()

    def _seed(self) -> None:
        now = datetime.now(timezone.utc)
        for index, (session_id, nickname, answer, persona) in enumerate(
            SEED_PARTICIPANTS, start=1
        ):
            self._sessions[session_id] = {
                "session_id": session_id,
                "nickname": nickname,
                "public_consent": True,
                "ranking_consent": False,
                "answer": answer,
                "vector": demo_embedding(answer),
                "persona_name": persona,
                "is_seed": True,
                "created_at": now - timedelta(minutes=35 - index * 4),
            }

    def create_session(
        self, nickname: str, public_consent: bool, ranking_consent: bool = False
    ) -> dict[str, Any]:
        session_id = uuid.uuid4().hex
        session = {
            "session_id": session_id,
            "nickname": nickname,
            "public_consent": public_consent,
            "ranking_consent": ranking_consent,
            "answer": None,
            "vector": None,
            "persona_name": None,
            "is_seed": False,
            "created_at": datetime.now(timezone.utc),
        }
        with self._lock:
            self._sessions[session_id] = session
        return {"session_id": session_id, "nickname": nickname}

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        source_labels: list[str] | None = None,
        latency_ms: int | None = None,
    ) -> None:
        with self._lock:
            self._messages.append(
                {
                    "session_id": session_id,
                    "role": role,
                    "content": content,
                    "source_labels": source_labels or [],
                    "latency_ms": latency_ms,
                    "created_at": datetime.now(timezone.utc),
                }
            )

    def save_survey(
        self,
        session_id: str,
        answer: str,
        vector: list[float],
        persona_name: str,
    ) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise KeyError("session_not_found")
            session.update(answer=answer, vector=vector, persona_name=persona_name)

    def find_matches(
        self, session_id: str, vector: list[float], limit: int = 3
    ) -> list[dict[str, Any]]:
        ranked: list[dict[str, Any]] = []
        with self._lock:
            candidates = list(self._sessions.values())
        for candidate in candidates:
            if (
                candidate["session_id"] == session_id
                or not candidate.get("public_consent")
                or candidate.get("vector") is None
            ):
                continue
            raw = cosine_similarity(vector, candidate["vector"])
            score = _cosine_score(raw)
            ranked.append(
                {
                    "nickname": candidate["nickname"],
                    "persona_name": candidate["persona_name"],
                    "score": round(score, 4),
                    "reason": _match_reason(candidate.get("answer", "")),
                }
            )
        return sorted(ranked, key=lambda item: item["score"], reverse=True)[:limit]

    def business_context(self, message: str) -> tuple[str, list[str]]:
        return _fallback_business_context(message)

    def record_metric(
        self,
        event_name: str,
        session_id: str | None,
        duration_ms: int | None,
        success: bool,
    ) -> None:
        with self._lock:
            self._metrics.append(
                {
                    "event_name": event_name,
                    "session_id": session_id,
                    "duration_ms": duration_ms,
                    "success": success,
                }
            )

    def stats(self) -> dict[str, Any]:
        with self._lock:
            sessions = list(self._sessions.values())
        completed = [session for session in sessions if session.get("persona_name")]
        persona_counts: dict[str, int] = {}
        for session in completed:
            persona = session["persona_name"]
            persona_counts[persona] = persona_counts.get(persona, 0) + 1
        recent = sorted(
            (item for item in completed if item.get("public_consent")),
            key=lambda item: item["created_at"],
            reverse=True,
        )
        return {
            "participants": len(sessions),
            "completed": len(completed),
            "persona_counts": persona_counts,
            "recent": [
                {
                    "nickname": item["nickname"],
                    "persona_name": item["persona_name"],
                    "session_id": item["session_id"],
                }
                for item in recent
            ],
        }

    def network_graph(self) -> dict[str, Any]:
        with self._lock:
            sessions = list(self._sessions.values())
        return _build_network_graph(sessions)

    def list_participants(self) -> list[dict[str, Any]]:
        with self._lock:
            sessions = list(self._sessions.values())
            message_counts: dict[str, int] = {}
            for message in self._messages:
                session_id = message["session_id"]
                message_counts[session_id] = message_counts.get(session_id, 0) + 1
        return [
            _participant_record(item, message_counts.get(item["session_id"], 0))
            for item in sorted(
                sessions,
                key=lambda session: str(session.get("created_at", "")),
                reverse=True,
            )
        ]

    def delete_participants(self, session_ids: list[str]) -> dict[str, int]:
        selected = set(_validated_session_ids(session_ids))
        with self._lock:
            deletable = {
                session_id
                for session_id in selected
                if session_id in self._sessions
                and not bool(self._sessions[session_id].get("is_seed"))
            }
            skipped_seed = sum(
                1
                for session_id in selected
                if session_id in self._sessions
                and bool(self._sessions[session_id].get("is_seed"))
            )
            for session_id in deletable:
                self._sessions.pop(session_id, None)
            self._messages = [
                item for item in self._messages if item.get("session_id") not in deletable
            ]
            self._metrics = [
                item for item in self._metrics if item.get("session_id") not in deletable
            ]
        return {"deleted": len(deletable), "skipped_seed": skipped_seed}

    def get_participant_detail(self, session_id: str) -> dict[str, Any]:
        _validated_session_ids([session_id])
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise KeyError("session_not_found")
            messages = [
                dict(item) for item in self._messages
                if item.get("session_id") == session_id
            ]
        vector = session.get("vector") or []
        return {
            "participant": _participant_record(session, len(messages)),
            "initial_qa": {
                "vectorized": False,
                "messages": [_message_record(item) for item in messages],
            },
            "office_preference": {
                "question": SURVEY_QUESTION,
                "answer": session.get("answer") or "",
                "vectorized": bool(vector),
                "storage_type": "VECTOR(1024, FLOAT32)",
                "dimension": len(vector),
                "values": [round(float(value), 7) for value in vector],
            },
        }


class SqlclAdbRepository:
    """ADB repository backed by one long-lived SQLcl connection.

    The supplied cloud wallet includes an SSO wallet, while python-oracledb Thin
    mode needs a separate PEM passphrase. SQLcl can use the SSO wallet directly,
    so this adapter keeps credentials out of process arguments and still uses
    Oracle VECTOR operations for the live demo.
    """

    mode = "adb"
    driver = "sqlcl"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        if not settings.adb_wallet_zip.exists():
            raise FileNotFoundError(f"ADB wallet not found: {settings.adb_wallet_zip}")
        self._lock = threading.Lock()
        self._sessions: dict[str, dict[str, Any]] = {}
        self._business_rows: list[dict[str, Any]] = []
        self._customer_row: dict[str, Any] | None = None
        self._connect()
        self._seed_if_needed()
        self._refresh_cache()

    def _connect(self) -> None:
        self._run(
            "select 'MIO_PING:1' from dual;",
            timeout=45,
            expect="MIO_PING:1",
        )

    def _run(self, sql: str, timeout: int = 30, expect: str | None = None) -> str:
        escaped_password = self.settings.adb_password.replace('"', '""')
        sql_file: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".sql",
                prefix="mio_demo_",
                dir="/tmp",
                delete=False,
            ) as handle:
                sql_file = handle.name
                handle.write(
                    "set heading off feedback off pagesize 0 linesize 32767 "
                    "trimspool on echo off\n"
                    "set define off\n"
                    "set sqlblanklines on\n"
                    "whenever sqlerror continue\n"
                    f"{sql.rstrip()}\n"
                )
            script = (
                f'connect {self.settings.adb_user}/"{escaped_password}"@{self.settings.adb_dsn}\n'
                f"@{sql_file}\n"
                "exit\n"
            )
            with self._lock:
                completed = subprocess.run(
                    [
                        "sql",
                        "-S",
                        "-cloudconfig",
                        str(self.settings.adb_wallet_zip),
                        "/nolog",
                    ],
                    cwd=Path(__file__).resolve().parent.parent,
                    input=script,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
        finally:
            if sql_file:
                try:
                    os.unlink(sql_file)
                except FileNotFoundError:
                    pass
        decoded = completed.stdout
        if "ORA-" in decoded or "SP2-" in decoded or "Error starting at line" in decoded:
            safe_lines = [
                line for line in decoded.splitlines()
                if "ORA-" in line or "SP2-" in line or "Error" in line
            ]
            raise RuntimeError("; ".join(safe_lines[-4:]) or "ADB SQL failed")
        if completed.returncode != 0:
            raise RuntimeError(f"SQLcl exited with status {completed.returncode}")
        if expect and expect not in decoded:
            raise RuntimeError(f"ADB response marker missing: {expect}")
        return decoded

    def _json_rows(self, sql: str) -> list[dict[str, Any]]:
        output = self._run(sql)
        rows: list[dict[str, Any]] = []
        for line in output.splitlines():
            position = line.find("MIO_JSON:")
            if position < 0:
                continue
            payload = line[position + len("MIO_JSON:") :].strip()
            try:
                rows.append(json.loads(payload))
            except json.JSONDecodeError:
                continue
        return rows

    def _seed_if_needed(self) -> None:
        existing_rows = self._json_rows(
            """
            select 'MIO_JSON:' || json_object(
                'session_id' value session_id returning varchar2(32767)
            ) from mio_demo_sessions where is_seed = 1;
            """
        )
        existing = {row["session_id"] for row in existing_rows}
        for session_id, nickname, answer, persona in SEED_PARTICIPANTS:
            if session_id in existing:
                continue
            self._run(
                f"""
                merge into mio_demo_sessions target
                using (select '{session_id}' session_id from dual) source
                on (target.session_id = source.session_id)
                when not matched then insert (
                    session_id, nickname, public_consent, persona_name,
                    answer_text, answer_vector, is_seed, expires_at
                ) values (
                    source.session_id, {_sql_text(nickname)}, 1, {_sql_text(persona)},
                    {_sql_text(answer)}, null, 1,
                    systimestamp + interval '30' day
                );
                commit;
                """
            )
            self._run(
                f"""
                update mio_demo_sessions
                set answer_vector = {_vector_sql(demo_embedding(answer))}
                where session_id = '{session_id}';
                commit;
                """
            )

    def _refresh_cache(self) -> None:
        rows = self._json_rows(
            """
            select 'MIO_JSON:' || json_object(
                'kind' value 'session', 'session_id' value session_id,
                'nickname' value nickname, 'consent' value public_consent,
                'ranking_consent' value ranking_consent,
                'persona_name' value persona_name, 'is_seed' value is_seed,
                'answer' value answer_text,
                'created_at' value to_char(created_at, 'YYYY-MM-DD"T"HH24:MI:SS')
                returning varchar2(32767)
            ) from mio_demo_sessions order by created_at;
            select 'MIO_JSON:' || json_object(
                'kind' value 'business', 'label' value metric_label,
                'value' value metric_value, 'unit' value unit_name,
                'period' value period_label returning varchar2(32767)
            ) from mio_demo_business_metrics order by display_order;
            select 'MIO_JSON:' || json_object(
                'kind' value 'customer', 'name' value customer_name,
                'health' value health_score, 'usage' value usage_change_pct,
                'tickets' value open_tickets, 'renewal' value renewal_days
                returning varchar2(32767)
            ) from mio_demo_customers where customer_key = 'A-CORP';
            """,
        )
        for row in rows:
            if row.get("kind") == "session":
                self._sessions[row["session_id"]] = row
            elif row.get("kind") == "business":
                self._business_rows.append(row)
            elif row.get("kind") == "customer":
                self._customer_row = row

    def create_session(
        self, nickname: str, public_consent: bool, ranking_consent: bool = False
    ) -> dict[str, Any]:
        session_id = uuid.uuid4().hex
        self._run(
            f"""
            insert into mio_demo_sessions (
                session_id, nickname, public_consent, ranking_consent, is_seed, expires_at
            ) values (
                '{session_id}', {_sql_text(nickname)}, {1 if public_consent else 0},
                {1 if ranking_consent else 0}, 0, systimestamp + interval '30' day
            );
            insert into mio_demo_metrics (event_name, session_id, success_flag)
            values ('session_started', '{session_id}', 1);
            commit;
            """
        )
        self._sessions[session_id] = {
            "session_id": session_id,
            "nickname": nickname,
            "consent": 1 if public_consent else 0,
            "ranking_consent": 1 if ranking_consent else 0,
            "persona_name": None,
            "answer": None,
            "vector": None,
            "is_seed": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return {"session_id": session_id, "nickname": nickname}

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        source_labels: list[str] | None = None,
        latency_ms: int | None = None,
    ) -> None:
        latency = "null" if latency_ms is None else str(int(latency_ms))
        self._run(
            f"""
            insert into mio_demo_messages (
                session_id, role_name, content_text, source_labels, latency_ms
            ) values (
                '{session_id}', {_sql_text(role)}, {_sql_text(content)},
                {_sql_text(json.dumps(source_labels or [], ensure_ascii=False))}, {latency}
            );
            commit;
            """
        )

    def save_survey(
        self,
        session_id: str,
        answer: str,
        vector: list[float],
        persona_name: str,
    ) -> None:
        output = self._run(
            f"""
            update mio_demo_sessions
            set answer_text = {_sql_text(answer)},
                answer_vector = {_vector_sql(vector)},
                persona_name = {_sql_text(persona_name)}
            where session_id = '{session_id}';
            select 'MIO_UPDATED:' || count(*)
            from mio_demo_sessions where session_id = '{session_id}';
            commit;
            """
        )
        if "MIO_UPDATED:0" in output:
            raise KeyError("session_not_found")
        if session_id in self._sessions:
            self._sessions[session_id].update(
                persona_name=persona_name, answer=answer, vector=vector
            )

    def chat_exchange(
        self,
        session_id: str,
        user_message: str,
        assistant_message: str,
        source_labels: list[str],
        latency_ms: int,
    ) -> None:
        self._run(
            f"""
            insert into mio_demo_messages (
                session_id, role_name, content_text, source_labels
            ) values (
                '{session_id}', 'user', {_sql_text(user_message)}, '[]'
            );
            insert into mio_demo_messages (
                session_id, role_name, content_text, source_labels, latency_ms
            ) values (
                '{session_id}', 'assistant', {_sql_text(assistant_message)},
                {_sql_text(json.dumps(source_labels, ensure_ascii=False))}, {int(latency_ms)}
            );
            insert into mio_demo_metrics (
                event_name, session_id, duration_ms, success_flag
            ) values ('chat_completed', '{session_id}', {int(latency_ms)}, 1);
            commit;
            """
        )

    def save_survey_and_find(
        self,
        session_id: str,
        answer: str,
        vector: list[float],
        persona_name: str,
        latency_ms: int,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        vector_expression = _vector_sql(vector)
        rows = self._json_rows(
            f"""
            update mio_demo_sessions
            set answer_text = {_sql_text(answer)},
                answer_vector = {vector_expression},
                persona_name = {_sql_text(persona_name)}
            where session_id = '{session_id}';
            insert into mio_demo_metrics (
                event_name, session_id, duration_ms, success_flag
            ) values ('survey_completed', '{session_id}', {int(latency_ms)}, 1);
            commit;
            select 'MIO_JSON:' || json_object(
                'nickname' value nickname,
                'persona_name' value persona_name,
                'answer' value answer_text,
                'similarity' value greatest(0, 1 - vector_distance(
                    answer_vector, {vector_expression}, cosine
                )) returning varchar2(32767)
            )
            from mio_demo_sessions
            where session_id <> '{session_id}'
              and public_consent = 1
              and answer_vector is not null
            order by vector_distance(
                answer_vector, {vector_expression}, cosine
            )
            fetch first {int(limit)} rows only;
            """,
        )
        if session_id in self._sessions:
            self._sessions[session_id].update(
                persona_name=persona_name, answer=answer, vector=vector
            )
        return [
            {
                "nickname": row["nickname"],
                "persona_name": row.get("persona_name"),
                "score": _cosine_score(row["similarity"]),
                "reason": _match_reason(row.get("answer", "")),
            }
            for row in rows
        ]

    def find_matches(
        self, session_id: str, vector: list[float], limit: int = 3
    ) -> list[dict[str, Any]]:
        rows = self._json_rows(
            f"""
            select 'MIO_JSON:' || json_object(
                'nickname' value nickname,
                'persona_name' value persona_name,
                'answer' value answer_text,
                'similarity' value greatest(0, 1 - vector_distance(
                    answer_vector, {_vector_sql(vector)}, cosine
                )) returning varchar2(32767)
            )
            from mio_demo_sessions
            where session_id <> '{session_id}'
              and public_consent = 1
              and answer_vector is not null
            order by vector_distance(
                answer_vector, {_vector_sql(vector)}, cosine
            )
            fetch first {int(limit)} rows only;
            """
        )
        return [
            {
                "nickname": row["nickname"],
                "persona_name": row.get("persona_name"),
                "score": _cosine_score(row["similarity"]),
                "reason": _match_reason(row.get("answer", "")),
            }
            for row in rows
        ]

    def business_context(self, message: str) -> tuple[str, list[str]]:
        if any(word in message for word in ("売上", "解約", "MRR")):
            rows = self._business_rows
            if rows:
                return (
                    "、".join(
                        f"{row['label']}は{row['value']}{row['unit']}（{row['period']}）"
                        for row in rows
                    ),
                    ["MIO_DEMO_BUSINESS_METRICS"],
                )
        if "A社" in message or "顧客" in message:
            rows = [self._customer_row] if self._customer_row else []
            if rows:
                row = rows[0]
                return (
                    f"{row['name']}のヘルススコアは{row['health']}、利用率は前月比"
                    f"{float(row['usage']):+g}%、未解決チケットは{row['tickets']}件、"
                    f"契約更新まで{row['renewal']}日です。",
                    ["MIO_DEMO_CUSTOMERS"],
                )
        return _fallback_business_context(message)

    def record_metric(
        self,
        event_name: str,
        session_id: str | None,
        duration_ms: int | None,
        success: bool,
    ) -> None:
        # Success metrics are committed with the matching transaction above.
        # Failure metrics remain local to avoid triggering a second ADB login
        # while already handling an error.
        return None

    def stats(self) -> dict[str, Any]:
        sessions = list(self._sessions.values())
        completed = [item for item in sessions if item.get("persona_name")]
        counts: dict[str, int] = {}
        for item in completed:
            name = item["persona_name"]
            counts[name] = counts.get(name, 0) + 1
        recent_rows = sorted(
            (item for item in completed if int(item.get("consent", 0))),
            key=lambda item: item.get("created_at", ""),
            reverse=True,
        )
        recent = [
            {
                "nickname": row["nickname"],
                "persona_name": row["persona_name"],
                "session_id": row["session_id"],
            }
            for row in recent_rows
        ]
        return {
            "participants": len(sessions),
            "completed": len(completed),
            "persona_counts": counts,
            "recent": recent,
        }

    def network_graph(self) -> dict[str, Any]:
        return _build_network_graph(list(self._sessions.values()))

    def list_participants(self) -> list[dict[str, Any]]:
        rows = self._json_rows(
            """
            select 'MIO_JSON:' || json_object(
                'session_id' value s.session_id,
                'nickname' value s.nickname,
                'consent' value s.public_consent,
                'ranking_consent' value s.ranking_consent,
                'persona_name' value s.persona_name,
                'answer' value s.answer_text,
                'is_seed' value s.is_seed,
                'created_at' value to_char(
                    sys_extract_utc(s.created_at),
                    'YYYY-MM-DD"T"HH24:MI:SS"Z"'
                ),
                'message_count' value (
                    select count(*) from mio_demo_messages m
                    where m.session_id = s.session_id
                ) returning varchar2(32767)
            )
            from mio_demo_sessions s
            order by s.created_at desc;
            """
        )
        return [
            _participant_record(row, int(row.get("message_count", 0)))
            for row in rows
        ]

    def delete_participants(self, session_ids: list[str]) -> dict[str, int]:
        selected = _validated_session_ids(session_ids)
        deletable = [
            session_id
            for session_id in selected
            if session_id in self._sessions
            and not bool(int(self._sessions[session_id].get("is_seed", 0)))
        ]
        skipped_seed = sum(
            1
            for session_id in selected
            if session_id in self._sessions
            and bool(int(self._sessions[session_id].get("is_seed", 0)))
        )
        if not deletable:
            return {"deleted": 0, "skipped_seed": skipped_seed}

        sql_ids = ",".join(f"'{session_id}'" for session_id in deletable)
        self._run(
            f"""
            delete from mio_demo_metrics where session_id in ({sql_ids});
            delete from mio_demo_messages where session_id in ({sql_ids});
            delete from mio_demo_sessions
            where is_seed = 0 and session_id in ({sql_ids});
            commit;
            """
        )
        for session_id in deletable:
            self._sessions.pop(session_id, None)
        return {"deleted": len(deletable), "skipped_seed": skipped_seed}

    def get_participant_detail(self, session_id: str) -> dict[str, Any]:
        _validated_session_ids([session_id])
        session = self._sessions.get(session_id)
        if not session:
            raise KeyError("session_not_found")
        answer = session.get("answer") or ""
        vector = session.get("vector") or (demo_embedding(answer) if answer else [])
        return {
            "participant": _participant_record(session, 0),
            "initial_qa": {"vectorized": False, "messages": []},
            "office_preference": {
                "question": SURVEY_QUESTION,
                "answer": answer,
                "vectorized": bool(vector),
                "storage_type": "VECTOR(1024, FLOAT32)",
                "dimension": len(vector),
                "values": [round(float(value), 7) for value in vector],
            },
        }

    def close(self) -> None:
        return None


def _sql_text(value: str) -> str:
    encoded = base64.b64encode(value.encode("utf-8")).decode("ascii")
    return (
        "utl_i18n.raw_to_char("
        f"utl_encode.base64_decode(utl_raw.cast_to_raw('{encoded}')), 'AL32UTF8')"
    )


def _vector_sql(vector: list[float]) -> str:
    sparse = sparse_vector_literal(vector)
    return (
        f"to_vector(to_vector('{sparse}', {len(vector)}, float32, sparse), "
        f"{len(vector)}, float32, dense)"
    )


class AdbRepository:
    mode = "adb"
    driver = "python-oracledb-thick"
    embedding_mode = "dbms_vector_chain/ocigenai/cohere.embed-v4.0"
    embedding_provider = DB_EMBED_PROVIDER
    embedding_model = DB_EMBED_MODEL
    embedding_region = DB_EMBED_REGION
    embedding_dimension = DB_EMBED_DIMENSION

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.wallet_dir = Path("/tmp/mio_demo_wallet")
        self._pool: oracledb.ConnectionPool | None = None
        self._prepare_wallet()
        use_thick = settings.oracle_client_lib.exists()
        if use_thick and oracledb.is_thin_mode():
            # The bundled full client needs ORACLE_HOME to locate its message
            # and network files before python-oracledb initializes Thick mode.
            os.environ["ORACLE_HOME"] = str(settings.oracle_client_lib.parent)
            oracledb.init_oracle_client(
                lib_dir=str(settings.oracle_client_lib),
                config_dir=str(self.wallet_dir),
            )
        pool_options: dict[str, Any] = {}
        if not use_thick:
            if not settings.adb_wallet_password:
                raise RuntimeError(
                    "MIO_ADB_WALLET_PASSWORD is required for python-oracledb Thin mode"
                )
            self.driver = "python-oracledb-thin"
            pool_options.update(
                config_dir=str(self.wallet_dir),
                wallet_location=str(self.wallet_dir),
                wallet_password=settings.adb_wallet_password,
            )
        self._pool = oracledb.create_pool(
            user=settings.adb_user,
            password=settings.adb_password,
            dsn=settings.adb_dsn,
            min=1,
            max=4,
            increment=1,
            getmode=oracledb.POOL_GETMODE_WAIT,
            **pool_options,
        )
        self._ping()
        self._seed_if_needed()
        self.cleanup_expired()

    def _prepare_wallet(self) -> None:
        if not self.settings.adb_wallet_zip.exists():
            raise FileNotFoundError(f"ADB wallet not found: {self.settings.adb_wallet_zip}")
        self.wallet_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        with zipfile.ZipFile(self.settings.adb_wallet_zip) as archive:
            archive.extractall(self.wallet_dir)
        (self.wallet_dir / "sqlnet.ora").write_text(
            "WALLET_LOCATION = (SOURCE = (METHOD = file) "
            f'(METHOD_DATA = (DIRECTORY="{self.wallet_dir}")))\n'
            "SSL_SERVER_DN_MATCH=yes\n",
            encoding="utf-8",
        )
        for child in self.wallet_dir.iterdir():
            child.chmod(0o600)

    @contextmanager
    def connection(self) -> Iterator[oracledb.Connection]:
        if self._pool is None:
            raise RuntimeError("ADB pool is not initialized")
        connection = self._pool.acquire()
        try:
            yield connection
        finally:
            self._pool.release(connection)

    def _ping(self) -> None:
        with self.connection() as connection:
            connection.ping()
            with connection.cursor() as cursor:
                cursor.execute("select count(*) from mio_demo_sessions")
                cursor.fetchone()

    def cleanup_expired(self) -> None:
        """Delete expired participant data and its rescue-player orphan rows."""
        with self.connection() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        delete from mio_demo_metrics
                        where session_id in (
                          select session_id from mio_demo_sessions
                          where is_seed = 0 and expires_at <= systimestamp
                        )
                        """
                    )
                    cursor.execute(
                        """
                        delete from mio_demo_sessions
                        where is_seed = 0 and expires_at <= systimestamp
                        """
                    )
                    cursor.execute(
                        """
                        delete from mio_players p
                        where not exists (
                          select 1 from mio_game_sessions g
                          where g.player_id = p.player_id
                        )
                        """
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                LOGGER.exception("expired participant cleanup failed")
                raise

    def _seed_if_needed(self) -> None:
        with self.connection() as connection:
            with connection.cursor() as cursor:
                for session_id, nickname, answer, persona in SEED_PARTICIPANTS:
                    cursor.execute(
                        """
                        merge into mio_demo_sessions target
                        using (select :session_id session_id from dual) source
                        on (target.session_id = source.session_id)
                        when not matched then insert (
                            session_id, nickname, public_consent, persona_name,
                            answer_text, answer_vector, is_seed, expires_at
                        ) values (
                            :session_id, :nickname, 1, :persona_name,
                            :answer_text, to_vector(:answer_vector), 1,
                            systimestamp + interval '30' day
                        )
                        """,
                        session_id=session_id,
                        nickname=nickname,
                        persona_name=persona,
                        answer_text=answer,
                        answer_vector=vector_literal(demo_embedding(answer)),
                    )
            connection.commit()

    def create_session(
        self, nickname: str, public_consent: bool, ranking_consent: bool = False
    ) -> dict[str, Any]:
        session_id = uuid.uuid4().hex
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into mio_demo_sessions (
                        session_id, nickname, public_consent, ranking_consent,
                        is_seed, expires_at
                    ) values (
                        :session_id, :nickname, :consent, :ranking_consent,
                        0, systimestamp + interval '30' day
                    )
                    """,
                    session_id=session_id,
                    nickname=nickname,
                    consent=1 if public_consent else 0,
                    ranking_consent=1 if ranking_consent else 0,
                )
            connection.commit()
        return {"session_id": session_id, "nickname": nickname}

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        source_labels: list[str] | None = None,
        latency_ms: int | None = None,
    ) -> None:
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into mio_demo_messages (
                        session_id, role_name, content_text, source_labels, latency_ms
                    ) values (:session_id, :role_name, :content_text, :source_labels, :latency_ms)
                    """,
                    session_id=session_id,
                    role_name=role,
                    content_text=content,
                    source_labels=json.dumps(source_labels or [], ensure_ascii=False),
                    latency_ms=latency_ms,
                )
            connection.commit()

    def save_survey(
        self,
        session_id: str,
        answer: str,
        vector: list[float],
        persona_name: str,
    ) -> None:
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    update mio_demo_sessions
                    set answer_text = :answer_text,
                        answer_vector = to_vector(:answer_vector),
                        persona_name = :persona_name
                    where session_id = :session_id
                    """,
                    answer_text=answer,
                    answer_vector=vector_literal(vector),
                    persona_name=persona_name,
                    session_id=session_id,
                )
                if cursor.rowcount != 1:
                    raise KeyError("session_not_found")
            connection.commit()

    def save_survey_with_db_embedding(
        self,
        session_id: str,
        answer: str,
        persona_name: str,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """Embed, store, and search entirely inside Oracle AI Database."""
        row_limit = max(1, min(int(limit), 10))
        with self.connection() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        update mio_demo_sessions
                        set answer_text = :answer_text,
                            answer_vector_v4 = dbms_vector_chain.utl_to_embedding(
                              to_clob(:answer_text), json(:embedding_parameters)
                            ),
                            embedding_provider = :embedding_provider,
                            embedding_model = :embedding_model,
                            embedding_region = :embedding_region,
                            embedded_at = systimestamp,
                            persona_name = :persona_name
                        where session_id = :session_id
                        """,
                        {
                            "answer_text": answer,
                            "embedding_parameters": db_embedding_parameters(),
                            "embedding_provider": DB_EMBED_PROVIDER,
                            "embedding_model": DB_EMBED_MODEL,
                            "embedding_region": DB_EMBED_REGION,
                            "persona_name": persona_name,
                            "session_id": session_id,
                        },
                    )
                    if cursor.rowcount != 1:
                        raise KeyError("session_not_found")
                    cursor.execute(
                        f"""
                        select nickname,
                               persona_name,
                               answer_text,
                               greatest(0, 1 - vector_distance(
                                   answer_vector_v4,
                                   (select answer_vector_v4
                                    from mio_demo_sessions
                                    where session_id = :session_id),
                                   cosine
                               )) as similarity
                        from mio_demo_sessions
                        where session_id <> :session_id
                          and public_consent = 1
                          and answer_vector_v4 is not null
                        order by vector_distance(
                            answer_vector_v4,
                            (select answer_vector_v4
                             from mio_demo_sessions
                             where session_id = :session_id),
                            cosine
                        )
                        fetch first {row_limit} rows only
                        """,
                        session_id=session_id,
                    )
                    rows = cursor.fetchall()
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return [
            {
                "nickname": row[0],
                "persona_name": row[1],
                "score": _cosine_score(row[3]),
                "reason": _match_reason(row[2] or ""),
            }
            for row in rows
        ]

    def find_matches(
        self, session_id: str, vector: list[float], limit: int = 3
    ) -> list[dict[str, Any]]:
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select nickname,
                           persona_name,
                           answer_text,
                           greatest(0, 1 - vector_distance(
                               answer_vector, to_vector(:query_vector), cosine
                           )) as similarity
                    from mio_demo_sessions
                    where session_id <> :session_id
                      and public_consent = 1
                      and answer_vector is not null
                    order by vector_distance(
                        answer_vector, to_vector(:query_vector), cosine
                    )
                    fetch first 3 rows only
                    """,
                    query_vector=vector_literal(vector),
                    session_id=session_id,
                )
                rows = cursor.fetchall()
        return [
            {
                "nickname": row[0],
                "persona_name": row[1],
                "score": _cosine_score(row[3]),
                "reason": _match_reason(row[2] or ""),
            }
            for row in rows[:limit]
        ]

    def business_context(self, message: str) -> tuple[str, list[str]]:
        fallback, labels = _fallback_business_context(message)
        try:
            if any(word in message for word in ("売上", "解約", "MRR")):
                with self.connection() as connection:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            select metric_label, metric_value, unit_name, period_label
                            from mio_demo_business_metrics
                            order by display_order
                            """
                        )
                        rows = cursor.fetchall()
                context = "、".join(
                    f"{row[0]}は{row[1]}{row[2]}（{row[3]}）" for row in rows
                )
                return context, ["MIO_DEMO_BUSINESS_METRICS"]
            if "A社" in message or "顧客" in message:
                with self.connection() as connection:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            select customer_name, health_score, usage_change_pct,
                                   open_tickets, renewal_days
                            from mio_demo_customers
                            where customer_key = 'A-CORP'
                            """
                        )
                        row = cursor.fetchone()
                if row:
                    return (
                        f"{row[0]}のヘルススコアは{row[1]}、利用率は前月比{row[2]:+}%、"
                        f"未解決チケットは{row[3]}件、契約更新まで{row[4]}日です。",
                        ["MIO_DEMO_CUSTOMERS"],
                    )
        except Exception:
            pass
        return fallback, labels

    def record_metric(
        self,
        event_name: str,
        session_id: str | None,
        duration_ms: int | None,
        success: bool,
    ) -> None:
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into mio_demo_metrics (
                        event_name, session_id, duration_ms, success_flag
                    ) values (:event_name, :session_id, :duration_ms, :success_flag)
                    """,
                    event_name=event_name,
                    session_id=session_id,
                    duration_ms=duration_ms,
                    success_flag=1 if success else 0,
                )
            connection.commit()

    def stats(self) -> dict[str, Any]:
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select count(*) from mio_demo_sessions")
                participants = int(cursor.fetchone()[0])
                cursor.execute(
                    """
                    select persona_name, count(*)
                    from mio_demo_sessions
                    where persona_name is not null
                    group by persona_name
                    """
                )
                persona_counts = {row[0]: int(row[1]) for row in cursor.fetchall()}
                cursor.execute(
                    """
                    select nickname, persona_name, session_id
                    from mio_demo_sessions
                    where persona_name is not null
                      and public_consent = 1
                      and (expires_at is null or expires_at > systimestamp)
                    order by created_at desc
                    """
                )
                recent = [
                    {
                        "nickname": row[0],
                        "persona_name": row[1],
                        "session_id": row[2],
                    }
                    for row in cursor.fetchall()
                ]
        return {
            "participants": participants,
            "completed": sum(persona_counts.values()),
            "persona_counts": persona_counts,
            "recent": recent,
        }

    def network_graph(self) -> dict[str, Any]:
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select session_id, nickname, public_consent, persona_name,
                           answer_text, answer_vector_v4, is_seed, created_at
                    from mio_demo_sessions
                    where public_consent = 1
                      and persona_name is not null
                      and answer_text is not null
                      and answer_vector_v4 is not null
                      and (expires_at is null or expires_at > systimestamp or is_seed = 1)
                    order by created_at
                    """
                )
                rows = cursor.fetchall()
                cursor.execute(
                    """
                    select a.session_id, b.session_id,
                           vector_distance(
                             a.answer_vector_v4,
                             b.answer_vector_v4,
                             cosine
                           ) as cosine_distance
                    from mio_demo_sessions a
                    join mio_demo_sessions b on a.session_id < b.session_id
                    where a.public_consent = 1
                      and b.public_consent = 1
                      and a.persona_name is not null
                      and b.persona_name is not null
                      and a.answer_text is not null
                      and b.answer_text is not null
                      and a.answer_vector_v4 is not null
                      and b.answer_vector_v4 is not null
                      and (a.expires_at is null or a.expires_at > systimestamp or a.is_seed = 1)
                      and (b.expires_at is null or b.expires_at > systimestamp or b.is_seed = 1)
                    """
                )
                oracle_distance_rows = cursor.fetchall()
        sessions = [
            {
                "session_id": row[0],
                "nickname": row[1],
                "public_consent": bool(row[2]),
                "persona_name": row[3],
                "answer": row[4],
                "vector": list(row[5]),
                "is_seed": bool(row[6]),
                "created_at": row[7],
            }
            for row in rows
        ]
        oracle_distances = {
            tuple(sorted((str(row[0]), str(row[1])))): float(row[2])
            for row in oracle_distance_rows
        }
        return _build_network_graph(
            sessions,
            oracle_distances=oracle_distances,
            distance_source="Oracle VECTOR_DISTANCE",
        )

    def list_participants(self) -> list[dict[str, Any]]:
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select s.session_id, s.nickname,
                           s.public_consent, s.ranking_consent, s.persona_name,
                           s.answer_text, s.is_seed,
                           s.created_at,
                           (select count(*) from mio_demo_messages m
                            where m.session_id = s.session_id)
                    from mio_demo_sessions s
                    order by s.created_at desc
                    """
                )
                rows = cursor.fetchall()
        return [
            _participant_record(
                {
                    "session_id": row[0],
                    "nickname": row[1],
                    "consent": row[2],
                    "ranking_consent": row[3],
                    "persona_name": row[4],
                    "answer": row[5],
                    "is_seed": row[6],
                    "created_at": row[7],
                },
                int(row[8]),
            )
            for row in rows
        ]

    def delete_participants(self, session_ids: list[str]) -> dict[str, int]:
        selected = _validated_session_ids(session_ids)
        placeholders = ",".join(f":id{index}" for index in range(len(selected)))
        parameters = {f"id{index}": value for index, value in enumerate(selected)}
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    select session_id, is_seed from mio_demo_sessions
                    where session_id in ({placeholders})
                    """,
                    parameters,
                )
                rows = cursor.fetchall()
                deletable = [row[0] for row in rows if not bool(row[1])]
                skipped_seed = sum(1 for row in rows if bool(row[1]))
                if deletable:
                    delete_placeholders = ",".join(
                        f":delete_id{index}" for index in range(len(deletable))
                    )
                    delete_parameters = {
                        f"delete_id{index}": value
                        for index, value in enumerate(deletable)
                    }
                    player_ids: list[int] = []
                    try:
                        cursor.execute(
                            f"select player_id from mio_game_sessions where session_id in ({delete_placeholders})",
                            delete_parameters,
                        )
                        player_ids = [int(row[0]) for row in cursor.fetchall()]
                    except oracledb.DatabaseError:
                        player_ids = []
                    cursor.execute(
                        f"delete from mio_demo_metrics where session_id in ({delete_placeholders})",
                        delete_parameters,
                    )
                    cursor.execute(
                        f"delete from mio_demo_sessions where is_seed = 0 and session_id in ({delete_placeholders})",
                        delete_parameters,
                    )
                    if player_ids:
                        player_placeholders = ",".join(
                            f":player_id{index}" for index in range(len(player_ids))
                        )
                        cursor.execute(
                            f"delete from mio_players where player_id in ({player_placeholders})",
                            {
                                f"player_id{index}": value
                                for index, value in enumerate(player_ids)
                            },
                        )
            connection.commit()
        return {"deleted": len(deletable), "skipped_seed": skipped_seed}

    def get_participant_detail(self, session_id: str) -> dict[str, Any]:
        _validated_session_ids([session_id])
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select session_id, nickname, public_consent, persona_name,
                           answer_text, answer_vector_v4, is_seed, created_at,
                           embedding_provider, embedding_model,
                           embedding_region, embedded_at
                    from mio_demo_sessions
                    where session_id = :session_id
                    """,
                    session_id=session_id,
                )
                session_row = cursor.fetchone()
                if not session_row:
                    raise KeyError("session_not_found")
                cursor.execute(
                    """
                    select role_name, dbms_lob.substr(content_text, 4000, 1), source_labels,
                           latency_ms, created_at
                    from mio_demo_messages
                    where session_id = :session_id
                    order by created_at, message_id
                    """,
                    session_id=session_id,
                )
                message_rows = cursor.fetchall()

        messages = [
            _message_record(
                {
                    "role": row[0],
                    "content": _text_value(row[1]),
                    "source_labels": _json_list(row[2]),
                    "latency_ms": row[3],
                    "created_at": row[4],
                }
            )
            for row in message_rows
        ]
        vector = list(session_row[5]) if session_row[5] is not None else []
        participant = _participant_record(
            {
                "session_id": session_row[0],
                "nickname": session_row[1],
                "consent": session_row[2],
                "persona_name": session_row[3],
                "answer": session_row[4],
                "is_seed": session_row[6],
                "created_at": session_row[7],
            },
            len(messages),
        )
        return {
            "participant": participant,
            "initial_qa": {"vectorized": False, "messages": messages},
            "office_preference": {
                "question": SURVEY_QUESTION,
                "answer": session_row[4] or "",
                "vectorized": bool(vector),
                "storage_type": f"VECTOR({DB_EMBED_DIMENSION}, FLOAT32)",
                "dimension": len(vector),
                "provider": session_row[8] or DB_EMBED_PROVIDER,
                "model": session_row[9] or DB_EMBED_MODEL,
                "region": session_row[10] or DB_EMBED_REGION,
                "operation": "DBMS_VECTOR_CHAIN.UTL_TO_EMBEDDING",
                "embedded_at": (
                    session_row[11].astimezone(timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z")
                    if session_row[11]
                    else None
                ),
                "values": [round(float(value), 7) for value in vector],
            },
        }

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close(force=True)
            self._pool = None


def _validated_session_ids(session_ids: list[str]) -> list[str]:
    unique: list[str] = []
    for session_id in session_ids:
        if not 7 <= len(session_id) <= 64 or not all(
            character.isalnum() or character in "_-" for character in session_id
        ):
            raise ValueError("invalid session id")
        if session_id not in unique:
            unique.append(session_id)
    if not unique:
        raise ValueError("at least one session id is required")
    return unique


def _participant_record(
    session: dict[str, Any], message_count: int = 0
) -> dict[str, Any]:
    created_at = session.get("created_at")
    if isinstance(created_at, datetime):
        created_at = created_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    consent_value = session.get("public_consent", session.get("consent", 0))
    ranking_value = session.get("ranking_consent", 0)
    seed_value = session.get("is_seed", 0)
    public_consent = str(consent_value).lower() not in {"", "0", "false", "none"}
    ranking_consent = str(ranking_value).lower() not in {"", "0", "false", "none"}
    is_seed = str(seed_value).lower() not in {"", "0", "false", "none"}
    persona_name = session.get("persona_name") or None
    return {
        "session_id": session["session_id"],
        "nickname": session["nickname"],
        "persona_name": persona_name,
        "answer": session.get("answer") or session.get("answer_text") or "",
        "public_consent": public_consent,
        "ranking_consent": ranking_consent,
        "is_seed": is_seed,
        "created_at": str(created_at or ""),
        "completed": bool(persona_name),
        "message_count": int(message_count),
    }


def _text_value(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "read"):
        return str(value.read())
    return str(value)


def _json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    try:
        parsed = json.loads(_text_value(value) or "[]")
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _message_record(message: dict[str, Any]) -> dict[str, Any]:
    created_at = message.get("created_at")
    if isinstance(created_at, datetime):
        created_at = (
            created_at.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
    return {
        "role": message.get("role") or message.get("role_name") or "",
        "content": _text_value(
            message.get("content", message.get("content_text", ""))
        ),
        "source_labels": _json_list(message.get("source_labels", [])),
        "latency_ms": message.get("latency_ms"),
        "created_at": str(created_at or ""),
    }


def _fallback_business_context(message: str) -> tuple[str, list[str]]:
    if any(word in message for word in ("売上", "解約", "MRR")):
        return (
            "今月の売上は1.28億円（前月比+8.4%）、解約率は2.1%（前月比-0.4pt）、"
            "MRRは9,640万円です。",
            ["MIO_DEMO_BUSINESS_METRICS"],
        )
    if "A社" in message or "顧客" in message:
        return (
            "A社のヘルススコアは74、利用率は前月比+18%、未解決チケットは2件、"
            "契約更新まで46日です。",
            ["MIO_DEMO_CUSTOMERS"],
        )
    if any(word in message for word in ("スケジュール", "予定", "商談")):
        return (
            "本日は10:00プロダクト定例、13:30 A社商談、16:00パートナー会議です。"
            "13:30の商談資料は準備済みです。",
            ["MIO_DEMO_SCHEDULE"],
        )
    if any(word in message for word in ("新幹線", "遅延", "移動")):
        return (
            "到着が25分遅れる想定です。A社商談を14:00へ変更し、先に資料を共有する案なら"
            "後続予定への影響を最小化できます。",
            ["MIO_DEMO_SCHEDULE", "MIO_DEMO_TRAVEL"],
        )
    return (
        "優先順位を「今日決めること」「誰かに頼めること」「今週でよいこと」に分けましょう。"
        "まず一番気になっていることを一つ教えてください。",
        ["MIO_DEMO_ASSISTANT_GUIDE"],
    )


def _match_reason(answer: str) -> str:
    if any(word in answer for word in ("任せ", "自律", "裁量", "見守")):
        return "信頼して任せるマネジメントを大切にする点が近いです"
    if any(word in answer for word in ("相談", "対話", "話", "聞", "チーム")):
        return "対話しながら一緒に考える姿勢が近いです"
    if any(word in answer for word in ("挑戦", "成長", "学び", "フィードバック")):
        return "挑戦と成長を後押しする価値観が近いです"
    if any(word in answer for word in ("目標", "判断", "優先", "決断", "成果")):
        return "目標と優先順位を明確にする点が近いです"
    if any(word in answer for word in ("安心", "失敗", "守", "公平", "尊重")):
        return "安心して働ける関係を重視する点が近いです"
    return "理想の上司に求める価値観が近いです"


def _mds_3d_positions(
    distance_matrix: list[list[float]],
) -> tuple[list[list[float]], float | None]:
    """Project a precomputed distance matrix to stable 3D MDS coordinates."""

    sample_count = len(distance_matrix)
    if sample_count == 1:
        return [[0.0, 0.0, 0.0]], 0.0
    if all(
        abs(float(distance_matrix[left][right])) <= 1e-12
        for left in range(sample_count)
        for right in range(left + 1, sample_count)
    ):
        # A matrix made entirely of identical answers has a valid zero-stress
        # solution at one point. Skip sklearn's divide-by-zero iterations; the
        # display-only duplicate offset is applied immediately afterwards.
        return [[0.0, 0.0, 0.0] for _ in range(sample_count)], 0.0
    try:
        import numpy as np
        from sklearn.manifold import MDS

        matrix = np.asarray(distance_matrix, dtype=float)
        model = MDS(
            n_components=3,
            metric=True,
            dissimilarity="precomputed",
            random_state=42,
            n_init=4,
            max_iter=300,
            eps=1e-6,
            normalized_stress="auto",
        )
        coordinates = model.fit_transform(matrix)
        coordinates -= coordinates.mean(axis=0, keepdims=True)
        max_abs = float(np.max(np.abs(coordinates))) or 1.0
        coordinates *= 90.0 / max_abs
        return coordinates.tolist(), float(model.stress_)
    except Exception as exc:
        LOGGER.warning("3D MDS fallback used: %s", type(exc).__name__)
        fallback = []
        for index in range(sample_count):
            angle = (index / sample_count) * 6.283185307179586
            fallback.append(
                [
                    70.0 * __import__("math").cos(angle),
                    70.0 * __import__("math").sin(angle),
                    ((index % 3) - 1) * 28.0,
                ]
            )
        return fallback, None


def _separate_exact_duplicate_positions(
    positions: list[list[float]],
    pair_distances: dict[tuple[int, int], float],
    session_ids: list[str],
    threshold: float = 1e-7,
) -> tuple[list[list[float]], int]:
    """Visually separate identical vectors without changing cosine distances.

    MDS correctly places zero-distance answers at the same point.  That is
    mathematically faithful but makes participant icons impossible to click.
    Exact-duplicate groups therefore receive a small, deterministic display
    offset around their shared centroid.  The distance matrix, edge values,
    similarity percentages, and nearest-neighbor selection remain untouched.
    """

    count = len(positions)
    if count < 2:
        return positions, 0

    parents = list(range(count))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    for (left, right), distance in pair_distances.items():
        if float(distance) <= threshold:
            union(left, right)

    groups: dict[int, list[int]] = {}
    for index in range(count):
        groups.setdefault(find(index), []).append(index)
    duplicate_groups = [members for members in groups.values() if len(members) > 1]
    if not duplicate_groups:
        return positions, 0

    import math

    separated = [list(position) for position in positions]
    for members in duplicate_groups:
        members = sorted(members, key=lambda index: session_ids[index])
        centroid = [
            sum(positions[index][axis] for index in members) / len(members)
            for axis in range(3)
        ]
        phase_seed = sum(ord(char) for index in members for char in session_ids[index])
        phase = math.radians(phase_seed % 360)
        radius = 7.5 + min(3.0, max(0, len(members) - 2) * 0.45)
        for order, index in enumerate(members):
            angle = phase + (2.0 * math.pi * order / len(members))
            z_offset = ((order % 3) - 1) * min(2.5, radius * 0.28)
            separated[index] = [
                centroid[0] + radius * math.cos(angle),
                centroid[1] + radius * math.sin(angle),
                centroid[2] + z_offset,
            ]
    return separated, len(duplicate_groups)


def _build_network_graph(
    sessions: list[dict[str, Any]],
    oracle_distances: dict[tuple[str, str], float] | None = None,
    distance_source: str = "application cosine fallback",
) -> dict[str, Any]:
    """Build a 3D MDS graph from cosine distances and nearest-neighbor links."""

    public_sessions = []
    for session in sessions:
        is_public = bool(
            session.get("public_consent", session.get("consent", 0))
        )
        answer = session.get("answer") or session.get("answer_text")
        if not is_public or not answer or not session.get("persona_name"):
            continue
        vector = session.get("vector") or demo_embedding(str(answer))
        public_sessions.append({**session, "answer": str(answer), "vector": vector})

    if not public_sessions:
        return {"nodes": [], "edges": [], "updated_at": datetime.now(timezone.utc).isoformat()}

    persona_lookup = {persona.name: persona for persona in PERSONAS}
    pair_cosines: dict[tuple[int, int], float] = {}
    pair_distances: dict[tuple[int, int], float] = {}
    distance_matrix = [
        [0.0 for _ in public_sessions] for _ in public_sessions
    ]
    for left in range(len(public_sessions)):
        for right in range(left + 1, len(public_sessions)):
            left_id = str(public_sessions[left]["session_id"])
            right_id = str(public_sessions[right]["session_id"])
            oracle_key = tuple(sorted((left_id, right_id)))
            if oracle_distances is not None and oracle_key in oracle_distances:
                distance = float(oracle_distances[oracle_key])
            else:
                similarity = cosine_similarity(
                    public_sessions[left]["vector"], public_sessions[right]["vector"]
                )
                distance = 1.0 - max(-1.0, min(1.0, similarity))
            distance = max(0.0, min(2.0, distance))
            similarity = 1.0 - distance
            pair_distances[(left, right)] = distance
            pair_cosines[(left, right)] = similarity
            distance_matrix[left][right] = distance
            distance_matrix[right][left] = distance

    positions, mds_stress = _mds_3d_positions(distance_matrix)
    positions, exact_duplicate_groups = _separate_exact_duplicate_positions(
        positions,
        pair_distances,
        [str(session["session_id"]) for session in public_sessions],
    )

    # Keep the display readable: choose the globally closest pairs while
    # limiting every participant to at most three visible connections.
    ranked_pairs = sorted(pair_distances, key=pair_distances.get)
    edge_keys: set[tuple[int, int]] = set()
    degrees = [0 for _ in public_sessions]
    for left, right in ranked_pairs:
        if degrees[left] >= 3 or degrees[right] >= 3:
            continue
        edge_keys.add((left, right))
        degrees[left] += 1
        degrees[right] += 1

    minimum_degree = min(2, max(0, len(public_sessions) - 1))
    for index in range(len(public_sessions)):
        if degrees[index] >= minimum_degree:
            continue
        candidates = sorted(
            (
                pair for pair in ranked_pairs
                if index in pair and pair not in edge_keys
            ),
            key=pair_distances.get,
        )
        for left, right in candidates:
            other = right if left == index else left
            if degrees[index] >= minimum_degree:
                break
            if degrees[index] >= 3 or degrees[other] >= 3:
                continue
            edge_keys.add((left, right))
            degrees[left] += 1
            degrees[right] += 1

    nodes = []
    for index, session in enumerate(public_sessions):
        persona = persona_lookup.get(session["persona_name"])
        nodes.append(
            {
                "id": session["session_id"],
                "nickname": session["nickname"],
                "persona_name": session["persona_name"],
                "icon": persona.icon if persona else "✦",
                "color": persona.color if persona else "#f4b653",
                "persona_tagline": persona.tagline if persona else "価値観を言葉にする人",
                "persona_description": persona.description if persona else "自由回答から見つかった価値観タイプです。",
                "x": round(50.0 + positions[index][0] * 0.42, 2),
                "y": round(50.0 + positions[index][1] * 0.42, 2),
                "x3d": round(positions[index][0], 5),
                "y3d": round(positions[index][1], 5),
                "z3d": round(positions[index][2], 5),
            }
        )

    edges = []
    for left, right in sorted(edge_keys):
        raw = pair_cosines[(left, right)]
        distance = pair_distances[(left, right)]
        edges.append(
            {
                "source": public_sessions[left]["session_id"],
                "target": public_sessions[right]["session_id"],
                "similarity": _cosine_score(raw),
                "distance": distance,
                "distance_metric": "COSINE",
            }
        )

    return {
        "nodes": nodes,
        "edges": edges,
        "layout": {
            "method": "metric MDS",
            "dimensions": 3,
            "distance_source": distance_source,
            "distance_metric": "COSINE",
            "neighbors_per_node": 3,
            "stress": mds_stress,
            "approximate": True,
            "exact_duplicate_visual_offset": True,
            "exact_duplicate_groups": exact_duplicate_groups,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def build_repository(settings: Settings) -> tuple[Repository, str | None]:
    if not settings.adb_requested:
        return MemoryRepository(), None
    try:
        return AdbRepository(settings), None
    except Exception as exc:
        if settings.data_mode == "adb":
            raise
        return MemoryRepository(), f"{type(exc).__name__}: ADB unavailable; using demo memory mode"
