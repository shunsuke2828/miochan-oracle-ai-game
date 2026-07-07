from __future__ import annotations

import logging
from typing import Any

import oci
from oci.generative_ai_inference import GenerativeAiInferenceClient
from oci.generative_ai_inference import models as genai_models

from .config import Settings
from .embedding import EMBEDDING_DIMENSION, demo_embedding


LOGGER = logging.getLogger(__name__)


class AiService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: GenerativeAiInferenceClient | None = None
        self.last_error: str | None = None
        if settings.oci_ready:
            try:
                config = {
                    "user": settings.oci_user_ocid,
                    "tenancy": settings.oci_tenancy_ocid,
                    "fingerprint": settings.oci_fingerprint,
                    "key_file": settings.oci_private_key_file,
                    "region": settings.oci_region,
                }
                oci.config.validate_config(config)
                self._client = GenerativeAiInferenceClient(
                    config=config,
                    service_endpoint=(
                        "https://inference.generativeai."
                        f"{settings.oci_region}.oci.oraclecloud.com"
                    ),
                    timeout=(5, 25),
                )
            except Exception as exc:
                self.last_error = f"OCI init failed: {type(exc).__name__}"
                LOGGER.warning(self.last_error)

    @property
    def mode(self) -> str:
        return "oci-generative-ai" if self._client else "demo-fallback"

    def answer(self, user_message: str, business_context: str) -> str:
        if not self._client:
            return compose_demo_reply(user_message, business_context)
        prompt = f"""
あなたはSaaS企業の経営者を支えるAI秘書「みおちゃん」です。
明るく、簡潔で、次に取れる行動を一つ示してください。
提供された業務データ以外の数値を作らないでください。

業務データ:
{business_context}

ユーザーの質問:
{user_message}
""".strip()
        try:
            details = genai_models.ChatDetails(
                compartment_id=self.settings.oci_compartment_ocid,
                serving_mode=genai_models.OnDemandServingMode(
                    model_id=self.settings.oci_chat_model_id
                ),
                chat_request=genai_models.GenericChatRequest(
                    messages=[
                        genai_models.UserMessage(
                            content=[genai_models.TextContent(text=prompt)]
                        )
                    ],
                    max_tokens=420,
                    temperature=0.25,
                    top_p=0.85,
                ),
            )
            response = self._client.chat(details)
            content = response.data.chat_response.choices[0].message.content
            text = "".join(getattr(item, "text", "") for item in content).strip()
            if text:
                return text
        except Exception as exc:
            self.last_error = f"OCI chat failed: {type(exc).__name__}"
            LOGGER.warning(self.last_error)
        return compose_demo_reply(user_message, business_context)

    def embed(self, text: str) -> tuple[list[float], str]:
        if not self._client:
            return demo_embedding(text), "demo-embedding"
        try:
            details = genai_models.EmbedTextDetails(
                inputs=[text],
                serving_mode=genai_models.OnDemandServingMode(
                    model_id=self.settings.oci_embed_model_id
                ),
                compartment_id=self.settings.oci_compartment_ocid,
                input_type="SEARCH_DOCUMENT",
                truncate="END",
                output_dimensions=EMBEDDING_DIMENSION,
            )
            response = self._client.embed_text(details)
            vector = [float(value) for value in response.data.embeddings[0]]
            if len(vector) == EMBEDDING_DIMENSION:
                return vector, "oci-generative-ai-embedding"
        except Exception as exc:
            self.last_error = f"OCI embedding failed: {type(exc).__name__}"
            LOGGER.warning(self.last_error)
        return demo_embedding(text), "demo-embedding-fallback"


def compose_demo_reply(user_message: str, business_context: str) -> str:
    if any(word in user_message for word in ("売上", "解約", "MRR")):
        return (
            f"確認しました。{business_context}\n\n"
            "売上は伸びていますが、解約率の改善が成長を後押ししています。"
            "次は、解約率が下がった顧客セグメントを確認しましょうか？"
        )
    if "A社" in user_message or "顧客" in user_message:
        return (
            f"A社の最新状況です。{business_context}\n\n"
            "利用は伸びていますが、更新前に未解決チケット2件を閉じるのが安心です。"
            "カスタマーサクセスとの15分レビューを提案します。"
        )
    if any(word in user_message for word in ("スケジュール", "予定")):
        return (
            f"今日の予定を確認しました。{business_context}\n\n"
            "A社商談の15分前に、ヘルススコアと未解決課題をまとめておきますね。"
        )
    if any(word in user_message for word in ("新幹線", "遅延", "移動")):
        return (
            f"大丈夫、影響を整理しました。{business_context}\n\n"
            "MVPでは実際の予定変更は行わないので、この調整案を確認してから実行してください。"
        )
    return (
        f"話してくれてありがとうございます。{business_context}\n\n"
        "全部を一度に解決しなくて大丈夫です。まず、今日中に決めたいことを一つ選びましょう。"
    )

