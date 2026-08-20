"""新版 query service 的无外部依赖契约测试。"""

import unittest
from unittest.mock import patch

from app.process.query.agent.state import create_query_default_state
from app.rag.query.answer_output_service import (
    build_evidence_context,
    build_source_label,
    produce_answer,
    replace_legacy_source_labels,
)
from app.rag.query.rerank_service import build_rerank_text, rerank_documents
from app.rag.query.rrf_service import fuse_retrieval_results
from app.rag.query.search_embedding_service import (
    build_milvus_filter_expr,
    normalize_local_candidates,
    normalize_query_filters,
)


def _local_candidate(chunk_id: str, score: float = 0.8) -> dict:
    return {
        "chunk_id": chunk_id,
        "document_id": "doc-1",
        "chunk_index": 0,
        "file_title": "北京市再生水管理办法",
        "section_title": "利用管理",
        "display_title": "北京市再生水管理办法 / 利用管理",
        "content": "再生水利用应当符合相关管理要求。",
        "context_type": "text",
        "region_names": ["北京市"],
        "document_type": "政策",
        "topics": ["再生水利用"],
        "keywords": ["利用管理"],
        "score": score,
        "source": "milvus",
        "retrieval_source": "embedding",
        "url": "",
    }


class _FakeTokenizer:
    def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:
        return list(range(len(text)))

    def decode(self, tokens: list[int], skip_special_tokens: bool = True) -> str:
        return "截取文本"


class _FakeReranker:
    tokenizer = _FakeTokenizer()

    def compute_score(
        self,
        pairs: list[list[str]],
        normalize: bool = True,
    ) -> list[float]:
        return [0.9 - index * 0.1 for index in range(len(pairs))]


class QueryServiceTests(unittest.TestCase):
    """验证新版字段、降级逻辑和 LangGraph 状态契约。"""

    def test_filter_expression_uses_new_schema(self) -> None:
        filters = normalize_query_filters(
            {
                "region_names": ["北京市"],
                "document_types": ["政策", "非法类型"],
                "hard_fields": ["region_names", "document_types"],
                "strict": False,
            }
        )
        expression = build_milvus_filter_expr(filters)
        self.assertNotIn("item_name", expression)
        self.assertIn("document_type", expression)
        self.assertIn("region_names", expression)
        self.assertIn("全国", expression)
        self.assertEqual(filters["document_types"], ["政策"])

    def test_local_candidate_and_rrf_contract(self) -> None:
        hit = {
            "distance": 0.91,
            "entity": {**_local_candidate("chunk-1"), "token_count": 20},
        }
        direct = normalize_local_candidates([hit], "embedding")
        hyde = [
            {**direct[0], "score": 0.7, "retrieval_source": "hyde"}
        ]
        update = fuse_retrieval_results(
            {
                "embedding_chunks": direct,
                "hyde_embedding_chunks": hyde,
            }
        )
        self.assertEqual(len(update["rrf_chunks"]), 1)
        result = update["rrf_chunks"][0]
        self.assertEqual(
            result["display_title"],
            "北京市再生水管理办法 / 利用管理",
        )
        self.assertEqual(result["retrieval_sources"], ["embedding", "hyde"])

    def test_reranker_accepts_local_only(self) -> None:
        from app.rag.query import rerank_service

        state = create_query_default_state(
            rewritten_query="北京市再生水利用有哪些管理要求？",
            rrf_chunks=[_local_candidate("chunk-1")],
            web_search_docs=[],
        )
        with patch.object(
            rerank_service.llm_provider,
            "reranker_model",
            return_value=_FakeReranker(),
        ):
            update = rerank_documents(state)
        self.assertEqual(len(update["reranked_docs"]), 1)
        self.assertEqual(update["reranked_docs"][0]["score"], 0.9)

    def test_rerank_text_uses_same_fields_for_local_and_web(self) -> None:
        local = _local_candidate("chunk-1")
        web = {
            **local,
            "source": "web",
            "url": "https://example.com/rewater-policy",
        }

        expected = (
            "北京市再生水管理办法 / 利用管理\n"
            "再生水利用应当符合相关管理要求。"
        )
        self.assertEqual(build_rerank_text(local), expected)
        self.assertEqual(build_rerank_text(web), expected)
        self.assertNotIn("政策", build_rerank_text(local))
        self.assertNotIn("北京市\n", build_rerank_text(local))
        self.assertEqual(local["region_names"], ["北京市"])

    def test_evidence_context_has_source_without_confidence(self) -> None:
        context = build_evidence_context([_local_candidate("chunk-1")])
        self.assertIn(
            "[本地知识库/北京市再生水管理办法/利用管理]",
            context,
        )
        self.assertNotIn("[来源1]", context)
        self.assertNotIn("置信度", context)

    def test_source_label_unifies_embedding_hyde_and_web(self) -> None:
        direct = _local_candidate("chunk-1")
        hyde = {**direct, "retrieval_source": "hyde"}
        web = {
            "source": "web",
            "url": "https://example.com/rewater-policy",
        }
        expected_local = (
            "[本地知识库/北京市再生水管理办法/利用管理]"
        )
        self.assertEqual(build_source_label(direct), expected_local)
        self.assertEqual(build_source_label(hyde), expected_local)
        self.assertEqual(
            build_source_label(web),
            "[网络搜索/https://example.com/rewater-policy]",
        )

    def test_legacy_numeric_source_is_replaced(self) -> None:
        answer = "宣传工作应广泛开展 [来源1]。"
        result = replace_legacy_source_labels(
            answer,
            [_local_candidate("chunk-1")],
        )
        self.assertEqual(
            result,
            "宣传工作应广泛开展 "
            "[本地知识库/北京市再生水管理办法/利用管理]。",
        )

    def test_no_result_uses_fixed_answer(self) -> None:
        from app.rag.query import answer_output_service

        state = create_query_default_state(
            session_id="test-no-result",
            original_query="没有命中的问题",
            rewritten_query="没有命中的问题",
            reranked_docs=[],
        )
        with patch.object(answer_output_service, "save_answer_history"):
            update = produce_answer(state)
        self.assertEqual(
            update["answer"],
            "未检索到足以回答该问题的参考内容。",
        )
        self.assertEqual(update["image_urls"], [])

    def test_query_graph_state_contract(self) -> None:
        """使用 mock 外部服务验证并行图可汇合并到达答案节点。"""
        from app.process.query.agent import main_graph
        from app.process.query.agent.nodes import node_answer_output
        from app.process.query.agent.nodes import node_item_name_confirm
        from app.process.query.agent.nodes import node_rerank
        from app.process.query.agent.nodes import node_search_embedding
        from app.process.query.agent.nodes import node_search_embedding_hyde
        from app.process.query.agent.nodes import node_web_search_mcp

        patches = (
            patch.object(
                node_item_name_confirm,
                "understand_query",
                side_effect=lambda state: {
                    "rewritten_query": state["original_query"],
                    "query_filters": {},
                    "history": [],
                    "answer": "",
                },
            ),
            patch.object(
                node_search_embedding,
                "search_chunks",
                return_value={
                    "embedding_chunks": [_local_candidate("chunk-1")]
                },
            ),
            patch.object(
                node_search_embedding_hyde,
                "search_chunks_with_hyde",
                return_value={"hyde_embedding_chunks": []},
            ),
            patch.object(
                node_web_search_mcp,
                "search_web_documents",
                return_value={"web_search_docs": []},
            ),
            patch.object(
                node_rerank,
                "rerank_documents",
                side_effect=lambda state: {
                    "reranked_docs": state["rrf_chunks"][:1]
                },
            ),
            patch.object(
                node_answer_output,
                "produce_answer",
                return_value={
                    "answer": "图执行成功",
                    "image_urls": [],
                    "prompt": "",
                },
            ),
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            final_state = main_graph.query_app.invoke(
                create_query_default_state(
                    session_id="test-graph",
                    original_query="北京市再生水利用要求是什么？",
                )
            )
        self.assertEqual(final_state["answer"], "图执行成功")
        self.assertEqual(len(final_state["rrf_chunks"]), 1)


if __name__ == "__main__":
    unittest.main()
