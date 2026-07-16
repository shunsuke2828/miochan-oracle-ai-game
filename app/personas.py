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
        "クマタイプ",
        "🐻",
        "挑戦から可能性をひらく人",
        "失敗を責めず、新しい挑戦と学びを後押しして成長の機会をつくる上司を好みます。",
        "失敗から学べる安心感をつくり、新しい挑戦と成長を応援してくれる上司。",
        "#4f9d69",
    ),
)


PERSONA_SIGNALS: dict[str, tuple[str, ...]] = {
    "フクロウタイプ": (
        "裁量", "自分のペース", "細かく口", "口を出さ", "考える時間",
        "任せ", "急かさ", "背景を共有",
    ),
    "イルカタイプ": (
        "つな", "連携", "協力", "橋渡し", "部署を越", "立場を越",
        "必要な人", "専門家", "巻き込",
    ),
    "小鳥タイプ": (
        "対話", "意見", "話を聞", "相談しながら", "チーム全員", "みんな",
        "公平", "称え", "一緒に考",
    ),
    "猫タイプ": (
        "柔軟", "生活", "体調", "リモート", "休", "無理", "安心",
        "見守", "働き方", "家庭",
    ),
    "鷹タイプ": (
        "目標", "優先順位", "決断", "判断", "役割", "明確", "期限",
        "次にやる", "方針", "責任",
    ),
    "クマタイプ": (
        "挑戦", "成長", "学び", "キャリア", "強み", "フィードバック",
        "失敗", "応援", "育て", "機会", "改善",
    ),
}


def _classification_score(answer: str, persona: Persona) -> float:
    semantic_score = cosine_similarity(
        demo_embedding(answer), demo_embedding(persona.prototype)
    )
    signal_hits = sum(
        1 for signal in PERSONA_SIGNALS[persona.name] if signal in answer
    )
    # Explicit values in a short answer should outweigh incidental feature-hash
    # similarity, while the cap keeps free-form answers semantically comparable.
    return semantic_score + min(0.48, signal_hits * 0.12)


def classify_persona(answer: str) -> tuple[Persona, float]:
    ranked = sorted(
        ((persona, _classification_score(answer, persona)) for persona in PERSONAS),
        key=lambda item: item[1],
        reverse=True,
    )
    persona, raw_score = ranked[0]
    runner_up_score = ranked[1][1]
    margin = max(0.0, raw_score - runner_up_score)
    confidence = max(0.58, min(0.94, 0.62 + margin * 1.4))
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


# Production-approved demo participants.  The stable session IDs intentionally
# point at real, already-completed demo sessions so a restart never recreates
# the former fictional participants.
SEED_PARTICIPANTS = (
    ("e4d4ddfcee3e4e76b2cf953fa5885abc", "araidon", "給料をあげてくれる", "フクロウタイプ"),
    ("23b5ec1f4e0846f79a375fd4a8553d28", "にわ", "一人ひとりのキャリアや将来について考えてくれる上司", "クマタイプ"),
    ("e8edc7a0fdc24e14942b4637ff3c085d", "うだがわ", "良いとこ見つけてテンション上げてくれる", "クマタイプ"),
    ("34232b78a58b43ea9fdd5e50d038e5ac", "Mariko", "格好いい上司", "鷹タイプ"),
    ("724e27a2125441f3a94fd8ebf6a503ac", "イトウヒロキ", "困ったときに相談しやすく、最後まで話を聞いてくれる上司", "イルカタイプ"),
    ("bf11126ccba24caebbba0f1541689f7e", "yamadas", "給料を上げてくれる上司", "フクロウタイプ"),
    ("2962ac9f80eb48788a41bcf931238596", "rieko", "忙しいときほど落ち着いて、状況を整理してくれる上司", "クマタイプ"),
)
