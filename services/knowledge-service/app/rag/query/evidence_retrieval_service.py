"""面向 DeepAgent 的最小内部知识库证据检索编排。"""

import math
from collections.abc import Mapping
from typing import Any

from app.api.schemas.query import RetrievalChunk
from app.process.query.agent.state import create_query_default_state
from app.rag.query.item_name_confirm_service import understand_query
from app.rag.query.rerank_service import rerank_documents
from app.rag.query.retrieval_config import resolve_retrieval_config
from app.rag.query.rrf_service import fuse_retrieval_results
from app.rag.query.search_embedding_hyde_service import search_chunks_with_hyde
from app.rag.query.search_embedding_service import search_chunks


def retrieve_evidence(query: str, request_id: str) -> dict[str, Any]:
    """顺序执行内部知识库检索，并在 Reranker 后结束。"""
    state = create_query_default_state(
        session_id=request_id,
        original_query=query,
        is_stream=False,
        eval_disable_history=True,
        eval_disable_web=True,
        retrieval_config=resolve_retrieval_config("balanced"),
    )

    state.update(understand_query(state))
    if state.get("answer"):
        return state

    state.update(search_chunks(state))
    state.update(search_chunks_with_hyde(state))
    state.update(fuse_retrieval_results(state))
    state.update(rerank_documents(state))
    return state


def _required_text(value: Any) -> str:
    """将必填标识字段转换为非空字符串。"""
    return str(value or "").strip()


def build_retrieval_chunks(
    reranked_docs: list[dict[str, Any]],
    top_k: int,
) -> list[RetrievalChunk]:
    """将精排结果映射为稳定的公开证据字段，并保持原有顺序。"""
    if not isinstance(reranked_docs, list):
        raise TypeError("reranked_docs 必须为列表")
    if type(top_k) is not int or not 1 <= top_k <= 6:
        raise ValueError("top_k 必须是 1～6 的整数")

    chunks: list[RetrievalChunk] = []
    for document in reranked_docs:
        if not isinstance(document, Mapping):
            continue
        chunk_id = _required_text(document.get("chunk_id"))
        document_id = _required_text(document.get("document_id"))
        document_name = _required_text(document.get("file_title"))
        content = document.get("content")
        if not chunk_id or not document_id or not document_name:
            continue
        if not isinstance(content, str) or not content.strip():
            continue

        raw_score = document.get("rerank_score")
        if raw_score is None:
            raw_score = document.get("score")
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(score):
            continue

        chunks.append(
            RetrievalChunk(
                chunk_id=chunk_id,
                document_id=document_id,
                document_name=document_name,
                section_title=_required_text(document.get("section_title")),
                content=content,
                score=score,
            )
        )
        if len(chunks) >= top_k:
            break
    return chunks
