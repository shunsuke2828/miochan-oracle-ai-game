from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator


PRIVATE_NICKNAME_PATTERN = re.compile(
    r"(?:[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|\d{2,4}[-ー]\d{2,4}[-ー]\d{3,4})"
)


class SessionCreate(BaseModel):
    nickname: str = Field(min_length=1, max_length=40)
    public_consent: bool = False
    ranking_consent: bool = False

    @field_validator("nickname")
    @classmethod
    def clean_nickname(cls, value: str) -> str:
        cleaned = " ".join(value.strip().split())
        if not cleaned:
            raise ValueError("ニックネームを入力してください")
        return cleaned


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)
    message: str = Field(min_length=1, max_length=500)


class SurveyRequest(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)
    answer: str = Field(min_length=3, max_length=500)


class RescueSessionCreate(BaseModel):
    session_id: Optional[str] = Field(default=None, min_length=8, max_length=64)
    nickname: str = Field(min_length=2, max_length=16)
    consent: bool
    public_consent: bool = False
    ranking_consent: bool = False

    @field_validator("nickname")
    @classmethod
    def clean_rescue_nickname(cls, value: str) -> str:
        cleaned = " ".join(value.strip().split())
        if len(cleaned) < 2:
            raise ValueError("ニックネームは2文字以上で入力してください")
        if PRIVATE_NICKNAME_PATTERN.search(cleaned):
            raise ValueError("個人情報ではないニックネームを入力してください")
        return cleaned

    @field_validator("consent")
    @classmethod
    def require_consent(cls, value: bool) -> bool:
        if not value:
            raise ValueError("ゲーム採点・保存への同意が必要です")
        return value

    @field_validator("session_id")
    @classmethod
    def validate_rescue_session_id(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", value):
            raise ValueError("無効なセッションIDです")
        return value


class RescueTurnRequest(BaseModel):
    turn_no: int = Field(ge=1, le=100)
    answer_type: str = Field(pattern=r"^(choice|free_text)$")
    user_answer: str = Field(min_length=2, max_length=500)

    @field_validator("user_answer")
    @classmethod
    def clean_rescue_answer(cls, value: str) -> str:
        return value.strip()


class MetricEvent(BaseModel):
    session_id: Optional[str] = Field(default=None, max_length=64)
    event_name: str = Field(min_length=1, max_length=80)
    duration_ms: Optional[int] = Field(default=None, ge=0, le=300_000)
    success: bool = True


class AdminDeleteRequest(BaseModel):
    session_ids: list[str] = Field(min_length=1, max_length=100)

    @field_validator("session_ids")
    @classmethod
    def validate_session_ids(cls, values: list[str]) -> list[str]:
        unique: list[str] = []
        for value in values:
            if not re.fullmatch(r"[A-Za-z0-9_-]{7,64}", value):
                raise ValueError("無効なセッションIDです")
            if value not in unique:
                unique.append(value)
        return unique
