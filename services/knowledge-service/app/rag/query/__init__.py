"""Query RAG 领域服务公共入口。

公共符号使用惰性加载，避免 state -> config -> package __init__ -> service -> state
形成循环导入。
"""

from importlib import import_module
from typing import Any

_EXPORTS = {
    "confirm_item_name": (
        "app.rag.query.item_name_confirm_service",
        "confirm_item_name",
    ),
    "understand_query": (
        "app.rag.query.item_name_confirm_service",
        "understand_query",
    ),
    "fuse_retrieval_results": (
        "app.rag.query.rrf_service",
        "fuse_retrieval_results",
    ),
    "produce_answer": (
        "app.rag.query.answer_output_service",
        "produce_answer",
    ),
    "rerank_documents": (
        "app.rag.query.rerank_service",
        "rerank_documents",
    ),
    "search_chunks": (
        "app.rag.query.search_embedding_service",
        "search_chunks",
    ),
    "search_chunks_with_hyde": (
        "app.rag.query.search_embedding_hyde_service",
        "search_chunks_with_hyde",
    ),
    "search_web_documents": (
        "app.rag.query.web_search_service",
        "search_web_documents",
    ),
    "validate_retrieval_state": (
        "app.rag.query.search_embedding_service",
        "validate_retrieval_state",
    ),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    """按需导入公开 service，避免包初始化时加载整个查询依赖图。"""
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = target
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value
