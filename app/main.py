from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .ai_service import AiService
from .config import ROOT, settings
from .database import MemoryRepository, Repository, build_repository
from .models import (
    AdminDeleteRequest,
    ChatRequest,
    MetricEvent,
    SessionCreate,
    SurveyRequest,
    RescueSessionCreate,
    RescueTurnRequest,
)
from .personas import PERSONAS, classify_persona, extract_keywords
from .rescue_service import (
    RescueConflict,
    RescueNotFound,
    RescueNotReady,
    build_rescue_service,
)


LOGGER = logging.getLogger("mio-demo")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


class AppState:
    repository: Repository = MemoryRepository()
    repository_warning: str | None = None
    ai: AiService = AiService(settings)
    rescue: Any = build_rescue_service(repository)


state = AppState()


@asynccontextmanager
async def lifespan(_: FastAPI):
    state.repository, state.repository_warning = build_repository(settings)
    state.ai = AiService(settings)
    state.rescue = build_rescue_service(state.repository)
    LOGGER.info(
        "Mio demo ready: data=%s ai=%s port=%s",
        state.repository.mode,
        state.ai.mode,
        settings.port,
    )
    async def cleanup_expired_participants() -> None:
        while True:
            await asyncio.sleep(3600)
            cleanup = getattr(state.repository, "cleanup_expired", None)
            if callable(cleanup):
                try:
                    await asyncio.to_thread(cleanup)
                except Exception:
                    LOGGER.exception("scheduled participant cleanup failed")

    cleanup_task = asyncio.create_task(cleanup_expired_participants())
    try:
        yield
    finally:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        close = getattr(state.repository, "close", None)
        if callable(close):
            close()


app = FastAPI(
    title="みおちゃん Oracle AI Demo",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url=None,
    lifespan=lifespan,
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), geolocation=()"
    response.headers["Cache-Control"] = (
        "no-store" if request.url.path.startswith("/api/") else "no-cache"
    )
    return response


static_dir = ROOT / "static"
asset_dir = ROOT / "assets"
app.mount("/static", StaticFiles(directory=static_dir), name="static")
app.mount("/assets", StaticFiles(directory=asset_dir), name="assets")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/display", include_in_schema=False)
def display() -> FileResponse:
    return FileResponse(static_dir / "display.html")


@app.get("/why-oracle", include_in_schema=False)
def why_oracle() -> FileResponse:
    return FileResponse(static_dir / "why-oracle.html")


@app.get("/admin", include_in_schema=False)
def admin() -> FileResponse:
    return FileResponse(static_dir / "admin.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "mio-demo",
        "port": settings.port,
        "data_mode": state.repository.mode,
        "database_driver": getattr(state.repository, "driver", "unknown"),
        "ai_mode": state.ai.mode,
        "embedding_mode": getattr(
            state.repository, "embedding_mode", "application-fallback"
        ),
        "embedding_provider": getattr(
            state.repository, "embedding_provider", "application"
        ),
        "embedding_model": getattr(
            state.repository, "embedding_model", settings.oci_embed_model_id
        ),
        "embedding_region": getattr(
            state.repository, "embedding_region", settings.oci_region
        ),
        "embedding_dimension": getattr(
            state.repository, "embedding_dimension", 1024
        ),
        "rescue_mode": getattr(state.rescue, "mode", "unknown"),
        "rescue_scoring_mode": "deferred-db-embedding",
        "rescue_chat_model": "google.gemini-2.5-flash",
        "warning": state.repository_warning or state.ai.last_error,
        "gif_source_ready": all(
            (ROOT / "assets" / "miochan" / filename).exists()
            for filename in (
                "waving.gif",
                "idle.gif",
                "waiting.gif",
                "review.gif",
                "running.gif",
                "jumping.gif",
                "failed.gif",
                "generated-v1/anxious.gif",
                "generated-v1/overwhelmed.gif",
                "generated-v1/thinking.gif",
                "generated-v1/relieved.gif",
                "generated-v1/presentation.gif",
                "generated-v1/time-pressure.gif",
                "generated-v1/idea.gif",
                "generated-v1/celebrate.gif",
                "generated-v1/listening.gif",
                "generated-v1/retry.gif",
            )
        ),
    }


@app.post("/api/mio/sessions")
def rescue_create_session(payload: RescueSessionCreate) -> dict[str, Any]:
    try:
        result = state.rescue.start(
            payload.nickname,
            payload.consent,
            payload.public_consent,
            session_id=payload.session_id,
            ranking_consent=payload.ranking_consent,
        )
        state.repository.record_metric(
            "rescue_started", result["session_id"], None, True
        )
        return {**result, "data_mode": state.repository.mode}
    except RescueConflict as exc:
        if str(exc) == "consent_required":
            raise HTTPException(status_code=422, detail="ゲーム保存への同意が必要です") from exc
        raise HTTPException(status_code=409, detail="このセッションではゲームを開始できません") from exc
    except Exception as exc:
        LOGGER.exception("rescue session creation failed")
        raise HTTPException(status_code=503, detail="レスキューを開始できませんでした") from exc


@app.get("/api/mio/sessions/{session_id}")
def rescue_session_state(session_id: str) -> dict[str, Any]:
    try:
        return state.rescue.state(session_id)
    except RescueNotFound as exc:
        raise HTTPException(status_code=404, detail="ゲームが見つかりません") from exc


@app.post("/api/mio/sessions/{session_id}/turns")
def rescue_turn(
    session_id: str,
    payload: RescueTurnRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    try:
        result = state.rescue.submit_turn(
            session_id,
            payload.turn_no,
            payload.answer_type,
            payload.user_answer,
        )
        processor = getattr(state.rescue, "process_pending_turn", None)
        if result.get("accepted") and result.get("scoring_pending") and callable(processor):
            background_tasks.add_task(processor, session_id, payload.turn_no)
        return result
    except RescueNotFound as exc:
        raise HTTPException(status_code=404, detail="ゲームが見つかりません") from exc
    except RescueConflict as exc:
        raise HTTPException(status_code=409, detail="このターンはすでに回答済みです") from exc
    except Exception as exc:
        LOGGER.exception("rescue turn failed")
        raise HTTPException(status_code=503, detail="回答を採点できませんでした") from exc


@app.post("/api/mio/sessions/{session_id}/finish")
def rescue_finish(session_id: str) -> dict[str, Any]:
    try:
        return state.rescue.finish(session_id)
    except RescueNotFound as exc:
        raise HTTPException(status_code=404, detail="ゲームが見つかりません") from exc
    except RescueNotReady as exc:
        raise HTTPException(status_code=409, detail="ゲームはまだ進行中です") from exc


@app.get("/api/mio/sessions/{session_id}/result")
def rescue_result(session_id: str) -> dict[str, Any]:
    try:
        return state.rescue.result(session_id)
    except RescueNotFound as exc:
        raise HTTPException(status_code=404, detail="ゲームが見つかりません") from exc
    except RescueNotReady as exc:
        raise HTTPException(status_code=409, detail="ゲームはまだ進行中です") from exc


@app.get("/api/mio/venue/scoreboard")
def rescue_scoreboard() -> dict[str, Any]:
    try:
        return {**state.rescue.scoreboard(), "data_mode": state.repository.mode}
    except Exception as exc:
        LOGGER.exception("rescue scoreboard failed")
        raise HTTPException(status_code=503, detail="ランキングを取得できませんでした") from exc


@app.post("/api/sessions")
def create_session(payload: SessionCreate) -> dict[str, Any]:
    try:
        result = state.repository.create_session(
            payload.nickname, payload.public_consent, payload.ranking_consent
        )
        state.repository.record_metric("session_started", result["session_id"], None, True)
        return {**result, "data_mode": state.repository.mode}
    except Exception as exc:
        LOGGER.exception("session creation failed")
        raise HTTPException(status_code=503, detail="セッションを開始できませんでした") from exc


@app.post("/api/chat")
def chat(payload: ChatRequest) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        context, sources = state.repository.business_context(payload.message)
        answer = state.ai.answer(payload.message, context)
        initial_elapsed_ms = int((time.perf_counter() - started) * 1000)
        exchange = getattr(state.repository, "chat_exchange", None)
        if callable(exchange):
            exchange(
                payload.session_id,
                payload.message,
                answer,
                sources,
                initial_elapsed_ms,
            )
        else:
            state.repository.add_message(payload.session_id, "user", payload.message)
            state.repository.add_message(
                payload.session_id,
                "assistant",
                answer,
                source_labels=sources,
                latency_ms=initial_elapsed_ms,
            )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        state.repository.record_metric(
            "chat_completed", payload.session_id, elapsed_ms, True
        )
        return {
            "answer": answer,
            "sources": sources,
            "latency_ms": elapsed_ms,
            "ai_mode": state.ai.mode,
            "steps": [
                {"label": "質問を理解", "service": "OCI Generative AI", "status": "done"},
                {"label": "業務データを参照", "service": "Oracle Database", "status": "done"},
                {"label": "回答を整理", "service": "AI Assistant", "status": "done"},
            ],
        }
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="セッションが見つかりません") from exc
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        LOGGER.exception("chat failed")
        try:
            state.repository.record_metric(
                "chat_failed", payload.session_id, elapsed_ms, False
            )
        except Exception:
            pass
        raise HTTPException(status_code=503, detail="みおちゃんが応答できませんでした") from exc


@app.post("/api/survey")
def survey(payload: SurveyRequest) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        persona, confidence = classify_persona(payload.answer)
        db_embedding = getattr(
            state.repository, "save_survey_with_db_embedding", None
        )
        if callable(db_embedding):
            matches = db_embedding(
                payload.session_id,
                payload.answer,
                persona.name,
                limit=3,
            )
            embedding_mode = getattr(
                state.repository,
                "embedding_mode",
                "dbms_vector_chain/ocigenai",
            )
        else:
            vector, embedding_mode = state.ai.embed(payload.answer)
            combined = getattr(state.repository, "save_survey_and_find", None)
            if callable(combined):
                matches = combined(
                    payload.session_id,
                    payload.answer,
                    vector,
                    persona.name,
                    int((time.perf_counter() - started) * 1000),
                    limit=3,
                )
            else:
                state.repository.save_survey(
                    payload.session_id, payload.answer, vector, persona.name
                )
                matches = state.repository.find_matches(
                    payload.session_id, vector, limit=3
                )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        state.repository.record_metric(
            "survey_completed", payload.session_id, elapsed_ms, True
        )
        return {
            "persona": {
                "name": persona.name,
                "icon": persona.icon,
                "tagline": persona.tagline,
                "description": persona.description,
                "color": persona.color,
                "confidence": round(confidence, 3),
            },
            "keywords": extract_keywords(payload.answer),
            "matches": matches,
            "embedding_mode": embedding_mode,
            "data_mode": state.repository.mode,
            "latency_ms": elapsed_ms,
            "steps": [
                {"label": "DB内で1536次元へ変換", "service": "DBMS_VECTOR_CHAIN + OCI GenAI", "status": "done"},
                {"label": "VECTOR(1536)へ保存", "service": "Oracle AI Database", "status": "done"},
                {"label": "近い参加者を検索", "service": "AI Vector Search", "status": "done"},
            ],
        }
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="セッションが見つかりません") from exc
    except Exception as exc:
        LOGGER.exception("survey failed")
        raise HTTPException(status_code=503, detail="診断を完了できませんでした") from exc


@app.get("/api/stats")
def stats() -> dict[str, Any]:
    result = state.repository.stats()
    result["data_mode"] = state.repository.mode
    result["personas"] = [
        {"name": item.name, "icon": item.icon, "color": item.color}
        for item in PERSONAS
    ]
    return result


@app.get("/api/network")
def network() -> dict[str, Any]:
    graph = state.repository.network_graph()
    graph["data_mode"] = state.repository.mode
    return graph


@app.get("/api/network/{session_id}")
def network_participant_detail(session_id: str) -> dict[str, Any]:
    try:
        detail = state.repository.get_participant_detail(session_id)
        participant = detail["participant"]
        embedding = detail["office_preference"]
        if not participant.get("public_consent") or not embedding.get("vectorized"):
            raise KeyError("not_public")
        persona = next(
            (item for item in PERSONAS if item.name == participant.get("persona_name")),
            None,
        )
        return {
            "session_id": session_id,
            "nickname": participant["nickname"],
            "persona": {
                "name": persona.name if persona else participant.get("persona_name"),
                "icon": persona.icon if persona else "✦",
                "tagline": persona.tagline if persona else "価値観を言葉にする人",
                "description": persona.description if persona else "自由回答から見つかった価値観タイプです。",
                "color": persona.color if persona else "#c74634",
            },
            "embedding": {
                "dimension": embedding.get("dimension", 0),
                "storage_type": embedding.get("storage_type", "VECTOR"),
                "model": embedding.get("model", "cohere.embed-v4.0"),
                "region": embedding.get("region", "us-chicago-1"),
                "operation": embedding.get("operation", "DBMS_VECTOR_CHAIN.UTL_TO_EMBEDDING"),
                "values": embedding.get("values", []),
            },
        }
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="公開参加者が見つかりません") from exc
    except Exception as exc:
        LOGGER.exception("network participant detail failed")
        raise HTTPException(status_code=503, detail="ベクトル詳細を取得できませんでした") from exc


@app.get("/api/admin/participants")
def admin_participants() -> dict[str, Any]:
    try:
        participants = state.repository.list_participants()
        return {
            "participants": participants,
            "data_mode": state.repository.mode,
            "total": len(participants),
        }
    except Exception as exc:
        LOGGER.exception("admin participant listing failed")
        raise HTTPException(
            status_code=503, detail="参加者一覧を取得できませんでした"
        ) from exc


@app.get("/api/admin/participants/{session_id}")
def admin_participant_detail(session_id: str) -> dict[str, Any]:
    try:
        detail = state.repository.get_participant_detail(session_id)
        return {
            **detail,
            "rescue": state.rescue.detail(session_id),
            "data_mode": state.repository.mode,
        }
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="参加者が見つかりません") from exc
    except Exception as exc:
        LOGGER.exception("admin participant detail failed")
        raise HTTPException(
            status_code=503, detail="参加者の詳細を取得できませんでした"
        ) from exc


@app.delete("/api/admin/participants")
def admin_delete_participants(payload: AdminDeleteRequest) -> dict[str, Any]:
    try:
        result = state.repository.delete_participants(payload.session_ids)
        return {**result, "data_mode": state.repository.mode}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="削除対象が正しくありません") from exc
    except Exception as exc:
        LOGGER.exception("admin participant deletion failed")
        raise HTTPException(
            status_code=503, detail="参加者を削除できませんでした"
        ) from exc


@app.post("/api/metrics", status_code=204)
def metric(payload: MetricEvent) -> JSONResponse:
    state.repository.record_metric(
        payload.event_name,
        payload.session_id,
        payload.duration_ms,
        payload.success,
    )
    return JSONResponse(status_code=204, content=None)
