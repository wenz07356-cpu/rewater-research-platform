"""DeepAgent 证据检索接口的最小契约测试。"""

import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.http import query_server
from app.rag.query import evidence_retrieval_service


def _candidate(index: int = 1) -> dict:
    return {
        "chunk_id": f"chunk-{index}",
        "document_id": f"doc-{index}",
        "file_title": "深圳市再生水利用规划",
        "section_title": "再生水利用方向",
        "content": f"第 {index} 条知识库原始证据。",
        "score": 0.7,
        "rerank_score": 0.9 - index * 0.01,
        "candidate_id": f"internal-{index}",
        "prompt": "不得公开",
    }


class RetrievalApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(query_server.app)

    def test_minimum_request_uses_defaults_and_normalizes_query(self) -> None:
        with patch.object(
            query_server,
            "retrieve_evidence",
            return_value={"answer": "", "reranked_docs": []},
        ) as retrieve:
            response = self.client.post(
                "/retrieval", json={"query": "  深圳市   再生水  "}
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "empty")
        self.assertEqual(body["query"], "深圳市 再生水")
        self.assertEqual(body["chunks"], [])
        uuid.UUID(body["request_id"])
        self.assertEqual(retrieve.call_args.args[0], "深圳市 再生水")

    def test_invalid_query_top_k_and_extra_fields_return_422(self) -> None:
        invalid_bodies = (
            {"query": "   "},
            {"query": "问题", "top_k": 0},
            {"query": "问题", "top_k": 7},
            {"query": "问题", "top_k": "6"},
            {"query": "问题", "filters": {}},
        )
        for body in invalid_bodies:
            with self.subTest(body=body):
                response = self.client.post("/retrieval", json=body)
                self.assertEqual(response.status_code, 422)

    def test_ok_response_maps_fields_preserves_content_and_applies_top_k(self) -> None:
        documents = [_candidate(1), _candidate(2)]
        with patch.object(
            query_server,
            "retrieve_evidence",
            return_value={"answer": "", "reranked_docs": documents},
        ):
            response = self.client.post(
                "/retrieval", json={"query": "深圳市再生水", "top_k": 1}
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(len(body["chunks"]), 1)
        self.assertEqual(
            body["chunks"][0],
            {
                "chunk_id": "chunk-1",
                "document_id": "doc-1",
                "document_name": "深圳市再生水利用规划",
                "section_title": "再生水利用方向",
                "content": "第 1 条知识库原始证据。",
                "score": 0.89,
            },
        )
        self.assertNotIn("candidate_id", body["chunks"][0])
        self.assertNotIn("prompt", body["chunks"][0])

    def test_invalid_candidates_are_ignored(self) -> None:
        documents = [
            {**_candidate(1), "chunk_id": ""},
            {**_candidate(2), "content": "   "},
            {**_candidate(3), "rerank_score": float("nan")},
        ]
        chunks = evidence_retrieval_service.build_retrieval_chunks(documents, 6)
        self.assertEqual(chunks, [])

    def test_needs_clarification_returns_question_without_chunks(self) -> None:
        with patch.object(
            query_server,
            "retrieve_evidence",
            return_value={
                "answer": "请补充需要查询的地区。",
                "reranked_docs": [_candidate()],
            },
        ):
            response = self.client.post(
                "/retrieval", json={"query": "当地再生水情况"}
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "needs_clarification")
        self.assertEqual(body["clarification_question"], "请补充需要查询的地区。")
        self.assertEqual(body["chunks"], [])

    def test_service_disables_history_web_and_answer_generation(self) -> None:
        from app.rag.query import answer_output_service
        from app.rag.query import item_name_confirm_service
        from app.rag.query import web_search_service

        understanding = {
            "rewritten_query": "深圳市再生水利用",
            "file_titles": [],
            "region_names": ["深圳市"],
            "document_types": [],
            "topics": ["再生水利用"],
            "keywords": [],
            "strict": False,
            "needs_clarification": False,
            "clarification_question": "",
        }
        with patch.object(
            item_name_confirm_service,
            "call_llm_query_understanding",
            return_value=understanding,
        ), patch.object(
            item_name_confirm_service.history_repository, "list_recent"
        ) as list_history, patch.object(
            item_name_confirm_service.history_repository, "save_message"
        ) as save_history, patch.object(
            evidence_retrieval_service,
            "search_chunks",
            return_value={"embedding_chunks": [_candidate()]},
        ) as embedding, patch.object(
            evidence_retrieval_service,
            "search_chunks_with_hyde",
            return_value={"hyde_embedding_chunks": []},
        ) as hyde, patch.object(
            evidence_retrieval_service,
            "fuse_retrieval_results",
            return_value={"rrf_chunks": [_candidate()]},
        ) as rrf, patch.object(
            evidence_retrieval_service,
            "rerank_documents",
            return_value={"reranked_docs": [_candidate()]},
        ) as rerank, patch.object(
            web_search_service, "search_web_documents"
        ) as web, patch.object(
            answer_output_service, "produce_answer"
        ) as answer:
            state = evidence_retrieval_service.retrieve_evidence(
                "深圳市再生水利用", "request-1"
            )

        self.assertTrue(state["eval_disable_history"])
        self.assertTrue(state["eval_disable_web"])
        self.assertEqual(state["session_id"], "request-1")
        self.assertEqual(len(state["reranked_docs"]), 1)
        list_history.assert_not_called()
        save_history.assert_not_called()
        web.assert_not_called()
        answer.assert_not_called()
        embedding.assert_called_once()
        hyde.assert_called_once()
        rrf.assert_called_once()
        rerank.assert_called_once()

    def test_clarification_short_circuits_all_retrieval_stages(self) -> None:
        with patch.object(
            evidence_retrieval_service,
            "understand_query",
            return_value={
                "rewritten_query": "",
                "query_filters": {},
                "history": [],
                "answer": "请补充具体地区。",
            },
        ), patch.object(
            evidence_retrieval_service, "search_chunks"
        ) as embedding, patch.object(
            evidence_retrieval_service, "search_chunks_with_hyde"
        ) as hyde, patch.object(
            evidence_retrieval_service, "fuse_retrieval_results"
        ) as rrf, patch.object(
            evidence_retrieval_service, "rerank_documents"
        ) as rerank:
            state = evidence_retrieval_service.retrieve_evidence(
                "当地情况", "request-2"
            )

        self.assertEqual(state["answer"], "请补充具体地区。")
        embedding.assert_not_called()
        hyde.assert_not_called()
        rrf.assert_not_called()
        rerank.assert_not_called()

    def test_index_exposes_retrieval_route(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["routes"]["retrieval"], "/retrieval")


if __name__ == "__main__":
    unittest.main()
