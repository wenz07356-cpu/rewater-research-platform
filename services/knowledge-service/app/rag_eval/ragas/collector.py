"""调用真实查询图并采集答案、上下文和四层 chunk ID。"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
from typing import Any

from .dataset import GoldCase

LAYER_FIELDS = {
    "embedding": "embedding_chunks",
    "hyde": "hyde_embedding_chunks",
    "rrf": "rrf_chunks",
    "rerank": "reranked_docs",
}


@dataclass(frozen=True)
class QueryTrace:
    response: str
    retrieved_contexts: tuple[str, ...]
    layer_ids: dict[str, list[str]]
    state: dict[str, Any]


def _ordered_chunk_ids(documents: object, *, layer: str) -> list[str]:
    if not isinstance(documents, list):
        raise TypeError(f"{LAYER_FIELDS[layer]} 必须为列表")
    result: list[str] = []
    for index, document in enumerate(documents):
        if not isinstance(document, dict):
            raise TypeError(f"{LAYER_FIELDS[layer]}[{index}] 必须为对象")
        chunk_id = str(document.get("chunk_id") or "").strip()
        if not chunk_id:
            if document.get("source") == "web":
                continue
            raise ValueError(f"{LAYER_FIELDS[layer]}[{index}] 缺少 chunk_id")
        if chunk_id not in result:
            result.append(chunk_id)
    return result


def collect_query(
    case: GoldCase,
    *,
    run_id: str,
    graph_app: Any | None = None,
    web_enabled: bool = False,
    retrieval_mode: str = "balanced",
    retrieval_options: dict[str, Any] | None = None,
) -> QueryTrace:
    """以无历史、默认无 Web 的评估状态执行一次真实查询。"""
    if graph_app is None:
        from app.process.query.agent.main_graph import query_app
        graph_app = query_app
    from app.process.query.agent.state import create_query_default_state
    from app.rag.query.retrieval_config import resolve_retrieval_config

    session_id = f"eval-{run_id}-{case.case_id}"
    retrieval_config = resolve_retrieval_config(
        retrieval_mode, retrieval_options
    )
    if web_enabled:
        retrieval_config = replace(retrieval_config, web_enabled=True)
    state = graph_app.invoke(create_query_default_state(
        session_id=session_id,
        original_query=case.user_input,
        is_stream=False,
        eval_disable_history=True,
        eval_disable_web=not web_enabled,
        retrieval_config=retrieval_config,
    ))
    if not isinstance(state, dict):
        raise TypeError("查询图最终状态必须为字典")
    response = str(state.get("answer") or "").strip()
    if not response:
        raise ValueError("查询图最终状态缺少 answer")
    reranked = state.get("answer_context_docs") or state.get("reranked_docs") or []
    if not isinstance(reranked, list):
        raise TypeError("reranked_docs 必须为列表")
    contexts: list[str] = []
    for index, document in enumerate(reranked):
        if not isinstance(document, dict):
            raise TypeError(f"reranked_docs[{index}] 必须为对象")
        content = str(document.get("content") or "").strip()
        if not content:
            raise ValueError(f"reranked_docs[{index}] 缺少 content")
        contexts.append(content)
    layer_ids = {
        name: _ordered_chunk_ids(state.get(field) or [], layer=name)
        for name, field in LAYER_FIELDS.items()
    }
    return QueryTrace(response, tuple(contexts), layer_ids, state)
