from __future__ import annotations

import hashlib
import math
import re


EMBEDDING_DIMENSION = 1024

SEMANTIC_AXES: tuple[tuple[str, ...], ...] = (
    ("静か", "個室", "集中", "一人", "深く", "自律", "没頭"),
    ("会話", "交流", "みんな", "共創", "チーム", "つなが", "雑談"),
    ("カフェ", "ソファ", "快適", "リラックス", "くつろ", "余白"),
    ("自然", "緑", "光", "開放", "庭", "植物", "景色"),
    ("効率", "機能", "無駄", "生産性", "設備", "合理", "動線"),
    ("自由", "好きな場所", "フリー", "柔軟", "リモート", "選べ"),
    ("健康", "運動", "睡眠", "食事", "ウェルネス"),
    ("成長", "学習", "挑戦", "キャリア", "研修", "未来"),
)


def _tokens(text: str) -> list[str]:
    compact = re.sub(r"\s+", "", text.lower())
    latin = re.findall(r"[a-z0-9]+", compact)
    japanese = [compact[i : i + 2] for i in range(max(0, len(compact) - 1))]
    return latin + japanese


def demo_embedding(text: str) -> list[float]:
    """Create a deterministic 1024-d vector for the offline demo fallback.

    The first axes are human-readable concepts and the remainder are signed
    feature hashes. Production can replace this with OCI embeddings without
    changing the Oracle VECTOR schema.
    """

    vector = [0.0] * EMBEDDING_DIMENSION
    lowered = text.lower()

    for axis, keywords in enumerate(SEMANTIC_AXES):
        hits = sum(1 for keyword in keywords if keyword in lowered)
        if hits:
            vector[axis] = 1.5 + 0.5 * hits

    for token in _tokens(text):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        raw = int.from_bytes(digest, "big")
        index = 16 + raw % (EMBEDDING_DIMENSION - 16)
        vector[index] += 1.0 if raw & 1 else -1.0

    if not any(vector):
        vector[15] = 1.0

    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [round(value / norm, 7) for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.7f}" for value in vector) + "]"


def sparse_vector_literal(vector: list[float]) -> str:
    indices = [index for index, value in enumerate(vector) if value != 0.0]
    values = [vector[index] for index in indices]
    return (
        f"[{len(vector)},["
        + ",".join(str(index) for index in indices)
        + "],["
        + ",".join(f"{value:.7f}" for value in values)
        + "]]"
    )
