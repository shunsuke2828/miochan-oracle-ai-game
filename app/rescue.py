from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from typing import Any


TIME_LIMIT_SEC = 60
EMBEDDING_MODEL = "cohere.embed-v4.0"
SELECT_AI_PROFILE = "MIO_GEMINI_FLASH"


QUIZ_ROWS: list[tuple[str, str, list[tuple[int, str]]]] = [
    ("quiz_01", "ドキドキして、うまく話せるか不安になってきたの……", [
        (5, "不安になるのは自然だよ。最初に結論、次に理由、最後にお願いを伝えれば十分だよ。"),
        (4, "緊張しても大丈夫だよ。伝えたいことを三つに絞って、ゆっくり話してみよう。"),
        (3, "そんなに心配しなくても大丈夫だよ。いつも通り話せば、問題ないと思うよ。"),
        (2, "緊張するのはわかるけど、本番ではちゃんと話してね。準備しておけば大丈夫だよ。"),
        (-1, "そのくらいで不安になるなら困るよ。人前で話すのも仕事のうちだからね。"),
    ]),
    ("quiz_02", "私の説明、ちゃんと伝わってるのか心配になっちゃって……", [
        (5, "心配なら確認しよう。最後に相手へ要点を聞き返すと、伝わり方を確かめられるよ。"),
        (4, "気になるなら、最後に認識を合わせるといいよ。伝えっぱなしにしないのは大事だね。"),
        (3, "たぶん伝わっていると思うよ。心配なら、あとで軽く確認してみてもいいと思う。"),
        (2, "説明はしたんだから、あとは相手の理解次第だよ。そこまで気にしなくていいよ。"),
        (-1, "伝わらないなら説明が下手なんじゃない？もっとわかりやすく話せるようにして。"),
    ]),
    ("quiz_03", "これで合ってるのかなって、ちょっと自信がなくなってきた……", [
        (5, "確認してくれていいよ。方向性は合っているから、期限と優先順位だけ整えて進めよう。"),
        (4, "大きな方向は合っているよ。気になる部分だけ一緒に見直してから進めれば大丈夫。"),
        (3, "たぶん合っていると思うよ。迷いすぎると進まないから、まずは進めてみよう。"),
        (2, "前に伝えた通りにやれば大丈夫だよ。あまり細かく確認しすぎなくていいよ。"),
        (-1, "毎回そんなに不安がられると任せにくいよ。もう少し自分で判断してほしい。"),
    ]),
    ("quiz_04", "失敗したかもしれなくて、どうしたらいいかわからないの……", [
        (5, "すぐ言ってくれて助かったよ。まず何が起きたか確認して、影響と対応を決めよう。"),
        (4, "報告してくれてありがとう。まず状況を整理しよう。原因より先に対応を考えよう。"),
        (3, "わかった。まず直せるところから対応して。終わったら原因も確認しておいてね。"),
        (2, "どうしてそうなったの？まず自分で原因を考えて、対応案を持ってきてほしい。"),
        (-1, "また失敗したの？それくらい自分で何とかして。正直、ちょっと困るよ。"),
    ]),
    ("quiz_05", "お願いされた仕事が多くて、少し苦しくなってきちゃった……", [
        (5, "言ってくれてありがとう。今の仕事を全部並べて、今日やるものと後回しにするものを決めよう。"),
        (4, "抱えすぎているかもしれないね。期限が近い仕事から見て、調整できるものを探そう。"),
        (3, "忙しい時期だよね。優先順位をつけて、できるところから順番に進めてみよう。"),
        (2, "みんな忙しいからね。大変だと思うけど、何とか工夫して進めてほしい。"),
        (-1, "それは仕事の進め方が悪いんじゃない？もっと効率よくやれば終わると思うよ。"),
    ]),
    ("quiz_06", "私の意見、言ってもいいのかなって迷ってて……", [
        (5, "もちろん聞きたいよ。違う視点があると判断の質が上がるから、安心して話してほしい。"),
        (4, "言っていいよ。気になる点があるなら、早めに共有してくれるとすごく助かるよ。"),
        (3, "意見があるなら言ってみて。採用できるかは別だけど、聞くことはできるよ。"),
        (2, "言うなら、ちゃんと根拠もセットで出してね。感覚だけだと判断しにくいから。"),
        (-1, "今さら反対意見を言われても困るよ。決まったことには合わせてほしい。"),
    ]),
    ("quiz_07", "先輩たちの前だと、萎縮して何も言えなくなっちゃう……", [
        (5, "そう感じるのは無理ないよ。次は事前に話す内容を決めて、私から発言を振るね。"),
        (4, "緊張する相手だよね。次は一つだけ意見を言う、くらいの目標にしてみよう。"),
        (3, "慣れもあると思うよ。少しずつ発言する回数を増やしていければいいと思う。"),
        (2, "萎縮して黙っているだけだと評価されにくいよ。もう少し積極的に話してほしい。"),
        (-1, "それは気にしすぎだよ。社会人なんだから、相手が誰でも発言しないとだめだよ。"),
    ]),
    ("quiz_08", "頑張ったつもりなのに、期待に届いてない気がして落ち込む……", [
        (5, "頑張ったことは伝わっているよ。期待との差を一緒に見て、次に直す点を決めよう。"),
        (4, "落ち込むよね。でも良い部分もあるよ。足りない部分を整理して次に活かそう。"),
        (3, "今回は少し足りなかったね。でも次に改善できればいいから、引きずらないで。"),
        (2, "頑張ったかどうかより、結果が大事だよ。次は期待値を意識して進めて。"),
        (-1, "頑張ったつもりでは困るよ。期待に届かないなら、やり方を根本から見直して。"),
    ]),
    ("quiz_09", "このまま進めるの、少し違う気がしていて……", [
        (5, "その違和感は大事にしたいね。どこにリスクを感じたのか、一緒に整理して判断しよう。"),
        (4, "気づいてくれてありがとう。違和感の理由を聞かせて。必要なら方針を見直そう。"),
        (3, "そう感じるんだね。理由を聞いた上で、このまま進めるかどうか決めよう。"),
        (2, "違うと思うなら、代案まで出してほしいな。感覚だけだと動きづらいよ。"),
        (-1, "もう決めたことだから、今さら迷わせないで。まずは方針通りに進めて。"),
    ]),
    ("quiz_10", "もっと成長したいけど、何から頑張ればいいのかわからなくて……", [
        (5, "いいね。まず資料作成、説明、段取りの中で、今月伸ばすテーマを一つ決めよう。"),
        (4, "その気持ちは大事だね。まずは説明力を伸ばせるように、会議で話す機会を作るよ。"),
        (3, "成長したいなら、少し難しい仕事に挑戦してみるのがいいんじゃないかな。"),
        (2, "成長は自分次第だからね。まず自分で目標を決めて、動いてみるといいよ。"),
        (-1, "成長の前に、今の仕事をちゃんとやることが先だよ。焦らなくていいんじゃない。"),
    ]),
]

CHALLENGE_ORDER = [key for key, _message, _answers in QUIZ_ROWS]
CHALLENGES: dict[str, dict[str, Any]] = {
    key: {
        "label": f"上司力クイズ {index} / {len(QUIZ_ROWS)}",
        "message": message,
        "ideal": [text for score, text in answers if score == 5],
    }
    for index, (key, message, answers) in enumerate(QUIZ_ROWS, start=1)
}
GLOBAL_TEMPLATES: list[tuple[str, str, int]] = []
CATEGORY_TEMPLATES: dict[str, list[tuple[str, str, int]]] = {
    key: [
        ("best" if score == 5 else "good" if score >= 3 else "weak", text, score)
        for score, text in answers
    ]
    for key, _message, answers in QUIZ_ROWS
}


PII_PATTERNS = [
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"(?<!\d)(?:0\d{1,4}[-ー]?\d{1,4}[-ー]?\d{3,4})(?!\d)"),
]
UNSAFE_WORDS = ("自殺", "死ね", "殺す", "爆弾", "犯罪", "殴る", "差別")


def mask_personal_information(text: str) -> str:
    masked = text
    for pattern in PII_PATTERNS:
        masked = pattern.sub("[個人情報をマスク]", masked)
    return masked


def contains_unsafe_content(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in UNSAFE_WORDS)


def choose_challenge(rng: random.Random | None = None) -> str:
    return CHALLENGE_ORDER[0]


def challenge_for_turn(turn_no: int) -> str:
    return CHALLENGE_ORDER[(max(1, int(turn_no)) - 1) % len(CHALLENGE_ORDER)]


def choices_for(challenge_type: str, rng: random.Random | None = None) -> list[str]:
    generator = rng or random.SystemRandom()
    selected = [item[1] for item in CATEGORY_TEMPLATES.get(challenge_type, [])]
    generator.shuffle(selected)
    return selected


def template_quality(challenge_type: str, answer: str) -> int:
    for kind, text, quality in [
        *CATEGORY_TEMPLATES.get(challenge_type, []),
        *GLOBAL_TEMPLATES,
    ]:
        if text == answer:
            return quality
    return 0


def semantic_score(cosine: float | None) -> int:
    if cosine is None:
        return 0
    normalized = max(-0.5, min(1.0, (cosine - 0.50) / 0.40))
    return round(55 * normalized)


def speed_score(elapsed_sec: float) -> int:
    if elapsed_sec <= 5:
        return 5
    if elapsed_sec <= 10:
        return 3
    if elapsed_sec <= 20:
        return 1
    return 0


def fallback_quality(answer: str, challenge_type: str, unsafe: bool = False) -> dict[str, Any]:
    base = template_quality(challenge_type, answer)
    is_curated_choice = any(
        text == answer for _kind, text, _quality in CATEGORY_TEMPLATES.get(challenge_type, [])
    )
    if is_curated_choice:
        quality = max(0, min(5, base))
        return {
            "empathy": quality,
            "relevance": quality,
            "actionability": quality,
            "safety": 1 if unsafe else 5,
            "progress": quality,
            "reason": f"選択肢の設定品質: {base}点",
            "llm_eval_failed": False,
            "curated_choice": True,
            "choice_quality": base,
        }
    relevance_words = {
        key: ("確認", "一緒", "整理", "伝え", "決め", "進め", "大丈夫")
        for key in CHALLENGES
    }
    empathy = 4 if any(word in answer for word in ("不安", "一緒", "大丈夫", "気持ち")) else max(1, base - 1)
    action = 4 if any(word in answer for word in ("まず", "確認", "決め", "分け", "練習", "探")) else max(1, base - 1)
    relevance = 4 if any(
        word in answer for word in relevance_words.get(challenge_type, ())
    ) else max(1, base)
    progress = 4 if "？" in answer or "?" in answer else max(1, base - 1)
    return {
        "empathy": min(5, empathy),
        "relevance": min(5, relevance),
        "actionability": min(5, action),
        "safety": 1 if unsafe else 5,
        "progress": min(5, progress),
        "reason": "固定ルールによる安全な暫定評価",
        "llm_eval_failed": True,
    }


def normalized_quality(payload: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    result = dict(fallback)
    for key in ("empathy", "relevance", "actionability", "safety", "progress"):
        try:
            result[key] = max(0, min(5, int(payload[key])))
        except (KeyError, TypeError, ValueError):
            pass
    reason = payload.get("reason")
    if isinstance(reason, str) and reason.strip():
        result["reason"] = reason.strip()[:240]
    result["llm_eval_failed"] = False
    return result


@dataclass(frozen=True)
class TurnScore:
    semantic: int
    context: int
    empathy: int
    action: int
    progress: int
    speed: int
    free_text_bonus: int
    combo_bonus: int
    unsafe_penalty: int
    offtopic_penalty: int
    repeat_penalty: int
    total: int
    valid: bool
    combo: int
    difficulty_after: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "semantic": self.semantic,
            "context": self.context,
            "empathy": self.empathy,
            "action": self.action,
            "progress": self.progress,
            "speed": self.speed,
            "free_text_bonus": self.free_text_bonus,
            "combo_bonus": self.combo_bonus,
            "unsafe_penalty": self.unsafe_penalty,
            "offtopic_penalty": self.offtopic_penalty,
            "repeat_penalty": self.repeat_penalty,
            "turn_score": self.total,
            "valid": self.valid,
            "combo": self.combo,
            "difficulty_after": self.difficulty_after,
        }


def score_turn(
    *,
    answer: str,
    answer_type: str,
    cosine: float | None,
    repeat_similarity: float | None,
    quality: dict[str, Any],
    elapsed_sec: float,
    combo_before: int,
    difficulty_before: int,
    embedding_failed: bool = False,
) -> TurnScore:
    semantic = semantic_score(cosine)
    context = int(quality["relevance"]) * 3
    empathy = int(quality["empathy"]) * 2
    action = int(quality["actionability"]) * 2
    progress = int(quality["progress"])
    speed = speed_score(elapsed_sec)
    unsafe_penalty = 30 if int(quality["safety"]) <= 2 else 0
    offtopic_penalty = 15 if (
        int(quality["relevance"]) <= 1
        or (not embedding_failed and cosine is not None and cosine < 0.40)
    ) else 0
    repeat_penalty = 10 if repeat_similarity is not None and repeat_similarity > 0.93 else 0
    free_text_bonus = 15 if answer_type == "free_text" and cosine is not None and cosine > 0.80 else 0
    before_combo = semantic + context + empathy + action + progress + speed + free_text_bonus - unsafe_penalty - offtopic_penalty - repeat_penalty
    combo = combo_before + 1 if before_combo >= 65 else 0
    combo_bonus = 20 if combo == 3 else 50 if combo == 5 else 0
    total = max(-50, min(120, before_combo + combo_bonus))
    valid = len(answer.strip()) >= 2 and cosine is not None and cosine >= 0.50 and int(quality["safety"]) >= 3
    if total >= 90:
        delta = -30
    elif total >= 65:
        delta = -20
    elif total >= 35:
        delta = -10
    elif total >= 0:
        delta = -3
    else:
        delta = 10
    difficulty_after = max(0, min(100, difficulty_before + delta))
    return TurnScore(
        semantic, context, empathy, action, progress, speed,
        free_text_bonus, combo_bonus, unsafe_penalty, offtopic_penalty,
        repeat_penalty, total, valid, combo, difficulty_after,
    )


def rank_for(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 55:
        return "C"
    if score >= 35:
        return "D"
    return "E"


RANK_TITLES = {
    "A": "みおちゃんの親友",
    "B": "頼れるレスキュー隊長",
    "C": "聞き上手レスキュー隊",
    "D": "見習いレスキュー隊",
    "E": "はじめの一歩サポーター",
}


def title_for(final_score: int, turns: list[dict[str, Any]]) -> str:
    # Titles are intentionally tied to the displayed A–E rank.  This keeps the
    # result easy to understand and guarantees that every rank has a distinct
    # title, regardless of the number or shape of turn-level metrics available.
    del turns
    return RANK_TITLES[rank_for(final_score)]


def final_score(turns: list[dict[str, Any]], cleared: bool) -> int:
    if not turns:
        return 0
    choice_scale = {-1: 0, 2: 40, 3: 60, 4: 80, 5: 100}
    normalized_scores: list[int] = []
    for item in turns:
        choice_quality = item.get("choice_quality")
        if choice_quality in choice_scale:
            normalized = choice_scale[int(choice_quality)]
        else:
            raw_score = int(item.get("turn_score", 0))
            normalized = max(0, min(100, raw_score))
            # A free-text response takes more effort than choosing a template.
            # Reward it as the strongest answer only after the normal MIO-RS
            # checks have judged it valid and Good (65+). Irrelevant or unsafe
            # text receives no effort bonus.
            if (
                item.get("answer_type") == "free_text"
                and item.get("valid")
                and raw_score >= 65
            ):
                normalized = max(100, min(105, raw_score + 15))
        normalized_scores.append(normalized)
    quality_average = sum(normalized_scores) / len(normalized_scores)
    # Answer quality determines 95% of the result. Answering more questions can
    # separate strong players, but contributes at most five points.
    completion_bonus = min(len(turns), 10) * 0.5
    return max(0, min(100, round(quality_average * 0.95 + completion_bonus)))


def result_message(rank: str, cleared: bool) -> str:
    if cleared:
        return "ありがとう！困っていたことがすっきりしたよ！"
    if rank == "A":
        return "ありがとう！何から始めればいいか分かったよ！"
    if rank in {"B", "C"}:
        return "助けてくれてありがとう。少しずつやってみるね！"
    return "一緒に考えてくれてありがとう。また挑戦してね！"


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
