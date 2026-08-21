"""本地与 Web 候选的 BGE Reranker 精排服务。"""

import copy
import hashlib
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser

from app.infra.llm.providers import llm_provider
from app.process.query.agent.state import QueryGraphState
from app.rag.query.config import (
    RERANK_GAP_ABS,
    RERANK_GAP_RATIO,
    RERANK_MAX_INPUT_TOKENS,
    RERANK_MAX_PER_DOCUMENT,
    RERANK_MAX_TOPK,
    RERANK_MIN_SUMMARY_CHARS,
    RERANK_MIN_TOPK,
    RERANK_SUMMARY_CHAR_RATIO,
)
from app.shared.runtime.load_prompt import load_prompt
from app.shared.runtime.logger import logger, step_log
from app.rag.query.retrieval_config import get_effective_retrieval_config


def validate_rerank_inputs(
    state: QueryGraphState,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """校验精排问题和两类候选，允许任一或两者为空。"""
    query = str(state.get("rewritten_query") or "").strip()
    local_docs = state.get("rrf_chunks") or []
    web_docs = state.get("web_search_docs") or []
    if not query:
        raise ValueError("rewritten_query 不能为空")
    if not isinstance(local_docs, list) or not isinstance(web_docs, list):
        raise TypeError("rrf_chunks 和 web_search_docs 必须为列表")
    return query, local_docs, web_docs


def merge_rerank_candidates(
    rrf_chunks: list[dict[str, Any]],
    web_search_docs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """复制、统一并去重本地和 Web 候选，不修改上游列表。"""
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in [*rrf_chunks, *web_search_docs]:
        source = candidate.get("source") or "milvus"
        if source == "web":
            raw_key = candidate.get("url") or (
                f"{candidate.get('display_title')}\n{candidate.get('content')}"
            )
            candidate_id = "web:" + hashlib.sha256(
                str(raw_key).encode("utf-8")
            ).hexdigest()
        else:
            candidate_id = str(candidate.get("chunk_id") or "")
        if not candidate_id or candidate_id in seen:
            continue
        seen.add(candidate_id)
        item = copy.deepcopy(candidate)
        item["candidate_id"] = candidate_id
        item["rerank_score"] = 0.0
        result.append(item)
    return result


def build_rerank_text(candidate: dict[str, Any]) -> str:
    """使用展示标题和正文构造来源一致的 Reranker 评分文本。"""
    parts = [
        str(candidate.get("display_title") or "").strip(),
        str(candidate.get("content") or "").strip(),
    ]
    return "\n".join(part for part in parts if part)


def fit_rerank_text(
    question: str,
    candidate: dict[str, Any],
    tokenizer: Any,
) -> str:
    """将评分副本控制在模型 token 上限内，原始 content 保持不变。"""
    text = build_rerank_text(candidate)
    question_tokens = tokenizer.encode(question, add_special_tokens=False)
    text_tokens = tokenizer.encode(text, add_special_tokens=False)
    available = max(1, RERANK_MAX_INPUT_TOKENS - len(question_tokens) - 4)
    if len(text_tokens) <= available:
        return text

    if candidate.get("context_type") in {"table", "code"}:
        return tokenizer.decode(text_tokens[:available], skip_special_tokens=True)

    limit = max(
        RERANK_MIN_SUMMARY_CHARS,
        int(available / RERANK_SUMMARY_CHAR_RATIO),
    )
    prompt = load_prompt(
        "rerank_text_refine",
        question=question,
        answer=text,
        limit=limit,
    )
    try:
        chain = llm_provider.chat() | StrOutputParser()
        refined = str(
            chain.invoke([HumanMessage(content=prompt)]) or ""
        ).strip()
    except Exception as exc:
        logger.warning(
            f"超长文本精简失败，改用确定性 token 截取：error={exc}"
        )
        return tokenizer.decode(
            text_tokens[:available], skip_special_tokens=True
        )
    refined_tokens = tokenizer.encode(refined, add_special_tokens=False)
    if len(refined_tokens) > available:
        refined = tokenizer.decode(
            refined_tokens[:available], skip_special_tokens=True
        )
    return refined


def create_rerank_pairs(
    rewritten_query: str,
    candidates: list[dict[str, Any]],
) -> list[list[str]]:
    """按候选顺序构建问题—评分文本对。"""
    tokenizer = llm_provider.reranker_model().tokenizer
    return [
        [rewritten_query, fit_rerank_text(rewritten_query, item, tokenizer)]
        for item in candidates
    ]


def score_and_sort_candidates(
    pairs: list[list[str]],
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """批量计算归一化分数并稳定降序排列。"""
    if len(pairs) != len(candidates):
        raise ValueError("Reranker 评分对与候选数量不一致")
    if not pairs:
        return []
    scores = llm_provider.reranker_model().compute_score(pairs, normalize=True)
    if isinstance(scores, (int, float)):
        scores = [scores]
    if len(scores) != len(candidates):
        raise ValueError("Reranker 返回分数数量异常")
    for score, candidate in zip(scores, candidates):
        value = float(score)
        candidate["rerank_score"] = value
        candidate["score"] = value
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates


def select_dynamic_top_k(
    candidates: list[dict[str, Any]],
    *,
    strict_single_file: bool = False,
    min_topk: int = RERANK_MIN_TOPK,
    max_topk: int = RERANK_MAX_TOPK,
    gap_ratio: float = RERANK_GAP_RATIO,
    gap_abs: float = RERANK_GAP_ABS,
    max_per_document: int = RERANK_MAX_PER_DOCUMENT,
) -> list[dict[str, Any]]:
    """根据分数断崖选取 2～6 条，并按需控制同文档数量。"""
    if not candidates:
        return []
    max_count = min(max_topk, len(candidates))
    top_k = max_count
    if max_count > min_topk:
        for index in range(min_topk - 1, max_count - 1):
            current = float(candidates[index].get("score") or 0.0)
            following = float(candidates[index + 1].get("score") or 0.0)
            absolute_gap = current - following
            relative_gap = absolute_gap / current if current > 0 else 0.0
            if absolute_gap >= gap_abs or relative_gap >= gap_ratio:
                top_k = index + 1
                break
    selected = candidates[:top_k]
    if strict_single_file:
        return selected

    diversified: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    # 从完整排名中补位，避免前几条都来自同一文档时最终结果过少。
    for candidate in candidates:
        if len(diversified) >= top_k:
            break
        document_id = str(
            candidate.get("document_id")
            or candidate.get("candidate_id")
            or ""
        )
        if counts.get(document_id, 0) >= max_per_document:
            continue
        counts[document_id] = counts.get(document_id, 0) + 1
        diversified.append(candidate)
    return diversified


@step_log("rerank_documents")
def rerank_documents(
    state: QueryGraphState,
) -> dict[str, Any]:
    """统一精排本地与 Web 候选。

    输入：包含 rewritten_query/rrf_chunks/web_search_docs/query_filters 的状态。
    输出：仅包含 reranked_docs 的状态增量。
    步骤：合并去重、构建评分对、模型打分、动态截断和来源多样性控制；
    模型异常时按上游顺序降级。
    """
    query, local_docs, web_docs = validate_rerank_inputs(state)
    retrieval_config = get_effective_retrieval_config(state)
    candidates = merge_rerank_candidates(local_docs, web_docs)
    if not candidates:
        logger.warning("本地和 Web 均无候选，Reranker 返回空列表")
        return {"reranked_docs": [], "reranker_status": "success"}
    try:
        pairs = create_rerank_pairs(query, candidates)
        ranked = score_and_sort_candidates(pairs, candidates)
        selected = select_dynamic_top_k(
            ranked,
            strict_single_file=False,
            min_topk=retrieval_config.rerank_min_topk,
            max_topk=retrieval_config.rerank_max_topk,
            gap_ratio=retrieval_config.rerank_gap_ratio,
            gap_abs=retrieval_config.rerank_gap_abs,
            max_per_document=retrieval_config.rerank_max_per_document,
        )
        status = "success"
    except Exception as exc:
        logger.exception(
            f"Reranker 执行失败，按上游顺序降级：error={exc}"
        )
        selected = candidates[:retrieval_config.rerank_max_topk]
        status = "failed"
    logger.info(
        f"Reranker 完成：local={len(local_docs)}, web={len(web_docs)}, "
        f"candidates={len(candidates)}, selected={len(selected)}"
    )
    return {"reranked_docs": selected, "reranker_status": status}
