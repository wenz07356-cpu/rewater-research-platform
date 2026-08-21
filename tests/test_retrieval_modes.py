"""请求级检索模式和公开元数据契约测试。"""

from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import Mock, patch

from pydantic import ValidationError
from app.api.schemas.query import QueryRequest
from app.rag.query import config
from app.rag.query.item_name_confirm_service import normalize_query_understanding
from app.rag.query.item_name_confirm_service import save_user_query_history
from app.rag.query.retrieval_config import (
    build_retrieval_metadata,
    get_effective_retrieval_config,
    resolve_retrieval_config,
)
from app.rag.query.search_embedding_hyde_service import search_chunks_with_hyde
from app.rag.query.search_embedding_service import (
    build_milvus_filter_expr,
    search_chunks,
)
from app.rag.query.rerank_service import rerank_documents
from app.rag.query.rrf_service import fuse_retrieval_results
from app.rag.query.web_search_service import search_web_documents


class RetrievalModeTests(unittest.TestCase):
    def test_presets_match_contract_and_balanced_baseline(self) -> None:
        balanced = resolve_retrieval_config("balanced")
        self.assertEqual(balanced.ann_limit, config.SEARCH_ANN_LIMIT)
        self.assertEqual(balanced.search_top_k, config.SEARCH_TOP_K)
        self.assertEqual(balanced.rrf_top_k, config.RRF_TOP_K)
        self.assertEqual(balanced.rerank_max_topk, config.RERANK_MAX_TOPK)
        self.assertTrue(balanced.hyde_enabled)
        self.assertTrue(balanced.web_enabled)
        self.assertEqual(
            balanced.snapshot(),
            {
                "mode": "balanced", "ann_limit": 20, "search_top_k": 10,
                "dense_weight": 0.6, "sparse_weight": 0.4,
                "hyde_enabled": True, "web_enabled": True, "web_top_k": 5,
                "rrf_k": 60, "rrf_embedding_weight": 1.0,
                "rrf_hyde_weight": 0.8, "rrf_top_k": 12,
                "rerank_min_topk": 2, "rerank_max_topk": 6,
                "rerank_gap_ratio": 0.2, "rerank_gap_abs": 0.2,
                "rerank_max_per_document": 2,
                "answer_max_context_chars": 20_000,
            },
        )

        precision = resolve_retrieval_config("precision")
        self.assertEqual(
            (precision.ann_limit, precision.search_top_k,
             precision.rrf_k, precision.rrf_top_k),
            (12, 6, 40, 8),
        )
        self.assertEqual(
            (precision.rerank_min_topk, precision.rerank_max_topk), (1, 3)
        )
        self.assertFalse(precision.web_enabled)

        recall = resolve_retrieval_config("recall")
        self.assertEqual(
            (recall.ann_limit, recall.search_top_k, recall.rrf_top_k),
            (40, 20, 24),
        )
        self.assertEqual(
            (recall.rerank_min_topk, recall.rerank_max_topk), (6, 12)
        )
        self.assertEqual(recall.answer_max_context_chars, 30_000)

    def test_custom_mapping_and_request_validation(self) -> None:
        options = {
            "candidate_top_k": 25,
            "max_reference_count": 12,
            "matching_preference": "semantic",
            "hyde_enabled": False,
            "hyde_influence": "high",
            "web_enabled": False,
        }
        custom = resolve_retrieval_config("custom", options)
        self.assertEqual(custom.ann_limit, 50)
        self.assertEqual(custom.rrf_top_k, 30)
        self.assertEqual((custom.dense_weight, custom.sparse_weight), (0.8, 0.2))
        self.assertFalse(custom.hyde_enabled)
        self.assertEqual(custom.answer_max_context_chars, 30_000)

        decoupled_options = {key: value for key, value in options.items()
                             if key != "web_enabled"}
        decoupled = resolve_retrieval_config("custom", decoupled_options)
        self.assertTrue(decoupled.web_enabled)
        request = QueryRequest.model_validate({
            "query": "问题", "retrieval_mode": "custom",
            "retrieval_options": decoupled_options, "web_enabled": False,
        })
        self.assertFalse(request.web_enabled)

        with self.assertRaises(ValidationError):
            QueryRequest.model_validate({
                "query": "问题", "retrieval_mode": "custom"
            })
        with self.assertRaises(ValidationError):
            QueryRequest.model_validate({
                "query": "问题", "retrieval_mode": "custom",
                "retrieval_options": {
                    **options, "candidate_top_k": "25",
                },
            })

    def test_custom_resolver_rejects_unvalidated_cli_or_history_values(self) -> None:
        valid = {
            "candidate_top_k": 10, "max_reference_count": 6,
            "matching_preference": "balanced", "hyde_enabled": True,
            "hyde_influence": "medium", "web_enabled": True,
        }
        invalid_values = (
            {**valid, "candidate_top_k": 0},
            {**valid, "max_reference_count": 0},
            {**valid, "hyde_enabled": "false"},
            {**valid, "web_enabled": 1},
            {**valid, "internal_timeout": 1},
        )
        for options in invalid_values:
            with self.subTest(options=options), self.assertRaises(ValueError):
                resolve_retrieval_config("custom", options)
        with self.assertRaises(ValidationError):
            QueryRequest.model_validate({
                "query": "问题", "retrieval_mode": "precision",
                "retrieval_options": options,
            })
        with self.assertRaises(ValidationError):
            QueryRequest.model_validate({
                "query": "问题", "query_scope": {"hard_fields": ["document_ids"]}
            })

    def test_request_configs_are_concurrently_isolated(self) -> None:
        before = (config.SEARCH_TOP_K, config.RRF_TOP_K, config.RERANK_MAX_TOPK)
        with ThreadPoolExecutor(max_workers=2) as executor:
            precision, recall = list(executor.map(
                resolve_retrieval_config, ("precision", "recall")
            ))
        self.assertEqual((precision.search_top_k, recall.search_top_k), (6, 20))
        self.assertEqual(
            before, (config.SEARCH_TOP_K, config.RRF_TOP_K, config.RERANK_MAX_TOPK)
        )
        self.assertEqual(get_effective_retrieval_config({}).mode, "balanced")
        with self.assertRaises((TypeError, ValueError)):
            get_effective_retrieval_config({
                "retrieval_config": {
                    **precision.snapshot(), "search_top_k": 99,
                }
            })

    def test_model_hard_fields_are_generated_from_normalized_strict_scope(self) -> None:
        result = normalize_query_understanding(
            {
                "rewritten_query": "问题", "strict": False,
                "file_titles": ["同名文件"], "region_names": ["北京市"],
                "hard_fields": ["file_titles", "region_names", "topics"],
            },
            "问题",
        )
        self.assertEqual(result["query_filters"]["hard_fields"], [])
        strict = normalize_query_understanding(
            {
                "rewritten_query": "问题", "strict": True,
                "file_titles": ["同名文件"], "region_names": ["北京市"],
                "document_types": ["政策"], "hard_fields": ["file_titles"],
            },
            "问题",
        )
        self.assertEqual(
            strict["query_filters"]["hard_fields"],
            ["region_names", "document_types"],
        )
        self.assertNotIn(
            "file_title in",
            build_milvus_filter_expr(strict["query_filters"]) or "",
        )

    def test_disabled_branches_do_not_call_external_dependencies(self) -> None:
        custom = resolve_retrieval_config("custom", {
            "candidate_top_k": 10, "max_reference_count": 6,
            "matching_preference": "balanced", "hyde_enabled": False,
            "hyde_influence": "medium", "web_enabled": False,
        })
        state = {
            "rewritten_query": "测试问题", "query_filters": {},
            "retrieval_config": custom,
        }
        with patch(
            "app.rag.query.search_embedding_hyde_service.generate_hyde_text"
        ) as generate:
            self.assertEqual(search_chunks_with_hyde(state)["hyde_status"], "disabled")
            generate.assert_not_called()
        with patch("app.rag.query.web_search_service.call_web_search_mcp") as call:
            self.assertEqual(search_web_documents(state)["web_status"], "disabled")
            call.assert_not_called()

    def test_retrieval_stages_read_request_config(self) -> None:
        from app.rag.query import search_embedding_service
        from app.rag.query import search_embedding_hyde_service
        from app.rag.query import web_search_service

        precision = resolve_retrieval_config("precision")
        state = {
            "rewritten_query": "测试问题", "query_filters": {},
            "retrieval_config": precision,
        }
        with patch.object(
            search_embedding_service,
            "embed_retrieval_query",
            return_value=([1.0], {1: 1.0}),
        ), patch.object(
            search_embedding_service, "search_chunks_by_milvus", return_value=[]
        ) as search:
            update = search_chunks(state)
        self.assertEqual(update["embedding_status"], "success")
        self.assertEqual(search.call_args.kwargs["ann_limit"], 12)
        self.assertEqual(search.call_args.kwargs["top_k"], 6)

        recall = resolve_retrieval_config("recall")
        hyde_state = {**state, "retrieval_config": recall}
        with patch.object(
            search_embedding_hyde_service, "generate_hyde_text", return_value="假设"
        ), patch.object(
            search_embedding_hyde_service,
            "embed_retrieval_query",
            return_value=([1.0], {1: 1.0}),
        ), patch.object(
            search_embedding_hyde_service,
            "search_chunks_by_milvus",
            return_value=[],
        ) as hyde_search:
            update = search_chunks_with_hyde(hyde_state)
        self.assertEqual(update["hyde_status"], "success")
        self.assertEqual(hyde_search.call_args.kwargs["ann_limit"], 40)
        self.assertEqual(hyde_search.call_args.kwargs["top_k"], 20)

        call_web = Mock(return_value="pending")
        with patch.object(web_search_service, "call_web_search_mcp", call_web), patch.object(
            web_search_service, "_run_coroutine", return_value="raw"
        ), patch.object(
            web_search_service, "parse_web_search_response", return_value=[]
        ) as parse:
            update = search_web_documents(hyde_state)
        self.assertEqual(update["web_status"], "success")
        self.assertEqual(call_web.call_args.args[1], 8)
        parse.assert_called_once_with("raw", 8)

    def test_rrf_rerank_and_answer_use_request_limits(self) -> None:
        from app.rag.query import answer_output_service
        from app.rag.query import rerank_service

        precision = resolve_retrieval_config("precision")
        chunks = [
            {
                "chunk_id": f"chunk-{index}", "content": str(index),
                "file_title": "文件", "retrieval_source": "embedding",
            }
            for index in range(20)
        ]
        fused = fuse_retrieval_results({
            "embedding_chunks": chunks, "hyde_embedding_chunks": [],
            "retrieval_config": precision,
        })["rrf_chunks"]
        self.assertEqual(len(fused), 8)
        self.assertAlmostEqual(fused[0]["score"], 1.0 / 41.0)

        recall = resolve_retrieval_config("recall")
        candidates = [
            {**item, "source": "milvus", "document_id": f"doc-{index}"}
            for index, item in enumerate(chunks[:15])
        ]
        with patch.object(
            rerank_service, "create_rerank_pairs", side_effect=RuntimeError("fail")
        ):
            update = rerank_documents({
                "rewritten_query": "问题", "rrf_chunks": candidates,
                "web_search_docs": [], "query_filters": {},
                "retrieval_config": recall,
            })
        self.assertEqual(update["reranker_status"], "failed")
        self.assertEqual(len(update["reranked_docs"]), 12)

        answer_state = {
            "session_id": "answer-config", "original_query": "问题",
            "rewritten_query": "问题", "reranked_docs": candidates[:1],
            "retrieval_config": precision, "eval_disable_history": True,
            "history": [], "query_filters": {},
        }
        with patch.object(
            answer_output_service,
            "_build_evidence_context_details",
            return_value=("证据", candidates[:1]),
        ) as build_context, patch.object(
            answer_output_service, "load_answer_prompt", return_value="提示"
        ), patch.object(
            answer_output_service, "generate_answer_by_llm", return_value="回答"
        ):
            answer_output_service.produce_answer(answer_state)
        build_context.assert_called_once_with(candidates[:1], 12_000)

        budget_config = resolve_retrieval_config("custom", {
            "candidate_top_k": 5, "max_reference_count": 2,
            "matching_preference": "balanced", "hyde_enabled": False,
            "hyde_influence": "low", "web_enabled": False,
        })
        long_documents = [
            {**candidates[0], "chunk_id": f"long-{index}", "content": "水" * 3000}
            for index in range(2)
        ]
        with patch.object(
            answer_output_service, "load_answer_prompt", return_value="提示"
        ), patch.object(
            answer_output_service, "generate_answer_by_llm", return_value="回答"
        ):
            update = answer_output_service.produce_answer({
                **answer_state, "retrieval_config": budget_config,
                "reranked_docs": long_documents,
            })
        self.assertEqual(len(update["answer_context_docs"]), 1)
        self.assertEqual(
            update["retrieval_metadata"]["counts"]["final_context"], 1
        )

    def test_public_metadata_only_reports_actual_failures(self) -> None:
        metadata = build_retrieval_metadata({
            "retrieval_config": resolve_retrieval_config("precision"),
            "embedding_status": "success", "hyde_status": "disabled",
            "web_status": "disabled", "reranker_status": "failed",
        })
        self.assertEqual(metadata["degradations"], ["reranker_failed"])
        self.assertEqual(metadata["counts"]["final_context"], 0)

    def test_public_metadata_does_not_expose_removed_scope(self) -> None:
        metadata = build_retrieval_metadata({
            "retrieval_config": resolve_retrieval_config(),
            "query_filters": {
                "region_names": ["北京市"], "document_types": ["政策"],
                "topics": ["再生水"], "keywords": ["管理"], "strict": True,
            },
        })
        self.assertNotIn("scope", metadata)

    def test_parallel_graph_disabled_branches_merge_once(self) -> None:
        from app.process.query.agent import main_graph
        from app.process.query.agent.nodes import node_answer_output
        from app.process.query.agent.nodes import node_item_name_confirm
        from app.process.query.agent.nodes import node_rerank
        from app.process.query.agent.nodes import node_rrf
        from app.process.query.agent.nodes import node_search_embedding

        disabled = resolve_retrieval_config("custom", {
            "candidate_top_k": 10, "max_reference_count": 6,
            "matching_preference": "balanced", "hyde_enabled": False,
            "hyde_influence": "medium", "web_enabled": False,
        })
        candidate = {
            "chunk_id": "chunk", "content": "内容", "file_title": "文件",
            "retrieval_source": "embedding", "source": "milvus",
        }
        with patch.object(
            node_item_name_confirm,
            "understand_query",
            return_value={
                "rewritten_query": "问题", "query_filters": {},
                "history": [], "answer": "",
            },
        ), patch.object(
            node_search_embedding,
            "search_chunks",
            return_value={
                "embedding_chunks": [candidate], "embedding_status": "success",
            },
        ), patch.object(
            node_rrf,
            "fuse_retrieval_results",
            wraps=fuse_retrieval_results,
        ) as fuse, patch.object(
            node_rerank,
            "rerank_documents",
            side_effect=lambda state: {
                "reranked_docs": state["rrf_chunks"],
                "reranker_status": "success",
            },
        ), patch.object(
            node_answer_output,
            "produce_answer",
            return_value={
                "answer": "完成", "image_urls": [], "prompt": "",
                "retrieval_metadata": {},
            },
        ):
            state = main_graph.query_app.invoke({
                "session_id": "parallel-disabled", "original_query": "问题",
                "is_stream": False, "retrieval_config": disabled,
            })
        self.assertEqual(fuse.call_count, 1)
        self.assertEqual(state["hyde_status"], "disabled")
        self.assertEqual(state["web_status"], "disabled")
        self.assertEqual(state["answer"], "完成")

    def test_omitted_mode_is_balanced_and_web_can_be_overridden(self) -> None:
        from app.api.http import query_server

        request = QueryRequest.model_validate({"query": "继续追问"})
        prepared = query_server.prepare_query_request(request)
        self.assertEqual(prepared["retrieval_config"].mode, "balanced")

        explicit = QueryRequest.model_validate({
            "query": "本次均衡", "retrieval_mode": "balanced",
        })
        prepared = query_server.prepare_query_request(explicit)
        self.assertEqual(prepared["retrieval_config"].mode, "balanced")

        web_override = QueryRequest.model_validate({
            "query": "精确检索并联网", "retrieval_mode": "precision",
            "web_enabled": True,
        })
        prepared = query_server.prepare_query_request(web_override)
        self.assertTrue(prepared["retrieval_config"].web_enabled)
        self.assertEqual(prepared["retrieval_config"].web_top_k, 3)

    def test_history_no_longer_stores_retrieval_preference(self) -> None:
        from app.api.http import query_server
        from app.rag.query import item_name_confirm_service

        state = {
            "session_id": "session", "original_query": "问题",
            "retrieval_config": resolve_retrieval_config("precision"),
        }
        update = {"rewritten_query": "问题", "query_filters": {}}
        with patch.object(
            item_name_confirm_service.history_repository, "save_message"
        ) as save:
            save_user_query_history(state, update)
        self.assertNotIn("retrieval_preference", save.call_args.kwargs)

        with patch.object(
            query_server.history_repository,
            "list_recent",
            return_value=[{
                "session_id": "session", "role": "assistant", "text": "旧回答",
                "item_names": None, "query_filters": None, "image_urls": None,
            }],
        ):
            history = query_server.build_history_response("session")
        self.assertEqual(history.items[0].text, "旧回答")
        self.assertIsNone(history.items[0].retrieval_metadata)

    def test_stream_and_non_stream_use_identical_final_metadata(self) -> None:
        from app.api.http import query_server

        state = {
            "session_id": "same-metadata", "answer": "回答",
            "image_urls": [], "retrieval_config": resolve_retrieval_config("recall"),
            "embedding_chunks": [{}], "hyde_embedding_chunks": [],
            "rrf_chunks": [{}], "web_search_docs": [],
            "reranked_docs": [{}, {}], "answer_context_docs": [{}],
            "embedding_status": "success", "hyde_status": "success",
            "web_status": "success", "reranker_status": "success",
        }
        state["retrieval_metadata"] = build_retrieval_metadata(state)
        with patch.object(
            query_server, "invoke_query", return_value=state
        ), patch.object(query_server, "get_task_result", return_value=""):
            response = query_server.execute_query(
                "问题", session_id="same-metadata"
            )
        pushed: list[tuple[str, str, dict]] = []
        with patch.object(
            query_server, "invoke_query", return_value=state
        ), patch.object(
            query_server, "get_task_result", return_value=""
        ), patch.object(
            query_server,
            "push_to_session",
            side_effect=lambda session, event, data: pushed.append(
                (session, event, data)
            ),
        ):
            query_server.run_stream_query_background(
                "same-metadata", "问题", {}
            )
        self.assertEqual(pushed[-1][1], "final")
        self.assertEqual(
            response.retrieval_metadata.model_dump(mode="json"),
            pushed[-1][2]["retrieval_metadata"],
        )


if __name__ == "__main__":
    unittest.main()
