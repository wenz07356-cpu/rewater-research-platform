"""请求级检索模式解析与公开摘要。"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from app.rag.query import config


@dataclass(frozen=True, slots=True)
class EffectiveRetrievalConfig:
    """一次查询使用的完整、不可变检索配置。"""

    mode: str
    ann_limit: int
    search_top_k: int
    dense_weight: float
    sparse_weight: float
    hyde_enabled: bool
    web_enabled: bool
    web_top_k: int
    rrf_k: int
    rrf_embedding_weight: float
    rrf_hyde_weight: float
    rrf_top_k: int
    rerank_min_topk: int
    rerank_max_topk: int
    rerank_gap_ratio: float
    rerank_gap_abs: float
    rerank_max_per_document: int
    answer_max_context_chars: int

    def snapshot(self) -> dict[str, Any]:
        """返回适合审计和离线复现的普通字典副本。"""
        return asdict(self)


_PRESETS: dict[str, dict[str, Any]] = {
    "balanced": {
        "ann_limit": config.SEARCH_ANN_LIMIT,
        "search_top_k": config.SEARCH_TOP_K,
        "dense_weight": config.DENSE_WEIGHT,
        "sparse_weight": config.SPARSE_WEIGHT,
        "hyde_enabled": True,
        "web_enabled": True,
        "web_top_k": config.WEB_SEARCH_TOP_K,
        "rrf_k": config.RRF_K,
        "rrf_embedding_weight": config.RRF_EMBEDDING_WEIGHT,
        "rrf_hyde_weight": config.RRF_HYDE_WEIGHT,
        "rrf_top_k": config.RRF_TOP_K,
        "rerank_min_topk": config.RERANK_MIN_TOPK,
        "rerank_max_topk": config.RERANK_MAX_TOPK,
        "rerank_gap_ratio": config.RERANK_GAP_RATIO,
        "rerank_gap_abs": config.RERANK_GAP_ABS,
        "rerank_max_per_document": config.RERANK_MAX_PER_DOCUMENT,
        "answer_max_context_chars": config.ANSWER_MAX_CONTEXT_CHARS,
    },
    "precision": {
        "ann_limit": 12, "search_top_k": 6,
        "dense_weight": 0.6, "sparse_weight": 0.4,
        "hyde_enabled": True, "web_enabled": False, "web_top_k": 3,
        "rrf_k": 40, "rrf_embedding_weight": 1.0,
        "rrf_hyde_weight": 0.4, "rrf_top_k": 8,
        "rerank_min_topk": 1, "rerank_max_topk": 3,
        "rerank_gap_ratio": 0.10, "rerank_gap_abs": 0.10,
        "rerank_max_per_document": 2,
        "answer_max_context_chars": 12_000,
    },
    "recall": {
        "ann_limit": 40, "search_top_k": 20,
        "dense_weight": 0.6, "sparse_weight": 0.4,
        "hyde_enabled": True, "web_enabled": True, "web_top_k": 8,
        "rrf_k": 60, "rrf_embedding_weight": 1.0,
        "rrf_hyde_weight": 1.0, "rrf_top_k": 24,
        "rerank_min_topk": 6, "rerank_max_topk": 12,
        "rerank_gap_ratio": 0.35, "rerank_gap_abs": 0.35,
        "rerank_max_per_document": 3,
        "answer_max_context_chars": 30_000,
    },
}


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def _custom_values(options: Mapping[str, Any]) -> dict[str, Any]:
    required_fields = {
        "candidate_top_k", "max_reference_count", "matching_preference",
        "hyde_enabled", "hyde_influence",
    }
    allowed_fields = required_fields | {"web_enabled"}
    if not required_fields.issubset(options) or not set(options).issubset(allowed_fields):
        raise ValueError("retrieval_options 字段不完整或包含未开放字段")
    candidate_top_k = options["candidate_top_k"]
    max_references = options["max_reference_count"]
    if type(candidate_top_k) is not int or not 5 <= candidate_top_k <= 25:
        raise ValueError("candidate_top_k 必须是 5～25 的整数")
    if type(max_references) is not int or not 1 <= max_references <= 12:
        raise ValueError("max_reference_count 必须是 1～12 的整数")
    if type(options["hyde_enabled"]) is not bool:
        raise ValueError("hyde_enabled 必须是布尔值")
    web_enabled = options.get("web_enabled", True)
    if type(web_enabled) is not bool:
        raise ValueError("web_enabled 必须是布尔值")
    matching_preference = str(options["matching_preference"])
    hyde_influence = str(options["hyde_influence"])
    if matching_preference not in {"keyword", "balanced", "semantic"}:
        raise ValueError("matching_preference 枚举值非法")
    if hyde_influence not in {"low", "medium", "high"}:
        raise ValueError("hyde_influence 枚举值非法")
    dense, sparse = {
        "keyword": (0.35, 0.65),
        "balanced": (0.6, 0.4),
        "semantic": (0.8, 0.2),
    }[matching_preference]
    hyde_enabled = options["hyde_enabled"]
    hyde_weight = {
        "low": 0.4, "medium": 0.8, "high": 1.0,
    }[hyde_influence]
    return {
        "ann_limit": _clamp(2 * candidate_top_k, 10, 50),
        "search_top_k": candidate_top_k,
        "dense_weight": dense, "sparse_weight": sparse,
        "hyde_enabled": hyde_enabled,
        "web_enabled": web_enabled, "web_top_k": 5,
        "rrf_k": 60, "rrf_embedding_weight": 1.0,
        "rrf_hyde_weight": hyde_weight,
        "rrf_top_k": _clamp(
            max(max_references, math.ceil(1.2 * candidate_top_k)), 5, 30
        ),
        "rerank_min_topk": min(2, max_references),
        "rerank_max_topk": max_references,
        "rerank_gap_ratio": 0.2, "rerank_gap_abs": 0.2,
        "rerank_max_per_document": 2,
        "answer_max_context_chars": _clamp(
            max_references * 2500, 5000, 30_000
        ),
    }


def resolve_retrieval_config(
    mode: str = "balanced",
    options: Mapping[str, Any] | None = None,
) -> EffectiveRetrievalConfig:
    """把已校验的公开模式确定性映射为内部配置。"""
    mode = str(getattr(mode, "value", mode) or "balanced")
    if mode == "custom":
        if options is None:
            raise ValueError("custom 模式必须提供 retrieval_options")
        values = _custom_values(options)
    elif mode in _PRESETS:
        if options is not None:
            raise ValueError("仅 custom 模式允许 retrieval_options")
        values = dict(_PRESETS[mode])
    else:
        raise ValueError(f"不支持的检索模式：{mode}")
    result = EffectiveRetrievalConfig(mode=mode, **values)
    _validate_invariants(result)
    return result


def _validate_invariants(value: EffectiveRetrievalConfig) -> None:
    if value.mode not in {"balanced", "precision", "recall", "custom"}:
        raise ValueError("检索模式非法")
    if type(value.hyde_enabled) is not bool or type(value.web_enabled) is not bool:
        raise ValueError("检索开关必须是布尔值")
    integer_fields = (
        value.ann_limit, value.search_top_k, value.web_top_k, value.rrf_k,
        value.rrf_top_k, value.rerank_min_topk, value.rerank_max_topk,
        value.rerank_max_per_document, value.answer_max_context_chars,
    )
    if any(type(item) is not int for item in integer_fields):
        raise ValueError("检索数量参数必须是整数")
    if not 10 <= value.ann_limit <= 50:
        raise ValueError("ann_limit 超过服务端硬上限")
    if not 5 <= value.search_top_k <= 25 or value.search_top_k > value.ann_limit:
        raise ValueError("search_top_k 非法")
    if not math.isclose(value.dense_weight + value.sparse_weight, 1.0):
        raise ValueError("Dense/Sparse 权重之和必须为 1")
    if not 0 <= value.dense_weight <= 1 or not 0 <= value.sparse_weight <= 1:
        raise ValueError("检索权重必须位于 0 到 1")
    if value.rerank_min_topk > value.rerank_max_topk:
        raise ValueError("Rerank 最小值不能大于最大值")
    if not 1 <= value.rerank_min_topk <= 12:
        raise ValueError("Rerank 最小值非法")
    if not 1 <= value.rerank_max_topk <= 12:
        raise ValueError("Rerank 最大值非法")
    if value.rrf_top_k < value.rerank_max_topk or value.rrf_top_k > 30:
        raise ValueError("RRF 输出数量非法")
    if not 10 <= value.rrf_k <= 100:
        raise ValueError("RRF K 非法")
    if not all(
        0 <= weight <= 1
        for weight in (
            value.rrf_embedding_weight, value.rrf_hyde_weight,
        )
    ):
        raise ValueError("RRF 权重非法")
    if not 1 <= value.web_top_k <= 10:
        raise ValueError("Web Top-K 非法")
    if not 0 <= value.rerank_gap_ratio <= 1:
        raise ValueError("Rerank 相对阈值非法")
    if not 0 <= value.rerank_gap_abs <= 1:
        raise ValueError("Rerank 绝对阈值非法")
    if not 1 <= value.rerank_max_per_document <= 5:
        raise ValueError("单文档上下文上限非法")
    if not 5_000 <= value.answer_max_context_chars <= 30_000:
        raise ValueError("最终上下文超过服务端硬上限")


def get_effective_retrieval_config(
    state: Mapping[str, Any] | None,
) -> EffectiveRetrievalConfig:
    """读取 state 配置；旧 service 调用缺失配置时回退 balanced。"""
    value = (state or {}).get("retrieval_config")
    if value is None:
        return resolve_retrieval_config()
    if isinstance(value, EffectiveRetrievalConfig):
        _validate_invariants(value)
        return value
    if isinstance(value, Mapping):
        result = EffectiveRetrievalConfig(**dict(value))
        _validate_invariants(result)
        return result
    raise TypeError("retrieval_config 必须是有效配置对象或字典")


_MODE_LABELS = {
    "balanced": "均衡", "precision": "精确回答",
    "recall": "全面检索", "custom": "自定义",
}


def build_retrieval_metadata(state: Mapping[str, Any]) -> dict[str, Any]:
    """从最终 state 生成普通用户可见的安全检索摘要。"""
    cfg = get_effective_retrieval_config(state)
    statuses = {
        "embedding": state.get("embedding_status"),
        "hyde": state.get("hyde_status"),
        "web": state.get("web_status"),
        "reranker": state.get("reranker_status"),
    }
    degradations = [f"{name}_failed" for name, status in statuses.items()
                    if status == "failed"]
    labels = {"keyword": "关键词优先", "semantic": "语义优先"}
    matching = "均衡"
    if cfg.dense_weight < cfg.sparse_weight:
        matching = labels["keyword"]
    elif cfg.dense_weight > 0.6:
        matching = labels["semantic"]
    return {
        "mode": cfg.mode,
        "mode_label": _MODE_LABELS[cfg.mode],
        "summary": {
            "search_breadth": "较窄" if cfg.search_top_k <= 6 else
                              "较广" if cfg.search_top_k >= 20 else "适中",
            "reference_range": f"{cfg.rerank_min_topk}～{cfg.rerank_max_topk}",
            "matching_preference": matching,
            "hyde_enabled": cfg.hyde_enabled,
            "web_enabled": cfg.web_enabled and not bool(state.get("eval_disable_web")),
        },
        "counts": {
            "embedding": len(state.get("embedding_chunks") or []),
            "hyde": len(state.get("hyde_embedding_chunks") or []),
            "local_fused": len(state.get("rrf_chunks") or []),
            "web": len(state.get("web_search_docs") or []),
            "final_context": len(
                state.get("answer_context_docs")
                or state.get("reranked_docs")
                or []
            ),
        },
        "degradations": degradations,
    }
