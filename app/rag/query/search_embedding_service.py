"""BGE-M3 + Milvus 普通混合检索服务。"""

import json
import re
from typing import Any

from app.infra.llm.providers import llm_provider
from app.infra.vector_store.milvus_gateway import milvus_gateway
from app.process.query.agent.state import QueryGraphState
from app.rag.query.config import (
    DENSE_WEIGHT,
    DOCUMENT_TYPES,
    HARD_FILTER_FIELDS,
    LOCAL_OUTPUT_FIELDS,
    QUERY_FILTER_MAX_VALUES,
    RETRIEVAL_QUERY_MAX_CHARS,
    SEARCH_ANN_LIMIT,
    SEARCH_TOP_K,
    SPARSE_WEIGHT,
    default_query_filters,
)
from app.rag.query.retrieval_config import get_effective_retrieval_config
from app.shared.runtime.logger import logger, step_log

_SPACE_RE = re.compile(r"\s+")


def _string_list(value: Any) -> list[str]:
    """规范化查询过滤中的字符串列表。"""
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = _SPACE_RE.sub(" ", str(item or "")).strip()
        if text and text not in result:
            result.append(text)
        if len(result) >= QUERY_FILTER_MAX_VALUES:
            break
    return result


def normalize_query_filters(value: Any) -> dict[str, Any]:
    """生成可被检索层安全使用的过滤结构。"""
    result = default_query_filters()
    if not isinstance(value, dict):
        return result
    for field in (
        "file_titles",
        "region_names",
        "document_types",
        "topics",
        "keywords",
    ):
        result[field] = _string_list(value.get(field))
    result["document_types"] = [
        item for item in result["document_types"] if item in DOCUMENT_TYPES
    ]
    result["hard_fields"] = [
        item
        for item in _string_list(value.get("hard_fields"))
        if item in HARD_FILTER_FIELDS and result.get(item)
    ]
    result["strict"] = bool(value.get("strict", False))
    return result


@step_log("validate_retrieval_state")
def validate_retrieval_state(
    state: QueryGraphState,
) -> tuple[str, dict[str, Any]]:
    """校验本地检索输入。

    输入：包含 rewritten_query 和可选 query_filters 的状态。
    输出：清洗后的问题和过滤结构。
    步骤：校验问题非空，再次规范化过滤字段，防止绕过入口节点。
    """
    rewritten_query = _SPACE_RE.sub(
        " ", str(state.get("rewritten_query") or "")
    ).strip()
    if not rewritten_query:
        logger.error("本地检索缺少 rewritten_query")
        raise ValueError("rewritten_query 不能为空")
    return rewritten_query, normalize_query_filters(state.get("query_filters"))


def build_retrieval_query(
    rewritten_query: str,
    query_filters: dict[str, Any],
) -> str:
    """将软 metadata 转换为简洁的向量检索文本。"""
    parts = [rewritten_query]
    labels = (
        ("file_titles", "文件"),
        ("region_names", "地域"),
        ("topics", "主题"),
        ("keywords", "关键词"),
    )
    for field, label in labels:
        values = [
            item
            for item in query_filters.get(field, [])
            if item not in rewritten_query
        ]
        if values:
            parts.append(f"{label}：{'、'.join(values)}")
    result = "\n".join(parts)
    if len(result) > RETRIEVAL_QUERY_MAX_CHARS:
        logger.warning("增强检索文本过长，仅保留改写问题")
        return rewritten_query[:RETRIEVAL_QUERY_MAX_CHARS]
    return result


def build_milvus_filter_expr(
    query_filters: dict[str, Any],
) -> str | None:
    """构造安全的 Milvus metadata 表达式。

    同字段多值使用 IN/ARRAY_CONTAINS_ANY，不同字段使用 AND。字符串通过
    JSON 序列化，禁止直接拼接原始用户字面量。
    """
    hard_fields = set(query_filters.get("hard_fields", []))
    expressions: list[str] = []
    if "document_types" in hard_fields:
        values = json.dumps(
            query_filters["document_types"], ensure_ascii=False
        )
        expressions.append(f"document_type in {values}")
    if "region_names" in hard_fields:
        regions = list(query_filters["region_names"])
        if not query_filters.get("strict") and "全国" not in regions:
            regions.append("全国")
        values = json.dumps(regions, ensure_ascii=False)
        expressions.append(f"ARRAY_CONTAINS_ANY(region_names, {values})")
    return " and ".join(expressions) or None


@step_log("embed_retrieval_query")
def embed_retrieval_query(
    retrieval_query: str,
) -> tuple[list[float], dict[int, float]]:
    """生成一条查询的稠密和稀疏 BGE-M3 向量。"""
    vectors = llm_provider.embed_documents([retrieval_query])
    dense = vectors.get("dense") or []
    sparse = vectors.get("sparse") or []
    if len(dense) != 1 or len(sparse) != 1:
        raise ValueError("BGE-M3 查询向量返回数量异常")
    if len(dense[0]) == 0 or len(sparse[0]) == 0:
        raise ValueError("BGE-M3 查询向量不能为空")
    return dense[0], sparse[0]


@step_log("search_chunks_by_milvus")
def search_chunks_by_milvus(
    dense_vector: list[float],
    sparse_vector: dict[int, float],
    filter_expr: str | None,
    *,
    ann_limit: int = SEARCH_ANN_LIMIT,
    top_k: int = SEARCH_TOP_K,
    dense_weight: float = DENSE_WEIGHT,
    sparse_weight: float = SPARSE_WEIGHT,
) -> list[Any]:
    """从当前配置的新版 chunks collection 执行混合检索。"""
    requests = milvus_gateway.create_requests(
        dense_vector=dense_vector,
        sparse_vector=sparse_vector,
        expr=filter_expr,
        limit=ann_limit,
    )
    result = milvus_gateway.hybrid_search(
        collection_name=milvus_gateway.chunks_collection,
        reqs=requests,
        ranker_weights=(dense_weight, sparse_weight),
        norm_score=True,
        limit=top_k,
        output_fields=LOCAL_OUTPUT_FIELDS,
    )
    if not result:
        return []
    return list(result[0] or [])


def build_display_title(file_title: str, section_title: str) -> str:
    """按统一展示规则生成文件/章节标题。"""
    file_title = str(file_title or "").strip()
    section_title = str(section_title or "").strip()
    if section_title and section_title != file_title:
        return f"{file_title} / {section_title}"
    return file_title


def normalize_local_candidates(
    milvus_hits: list[Any],
    retrieval_source: str,
) -> list[dict[str, Any]]:
    """将 Milvus 命中映射为 query 全链路统一候选。"""
    candidates: list[dict[str, Any]] = []
    for hit in milvus_hits:
        entity = hit.get("entity", {}) if hasattr(hit, "get") else {}
        chunk_id = str(entity.get("chunk_id") or "").strip()
        content = str(entity.get("content") or "").strip()
        file_title = str(entity.get("file_title") or "").strip()
        if not chunk_id or not content or not file_title:
            logger.warning(
                "跳过缺少 chunk_id/content/file_title 的 Milvus 命中"
            )
            continue
        section_title = str(entity.get("section_title") or "").strip()
        candidates.append(
            {
                "chunk_id": chunk_id,
                "document_id": entity.get("document_id"),
                "chunk_index": entity.get("chunk_index"),
                "file_title": file_title,
                "section_title": section_title,
                "display_title": build_display_title(
                    file_title, section_title
                ),
                "content": content,
                "context_type": entity.get("context_type") or "text",
                "region_names": entity.get("region_names") or [],
                "document_type": entity.get("document_type") or "其他",
                "topics": entity.get("topics") or [],
                "keywords": entity.get("keywords") or [],
                "token_count": entity.get("token_count") or 0,
                "score": float(hit.get("distance") or 0.0),
                "source": "milvus",
                "retrieval_source": retrieval_source,
                "url": "",
            }
        )
    return candidates


@step_log("search_chunks")
def search_chunks(state: QueryGraphState) -> dict[str, Any]:
    """执行普通混合检索。

    输入：包含 rewritten_query/query_filters 的查询状态。
    输出：仅包含 embedding_chunks 的状态增量。
    步骤：构造检索文本和过滤条件，生成双向量，查询 Milvus 并统一候选；
    外部检索异常时记录日志并返回空列表。
    """
    rewritten_query, filters = validate_retrieval_state(state)
    retrieval_config = get_effective_retrieval_config(state)
    try:
        retrieval_query = build_retrieval_query(rewritten_query, filters)
        filter_expr = build_milvus_filter_expr(filters)
        dense, sparse = embed_retrieval_query(retrieval_query)
        hits = search_chunks_by_milvus(
            dense, sparse, filter_expr,
            ann_limit=retrieval_config.ann_limit,
            top_k=retrieval_config.search_top_k,
            dense_weight=retrieval_config.dense_weight,
            sparse_weight=retrieval_config.sparse_weight,
        )
        candidates = normalize_local_candidates(hits, "embedding")
        logger.info(
            "普通混合检索完成："
            f"collection={milvus_gateway.chunks_collection}, "
            f"filtered={bool(filter_expr)}, hits={len(candidates)}"
        )
        return {"embedding_chunks": candidates, "embedding_status": "success"}
    except Exception as exc:
        logger.exception(f"普通混合检索失败，降级为空结果：error={exc}")
        return {"embedding_chunks": [], "embedding_status": "failed"}


# 旧节点调用方兼容。
search_by_embedding = search_chunks
