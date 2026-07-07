from __future__ import annotations

from dataclasses import dataclass

from .embedding import cosine_similarity, demo_embedding


@dataclass(frozen=True)
class Persona:
    name: str
    icon: str
    tagline: str
    description: str
    prototype: str
    color: str


PERSONAS: tuple[Persona, ...] = (
    Persona(
        "フクロウタイプ",
        "🦉",
        "考える時間を尊重してくれる人",
        "細かく管理せず、背景を共有したうえで自分のペースと裁量を任せてくれる上司を好みます。",
        "目的と背景を説明し、考える時間を尊重して、細かく口を出さず任せてくれる上司。",
        "#7766d7",
    ),
    Persona(
        "イルカタイプ",
        "🐬",
        "人とチームをしなやかにつなぐ人",
        "部署や立場を越えて必要な人をつなぎ、柔軟に協力を引き出してくれる上司を好みます。",
        "部署を越えて人をつなぎ、困ったときに必要な協力を柔軟に集めてくれる上司。",
        "#19a7a0",
    ),
    Persona(
        "小鳥タイプ",
        "🐦",
        "対話でチームを前へ運ぶ人",
        "意見をよく聞き、相談しながらチームで答えをつくる上司との関係を大切にします。",
        "話をよく聞き、チームみんなで相談しながら納得できる答えをつくる上司。",
        "#f3a529",
    ),
    Persona(
        "猫タイプ",
        "🐈",
        "信頼と余白をつくってくれる人",
        "生活や体調にも配慮し、必要なときは支えながら普段は自由に任せてくれる上司を好みます。",
        "働き方の柔軟性を認め、無理をさせず、信頼して見守ってくれる上司。",
        "#ec6f75",
    ),
    Persona(
        "鷹タイプ",
        "🦅",
        "明確な判断で成果へ導く人",
        "目標と優先順位をはっきり示し、迷う場面では素早く決断してくれる上司を好みます。",
        "目標、役割、優先順位を明確にし、必要なときはすぐ決断してくれる上司。",
        "#335c91",
    ),
    Persona(
        "森の探検家タイプ",
        "🌿",
        "挑戦から可能性をひらく人",
        "失敗を責めず、新しい挑戦と学びを後押しして成長の機会をつくる上司を好みます。",
        "失敗から学べる安心感をつくり、新しい挑戦と成長を応援してくれる上司。",
        "#4f9d69",
    ),
)


def classify_persona(answer: str) -> tuple[Persona, float]:
    answer_vector = demo_embedding(answer)
    ranked = sorted(
        (
            (persona, cosine_similarity(answer_vector, demo_embedding(persona.prototype)))
            for persona in PERSONAS
        ),
        key=lambda item: item[1],
        reverse=True,
    )
    persona, raw_score = ranked[0]
    confidence = max(0.58, min(0.94, 0.68 + raw_score * 0.9))
    return persona, confidence


def extract_keywords(answer: str) -> list[str]:
    keyword_groups = (
        ("信頼", ("信頼", "任せ", "見守", "裁量")),
        ("対話", ("対話", "相談", "話", "聞", "チーム")),
        ("安心", ("安心", "尊重", "公平", "守", "無理")),
        ("明確さ", ("明確", "目標", "役割", "優先", "決断")),
        ("柔軟性", ("自由", "柔軟", "事情", "働き方")),
        ("成長", ("成長", "学び", "挑戦", "フィードバック")),
        ("支援", ("支え", "助け", "フォロー", "協力")),
    )
    found = [label for label, words in keyword_groups if any(word in answer for word in words)]
    return (found + ["信頼関係", "働きやすさ", "成長支援"])[:3]


SEED_PARTICIPANTS = (
    ("集中のユウ", "目的を伝えたら、考える時間と裁量を尊重して任せてくれる上司。", "フクロウタイプ"),
    ("つなぐミナ", "部署を越えて必要な人をつなぎ、協力を引き出してくれる上司。", "イルカタイプ"),
    ("共創のソラ", "話をよく聞き、チームみんなで相談して答えをつくる上司。", "小鳥タイプ"),
    ("余白のリン", "働き方の事情を尊重し、信頼して柔軟に見守ってくれる上司。", "猫タイプ"),
    ("効率のカイ", "目標と優先順位を明確にし、必要なときはすぐ決断する上司。", "鷹タイプ"),
    ("緑のハル", "失敗を責めず、新しい挑戦と成長を応援してくれる上司。", "森の探検家タイプ"),
)
