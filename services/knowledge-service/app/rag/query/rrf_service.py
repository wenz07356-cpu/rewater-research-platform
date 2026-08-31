"""普通检索与 HyDE 检索的加权 RRF 融合服务。"""

import copy
from typing import Any

from app.process.query.agent.state import QueryGraphState
from app.rag.query.config import (
    RRF_EMBEDDING_WEIGHT,
    RRF_HYDE_WEIGHT,
    RRF_K,
    RRF_TOP_K,
)
from app.rag.query.retrieval_config import get_effective_retrieval_config
from app.shared.runtime.logger import logger, step_log


def validate_rrf_inputs(
    state: QueryGraphState,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """读取两路本地候选；允许空列表，但拒绝错误状态类型。"""
    embedding = state.get("embedding_chunks") or []
    hyde = state.get("hyde_embedding_chunks") or []
    if not isinstance(embedding, list) or not isinstance(hyde, list):
        logger.error("RRF 输入必须为列表")
        raise TypeError("embedding_chunks 和 hyde_embedding_chunks 必须为列表")
    return embedding, hyde


def reciprocal_rank_fusion(
    ranked_sources: list[tuple[float, list[dict[str, Any]]]],
    k: int = RRF_K,
    limit: int = RRF_TOP_K,
) -> list[dict[str, Any]]:
    """按 chunk_id 去重并计算 weight/(k+rank) 累积分数。"""
    scores: dict[str, float] = {}
    chunks: dict[str, dict[str, Any]] = {}
    sources: dict[str, list[str]] = {}
    retrieval_scores: dict[str, dict[str, float]] = {}
    for weight, candidates in ranked_sources:
        for rank, candidate in enumerate(candidates, start=1):
            chunk_id = str(candidate.get("chunk_id") or "").strip()
            if not chunk_id:
                logger.warning("RRF 跳过缺少 chunk_id 的本地候选")
                continue
            scores[chunk_id] = scores.get(chunk_id, 0.0) + weight / (k + rank)
            chunks.setdefault(chunk_id, copy.deepcopy(candidate))
            source = str(candidate.get("retrieval_source") or "unknown")
            sources.setdefault(chunk_id, [])
            if source not in sources[chunk_id]:
                sources[chunk_id].append(source)
            retrieval_scores.setdefault(chunk_id, {})[source] = float(
                candidate.get("score") or 0.0
            )

    result: list[dict[str, Any]] = []
    for chunk_id, score in scores.items():
        candidate = chunks[chunk_id]
        candidate["score"] = score
        candidate["retrieval_sources"] = sources[chunk_id]
        candidate["retrieval_scores"] = retrieval_scores[chunk_id]
        result.append(candidate)
    result.sort(key=lambda item: item.get("score", 0.0), reverse=True)
    return result[:limit]


@step_log("fuse_retrieval_results")
def fuse_retrieval_results(
    state: QueryGraphState,
) -> dict[str, list[dict[str, Any]]]:
    """融合两路本地结果。

    输入：包含 embedding_chunks/hyde_embedding_chunks 的查询状态。
    输出：仅包含 rrf_chunks 的状态增量。
    步骤：校验列表类型，按配置权重执行 RRF；任一路为空仍使用另一条，
    两路均空时返回空列表。
    """
    embedding, hyde = validate_rrf_inputs(state)
    retrieval_config = get_effective_retrieval_config(state)
    result = reciprocal_rank_fusion(
        [
            (retrieval_config.rrf_embedding_weight, embedding),
            (retrieval_config.rrf_hyde_weight, hyde),
        ],
        k=retrieval_config.rrf_k,
        limit=retrieval_config.rrf_top_k,
    )
    if not embedding and not hyde:
        logger.warning("普通检索与 HyDE 均无结果，RRF 返回空列表")
    logger.info(
        f"RRF 完成：embedding={len(embedding)}, hyde={len(hyde)}, "
        f"fused={len(result)}"
    )
    return {"rrf_chunks": result}


fuse_by_rrf = fuse_retrieval_results
