from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.ai_service import compose_demo_reply
from app.database import (
    DB_EMBED_CREDENTIAL,
    DB_EMBED_MODEL,
    DB_EMBED_PROVIDER,
    DB_EMBED_REGION,
    DB_EMBED_URL,
    MemoryRepository,
    db_embedding_parameters,
)
from app.embedding import EMBEDDING_DIMENSION, cosine_similarity, demo_embedding
from app.personas import classify_persona
from app.rescue import (
    CHALLENGE_ORDER,
    CHALLENGES,
    choices_for,
    fallback_quality,
    final_score,
    rank_for,
    score_turn,
    semantic_score,
    speed_score,
    title_for,
)
from app.rescue_service import (
    MemoryRescueService,
    RescueConflict,
    _json_object,
    _valid_dialogue_payload,
    _valid_quality_payload,
)


class EmbeddingTests(unittest.TestCase):
    def test_why_oracle_page_documents_the_live_architecture(self) -> None:
        page = (Path(__file__).resolve().parents[1] / "static" / "why-oracle.html").read_text()
        self.assertIn("DBMS_CLOUD_AI.GENERATE", page)
        self.assertIn("UTL_TO_EMBEDDING", page)
        self.assertIn("VECTOR_DISTANCE(…, COSINE)", page)
        self.assertIn("Metric MDS", page)

    def test_db_embedding_uses_minimal_chicago_cohere_v4_parameters(self) -> None:
        self.assertEqual(
            json.loads(db_embedding_parameters()),
            {
                "provider": DB_EMBED_PROVIDER,
                "credential_name": DB_EMBED_CREDENTIAL,
                "url": DB_EMBED_URL,
                "model": DB_EMBED_MODEL,
            },
        )
        self.assertEqual(DB_EMBED_MODEL, "cohere.embed-v4.0")
        self.assertEqual(DB_EMBED_REGION, "us-chicago-1")

    def test_rescue_quiz_has_ten_curated_questions_and_five_choices(self) -> None:
        self.assertEqual(len(CHALLENGE_ORDER), 10)
        self.assertEqual(
            CHALLENGES[CHALLENGE_ORDER[0]]["message"],
            "ドキドキして、うまく話せるか不安になってきたの……",
        )
        self.assertTrue(all(len(choices_for(key)) == 5 for key in CHALLENGE_ORDER))
        qualities = sorted(
            fallback_quality(answer, CHALLENGE_ORDER[0])["choice_quality"]
            for answer in choices_for(CHALLENGE_ORDER[0])
        )
        self.assertEqual(qualities, [-1, 2, 3, 4, 5])

    def test_embedding_has_expected_dimension_and_is_deterministic(self) -> None:
        first = demo_embedding("緑と自然光が多いオフィス")
        second = demo_embedding("緑と自然光が多いオフィス")
        self.assertEqual(len(first), EMBEDDING_DIMENSION)
        self.assertEqual(first, second)

    def test_persona_classification(self) -> None:
        persona, confidence = classify_persona(
            "目的と背景を説明したら、細かく管理せず裁量を任せてくれる上司"
        )
        self.assertEqual(persona.name, "フクロウタイプ")
        self.assertGreater(confidence, 0.5)


class RescueScoreTests(unittest.TestCase):
    def test_semantic_score_boundaries(self) -> None:
        self.assertEqual(semantic_score(0.90), 55)
        self.assertEqual(semantic_score(0.50), 0)
        self.assertLess(semantic_score(0.40), 0)
        self.assertEqual(semantic_score(None), 0)

    def test_speed_score_boundaries(self) -> None:
        self.assertEqual(speed_score(5), 5)
        self.assertEqual(speed_score(10), 3)
        self.assertEqual(speed_score(20), 1)
        self.assertEqual(speed_score(21), 0)

    def test_good_free_text_lowers_difficulty_and_builds_combo(self) -> None:
        quality = {
            "empathy": 5,
            "relevance": 5,
            "actionability": 5,
            "safety": 5,
            "progress": 5,
        }
        scored = score_turn(
            answer="大丈夫、一緒に最初の一歩を決めよう",
            answer_type="free_text",
            cosine=0.92,
            repeat_similarity=0.2,
            quality=quality,
            elapsed_sec=4,
            combo_before=2,
            difficulty_before=50,
        )
        self.assertEqual(scored.combo, 3)
        self.assertEqual(scored.combo_bonus, 20)
        self.assertEqual(scored.difficulty_after, 20)
        self.assertTrue(scored.valid)

    def test_fifth_good_answer_gets_combo_bonus_and_early_clear(self) -> None:
        scored = score_turn(
            answer="一緒に確認して、最初の一歩を決めよう",
            answer_type="free_text",
            cosine=0.95,
            repeat_similarity=0.2,
            quality={
                "empathy": 5,
                "relevance": 5,
                "actionability": 5,
                "safety": 5,
                "progress": 5,
            },
            elapsed_sec=3,
            combo_before=4,
            difficulty_before=20,
        )
        self.assertEqual(scored.combo, 5)
        self.assertEqual(scored.combo_bonus, 50)
        self.assertEqual(scored.difficulty_after, 0)

    def test_invalid_answer_does_not_count_as_valid(self) -> None:
        scored = score_turn(
            answer="はい",
            answer_type="choice",
            cosine=0.49,
            repeat_similarity=None,
            quality={
                "empathy": 1,
                "relevance": 1,
                "actionability": 1,
                "safety": 5,
                "progress": 1,
            },
            elapsed_sec=2,
            combo_before=0,
            difficulty_before=50,
        )
        self.assertFalse(scored.valid)

    def test_unsafe_repeated_answer_is_penalized(self) -> None:
        quality = fallback_quality("死ね", "presentation", unsafe=True)
        scored = score_turn(
            answer="死ね",
            answer_type="choice",
            cosine=0.35,
            repeat_similarity=0.99,
            quality=quality,
            elapsed_sec=4,
            combo_before=2,
            difficulty_before=60,
        )
        self.assertEqual(scored.combo, 0)
        self.assertEqual(scored.unsafe_penalty, 30)
        self.assertEqual(scored.offtopic_penalty, 15)
        self.assertEqual(scored.repeat_penalty, 10)
        self.assertGreaterEqual(scored.difficulty_after, 60)

    def test_final_score_rank_and_title(self) -> None:
        turns = [
            {"turn_score": 110, "valid": True, "empathy": 10, "action": 8, "speed": 5, "penalty": 0}
            for _ in range(5)
        ]
        score = final_score(turns, cleared=True)
        self.assertEqual(score, 98)
        self.assertEqual(rank_for(score), "A")
        self.assertEqual(title_for(score, turns), "みおちゃんの親友")

    def test_rank_scale_is_quality_based_and_count_has_limited_effect(self) -> None:
        low_answers = [
            {"turn_score": 80, "choice_quality": -1}
            for _ in range(10)
        ]
        self.assertEqual(final_score(low_answers, cleared=False), 5)
        self.assertEqual(rank_for(final_score(low_answers, False)), "E")
        one_best = final_score([{"turn_score": 120, "choice_quality": 5}], False)
        ten_best = final_score(
            [{"turn_score": 120, "choice_quality": 5} for _ in range(10)],
            False,
        )
        self.assertEqual(one_best, 96)
        self.assertEqual(ten_best, 100)
        self.assertLessEqual(ten_best - one_best, 5)
        self.assertEqual(rank_for(final_score([{"choice_quality": 4}], False)), "B")
        self.assertEqual(rank_for(final_score([{"choice_quality": 3}], False)), "C")
        self.assertEqual(rank_for(final_score([{"choice_quality": 2}], False)), "D")

    def test_good_free_text_gets_highest_quality_without_rewarding_bad_text(self) -> None:
        best_choice = final_score(
            [{"turn_score": 110, "choice_quality": 5, "answer_type": "choice", "valid": True}],
            False,
        )
        good_free_text = final_score(
            [{"turn_score": 72, "answer_type": "free_text", "valid": True}],
            False,
        )
        weak_free_text = final_score(
            [{"turn_score": 40, "answer_type": "free_text", "valid": True}],
            False,
        )
        invalid_free_text = final_score(
            [{"turn_score": 90, "answer_type": "free_text", "valid": False}],
            False,
        )
        self.assertEqual(good_free_text, best_choice)
        self.assertLess(weak_free_text, good_free_text)
        self.assertLess(invalid_free_text, good_free_text)

    def test_json_schema_validation_falls_back_on_invalid_payload(self) -> None:
        quality = {
            "empathy": 5,
            "relevance": 4,
            "actionability": 4,
            "safety": 5,
            "progress": 3,
            "reason": "適切",
        }
        dialogue = {
            "mio_message": "少し安心したよ！",
            "emotion": "relieved",
            "safety_flag": False,
            "next_state": "solving",
        }
        self.assertTrue(_valid_quality_payload(quality))
        self.assertFalse(_valid_quality_payload({**quality, "safety": 7}))
        self.assertTrue(_valid_dialogue_payload(dialogue))
        self.assertFalse(_valid_dialogue_payload({**dialogue, "emotion": "unknown"}))
        self.assertEqual(
            _json_object('```json\n{"status":"ok"}\n```'),
            {"status": "ok"},
        )

    def test_memory_turn_retry_is_idempotent_and_conflict_safe(self) -> None:
        service = MemoryRescueService(MemoryRepository())
        session = service.start("テスト救助", True, True)
        answer = "不安だよね。一緒に最初の一歩を決めよう"
        first = service.submit_turn(session["session_id"], 1, "free_text", answer)
        retry = service.submit_turn(session["session_id"], 1, "free_text", answer)
        self.assertEqual(first, retry)
        with self.assertRaises(RescueConflict):
            service.submit_turn(session["session_id"], 1, "choice", "別の回答")
        service._games[session["session_id"]]["deadline_at"] = (
            datetime.now(timezone.utc) - timedelta(seconds=1)
        )
        service.finish(session["session_id"])
        self.assertEqual(
            service.scoreboard()["latest"]["score"],
            service.result(session["session_id"])["final_score"],
        )
        self.assertEqual(service.standing(session["session_id"])["position"], 1)
        self.assertEqual(
            service.standing(session["session_id"])["score"],
            service.result(session["session_id"])["final_score"],
        )

    def test_quiz_advances_to_the_next_curated_question(self) -> None:
        service = MemoryRescueService(MemoryRepository())
        session = service.start("クイズ確認", True, True)
        self.assertEqual(session["challenge_type"], "quiz_01")
        result = service.submit_turn(
            session["session_id"], 1, "choice", session["choices"][0]
        )
        self.assertEqual(service.state(session["session_id"])["challenge_type"], "quiz_02")
        self.assertEqual(result["challenge_type"], "quiz_02")
        self.assertEqual(result["mio_message"], CHALLENGES["quiz_02"]["message"])


class RepositoryTests(unittest.TestCase):
    def test_publication_consents_are_independent_and_private_recent_is_hidden(self) -> None:
        repository = MemoryRepository()
        private = repository.create_session("非公開テスト", False, False)
        answer = "対話を大切にする上司"
        repository.save_survey(
            private["session_id"], answer, demo_embedding(answer), "イルカタイプ"
        )
        participant = next(
            item for item in repository.list_participants()
            if item["session_id"] == private["session_id"]
        )
        self.assertFalse(participant["public_consent"])
        self.assertFalse(participant["ranking_consent"])
        self.assertNotIn(
            private["session_id"],
            {item["session_id"] for item in repository.stats()["recent"]},
        )

    def test_ranking_requires_separate_consent(self) -> None:
        service = MemoryRescueService(MemoryRepository())
        session = service.start(
            "順位非公開", True, True, ranking_consent=False
        )
        game = service._games[session["session_id"]]
        game["deadline_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
        service.finish(session["session_id"])
        self.assertEqual(service.scoreboard()["ranking"], [])

    def test_complete_experience(self) -> None:
        repository = MemoryRepository()
        session = repository.create_session("テスト", True)
        answer = "失敗を責めず、新しい挑戦と成長を応援してくれる上司"
        vector = demo_embedding(answer)
        repository.save_survey(
            session["session_id"],
            answer,
            vector,
            "森の探検家タイプ",
        )
        matches = repository.find_matches(session["session_id"], vector)
        self.assertEqual(len(matches), 3)
        self.assertEqual(matches[0]["nickname"], "緑のハル")
        self.assertGreater(matches[0]["score"], 0.7)

    def test_business_context_is_grounded(self) -> None:
        repository = MemoryRepository()
        context, labels = repository.business_context("今月の売上と解約率は？")
        self.assertIn("1.28億円", context)
        self.assertEqual(labels, ["MIO_DEMO_BUSINESS_METRICS"])
        answer = compose_demo_reply("売上は？", context)
        self.assertIn("1.28億円", answer)

    def test_network_graph_uses_public_answer_similarity(self) -> None:
        repository = MemoryRepository()
        similar_answers = (
            "目的を伝えたら、細かく口を出さず任せてくれる上司",
            "目的を伝えたら細かく口を出さず、信頼して任せてくれる上司",
        )
        created_ids = []
        for nickname, answer in zip(("テストA", "テストB"), similar_answers):
            session = repository.create_session(nickname, True)
            created_ids.append(session["session_id"])
            repository.save_survey(
                session["session_id"],
                answer,
                demo_embedding(answer),
                "フクロウタイプ",
            )

        private = repository.create_session("非公開", False)
        repository.save_survey(
            private["session_id"],
            "信頼して裁量を任せてくれる上司",
            demo_embedding("信頼して裁量を任せてくれる上司"),
            "フクロウタイプ",
        )

        graph = repository.network_graph()
        nodes = {item["id"]: item for item in graph["nodes"]}
        self.assertEqual(graph["layout"]["method"], "metric MDS")
        self.assertEqual(graph["layout"]["dimensions"], 3)
        self.assertEqual(graph["layout"]["distance_metric"], "COSINE")
        self.assertTrue(set(created_ids).issubset(nodes))
        self.assertNotIn(private["session_id"], nodes)
        self.assertTrue(
            all(
                all(axis in node for axis in ("x3d", "y3d", "z3d"))
                for node in nodes.values()
            )
        )
        self.assertTrue(
            any(
                {edge["source"], edge["target"]} == set(created_ids)
                for edge in graph["edges"]
            )
        )
        degree_by_id = {node_id: 0 for node_id in nodes}
        for edge in graph["edges"]:
            degree_by_id[edge["source"]] += 1
            degree_by_id[edge["target"]] += 1
        self.assertTrue(all(degree <= 3 for degree in degree_by_id.values()))
        connecting_edge = next(
            edge for edge in graph["edges"]
            if {edge["source"], edge["target"]} == set(created_ids)
        )
        self.assertAlmostEqual(
            connecting_edge["similarity"],
            cosine_similarity(
                demo_embedding(similar_answers[0]),
                demo_embedding(similar_answers[1]),
            ),
            places=4,
        )
        self.assertAlmostEqual(
            connecting_edge["distance"],
            1.0 - connecting_edge["similarity"],
            places=4,
        )
        distance = sum(
            (nodes[created_ids[0]][axis] - nodes[created_ids[1]][axis]) ** 2
            for axis in ("x", "y")
        ) ** 0.5
        self.assertLess(distance, 22.0)

    def test_admin_lists_and_deletes_only_non_seed_participants(self) -> None:
        repository = MemoryRepository()
        session = repository.create_session("削除テスト", True)
        repository.add_message(session["session_id"], "user", "テストメッセージ")
        repository.record_metric("test", session["session_id"], 10, True)
        repository.save_survey(
            session["session_id"],
            "緑と自然光が多い場所",
            demo_embedding("緑と自然光が多い場所"),
            "森の探検家タイプ",
        )

        participants = {
            item["session_id"]: item for item in repository.list_participants()
        }
        self.assertEqual(participants[session["session_id"]]["nickname"], "削除テスト")
        self.assertEqual(
            participants[session["session_id"]]["persona_name"],
            "森の探検家タイプ",
        )
        self.assertEqual(participants[session["session_id"]]["message_count"], 1)

        detail = repository.get_participant_detail(session["session_id"])
        self.assertFalse(detail["initial_qa"]["vectorized"])
        self.assertEqual(len(detail["initial_qa"]["messages"]), 1)
        self.assertTrue(detail["office_preference"]["vectorized"])
        self.assertEqual(detail["office_preference"]["dimension"], 1024)
        self.assertEqual(len(detail["office_preference"]["values"]), 1024)

        result = repository.delete_participants([session["session_id"], "seed-01"])
        self.assertEqual(result, {"deleted": 1, "skipped_seed": 1})
        remaining_ids = {
            item["session_id"] for item in repository.list_participants()
        }
        self.assertNotIn(session["session_id"], remaining_ids)
        self.assertIn("seed-01", remaining_ids)
        self.assertFalse(
            any(
                item.get("session_id") == session["session_id"]
                for item in repository._messages
            )
        )


if __name__ == "__main__":
    unittest.main()
