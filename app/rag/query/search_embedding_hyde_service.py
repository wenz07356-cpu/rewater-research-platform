"""HyDE 增强混合检索服务。"""

from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser

from app.infra.llm.providers import llm_provider
from app.process.query.agent.state import QueryGraphState
from app.rag.query.config import HYDE_MAX_CHARS
from app.rag.query.search_embedding_service import (
    build_milvus_filter_expr,
    build_retrieval_query,
    embed_retrieval_query,
    normalize_local_candidates,
    search_chunks_by_milvus,
    validate_retrieval_state,
)
from app.shared.runtime.load_prompt import load_prompt
from app.shared.runtime.logger import logger, step_log


def build_query_scope_text(query_filters: dict[str, Any]) -> str:
    """将查询范围转换为简短的 HyDE Prompt 文本。"""
    labels = (
        ("file_titles", "文件"),
        ("region_names", "地域"),
        ("document_types", "文档类型"),
        ("topics", "主题"),
    )
    parts = [
        f"{label}：{'、'.join(query_filters.get(field, []))}"
        for field, label in labels
        if query_filters.get(field)
    ]
    return "；".join(parts) or "无额外范围限制"


@step_log("generate_hyde_text")
def generate_hyde_text(
    rewritten_query: str,
    scope_text: str,
) -> str:
    """调用大模型生成只用于召回的 HyDE 文本。"""
    prompt = load_prompt(
        "hyde_prompt",
        rewritten_query=rewritten_query,
        query_scope=scope_text,
        max_chars=HYDE_MAX_CHARS,
    )
    chain = llm_provider.chat() | StrOutputParser()
    text = str(chain.invoke([HumanMessage(content=prompt)]) or "").strip()
    if len(text) > HYDE_MAX_CHARS:
        text = text[:HYDE_MAX_CHARS]
    return text


def build_hyde_retrieval_query(
    rewritten_query: str,
    hyde_text: str,
    query_filters: dict[str, Any],
) -> str:
    """组合原问题、HyDE 表述和软 metadata，避免假设文本替代用户意图。"""
    base_query = build_retrieval_query(rewritten_query, query_filters)
    return f"{base_query}\n相关文档可能表述：{hyde_text}"


@step_log("search_chunks_with_hyde")
def search_chunks_with_hyde(
    state: QueryGraphState,
) -> dict[str, list[dict[str, Any]]]:
    """执行 HyDE 生成与增强混合检索。

    输入：查询图状态。
    输出：hyde_embedding_chunks 状态增量。
    步骤：校验、生成 HyDE、向量化、复用普通 Milvus 检索和候选映射。
    """
    rewritten_query, filters = validate_retrieval_state(state)
    try:
        scope_text = build_query_scope_text(filters)
        hyde_text = generate_hyde_text(rewritten_query, scope_text)
        if not hyde_text:
            logger.warning("HyDE 模型返回空文本，本分支降级为空结果")
            return {"hyde_embedding_chunks": []}
        retrieval_query = build_hyde_retrieval_query(
            rewritten_query, hyde_text, filters
        )
        dense, sparse = embed_retrieval_query(retrieval_query)
        filter_expr = build_milvus_filter_expr(filters)
        hits = search_chunks_by_milvus(dense, sparse, filter_expr)
        candidates = normalize_local_candidates(hits, "hyde")
        logger.info(
            f"HyDE 混合检索完成：filtered={bool(filter_expr)}, "
            f"hits={len(candidates)}"
        )
        return {"hyde_embedding_chunks": candidates}
    except Exception as exc:
        logger.exception(f"HyDE 检索失败，降级为空结果：error={exc}")
        return {"hyde_embedding_chunks": []}


# 旧节点调用方兼容。
search_by_hyde = search_chunks_with_hyde
