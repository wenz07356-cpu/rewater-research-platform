"""LangGraph 查询流程状态定义。"""

import copy
from typing import Any

from typing_extensions import TypedDict

from app.rag.query.config import default_query_filters
from app.rag.query.retrieval_config import (
    EffectiveRetrievalConfig,
    resolve_retrieval_config,
)


class QueryGraphState(TypedDict):
    """查询图全量状态；并行节点只返回自己负责的状态增量。"""

    session_id: str
    original_query: str
    rewritten_query: str
    query_filters: dict[str, Any]
    retrieval_config: EffectiveRetrievalConfig
    history: list[dict[str, Any]]
    embedding_chunks: list[dict[str, Any]]
    hyde_embedding_chunks: list[dict[str, Any]]
    web_search_docs: list[dict[str, Any]]
    rrf_chunks: list[dict[str, Any]]
    reranked_docs: list[dict[str, Any]]
    answer_context_docs: list[dict[str, Any]]
    prompt: str
    answer: str
    is_stream: bool
    image_urls: list[str]
    retrieval_metadata: dict[str, Any]
    embedding_status: str
    hyde_status: str
    web_status: str
    reranker_status: str
    # 评估调用的局部副作用开关；生产入口默认均为 False。
    eval_disable_history: bool
    eval_disable_web: bool
    # 只用于读取旧历史和旧调用方兼容，不参与新版查询业务。
    item_names: list[str]


def _build_default_state() -> QueryGraphState:
    """构造一份全新的默认状态。"""
    return {
        "session_id": "",
        "original_query": "",
        "rewritten_query": "",
        "query_filters": default_query_filters(),
        "retrieval_config": resolve_retrieval_config(),
        "history": [],
        "embedding_chunks": [],
        "hyde_embedding_chunks": [],
        "web_search_docs": [],
        "rrf_chunks": [],
        "reranked_docs": [],
        "answer_context_docs": [],
        "prompt": "",
        "answer": "",
        "is_stream": False,
        "image_urls": [],
        "retrieval_metadata": {},
        "embedding_status": "pending",
        "hyde_status": "pending",
        "web_status": "pending",
        "reranker_status": "pending",
        "eval_disable_history": False,
        "eval_disable_web": False,
        "item_names": [],
    }


query_graph_default_state: QueryGraphState = _build_default_state()


def create_query_default_state(**overrides: Any) -> QueryGraphState:
    """创建默认查询状态，并使用调用方字段覆盖默认值。"""
    state = _build_default_state()
    state.update(overrides)
    return state


def get_query_default_state() -> QueryGraphState:
    """返回默认查询状态的深拷贝。"""
    return copy.deepcopy(query_graph_default_state)


def copy_query_state(
    state: QueryGraphState,
    **overrides: Any,
) -> QueryGraphState:
    """深拷贝现有状态并应用字段覆盖，不污染原对象。"""
    new_state = copy.deepcopy(state)
    new_state.update(overrides)
    return new_state
