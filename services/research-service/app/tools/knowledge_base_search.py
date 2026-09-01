import math
import re
from typing import Any

import httpx
from loguru import logger

from app.config.config import get_settings

REQUEST_TIMEOUT_SECONDS = 90
DEFAULT_TOP_K = 6
MIN_TOP_K = 1
MAX_TOP_K = 6
PROVIDER = "knowledge_service"
SOURCE_TYPE = "internal_knowledge_base"
_MAX_ERROR_MESSAGE_LENGTH = 240
_MAX_LOG_QUERY_LENGTH = 120


async def knowledge_base_search(
    query: str,
    top_k: int | None = None,
) -> dict[str, Any]:
    """调用自研知识库的证据检索接口并返回统一格式的原始证据。"""

    normalized_query = _normalize_query(query)
    if not normalized_query:
        return _build_result(status="error", query="", error="query 不能为空")

    settings = get_settings()
    # 配置字段将在后续配置接入步骤中加入；兼容式读取保证本模块可独立落地。
    if not getattr(settings, "enable_knowledge_service", False):
        logger.warning("自研知识库未启用，跳过检索")
        return _build_result(
            status="skipped",
            query=normalized_query,
            error="ENABLE_KNOWLEDGE_SERVICE 未启用",
        )

    base_url = getattr(settings, "knowledge_service_base_url", None)
    if not base_url:
        logger.warning("自研知识库 Base URL 未配置，跳过检索")
        return _build_result(
            status="skipped",
            query=normalized_query,
            error="KNOWLEDGE_SERVICE_BASE_URL 未配置",
        )

    try:
        resolved_top_k = _resolve_top_k(
            top_k,
            getattr(settings, "knowledge_service_top_k", DEFAULT_TOP_K),
        )
    except ValueError as exc:
        return _build_result(
            status="error",
            query=normalized_query,
            error=_format_error(exc),
        )

    retrieval_url = f"{str(base_url).rstrip('/')}/retrieval"
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                retrieval_url,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={"query": normalized_query, "top_k": resolved_top_k},
            )
            response.raise_for_status()
            response_data = response.json()
        result = _normalize_response(response_data, normalized_query)
    except (httpx.HTTPError, TypeError, ValueError) as exc:
        error = _format_error(exc)
        logger.warning(
            "自研知识库检索失败，query={}，error={}",
            _truncate(normalized_query, _MAX_LOG_QUERY_LENGTH),
            error,
        )
        return _build_result(status="error", query=normalized_query, error=error)

    logger.info(
        "自研知识库检索完成，query={}，status={}，chunks={}，request_id={}",
        _truncate(normalized_query, _MAX_LOG_QUERY_LENGTH),
        result["status"],
        len(result["chunks"]),
        result["request_id"],
    )
    return result


def _normalize_query(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def _resolve_top_k(value: object, configured_value: object) -> int:
    candidate = configured_value if value is None else value
    if isinstance(candidate, bool):
        raise ValueError("top_k 必须是整数，不能是布尔值")

    if isinstance(candidate, int):
        resolved = candidate
    elif isinstance(candidate, str) and re.fullmatch(r"[+-]?\d+", candidate.strip()):
        resolved = int(candidate.strip())
    else:
        raise ValueError("top_k 必须是可转换为整数的值")

    return max(MIN_TOP_K, min(resolved, MAX_TOP_K))


def _normalize_response(response_data: object, query: str) -> dict[str, Any]:
    if not isinstance(response_data, dict):
        raise TypeError("知识库响应必须是 JSON object")

    status = response_data.get("status")
    if status not in {"ok", "empty", "needs_clarification"}:
        raise ValueError(f"知识库返回未知 status: {status!r}")

    request_id = _optional_string(response_data.get("request_id"))
    if status == "empty":
        return _build_result(status="empty", query=query, request_id=request_id)

    if status == "needs_clarification":
        clarification_question = _optional_string(
            response_data.get("clarification_question")
        )
        return _build_result(
            status="needs_clarification",
            query=query,
            request_id=request_id,
            clarification_question=clarification_question,
        )

    raw_chunks = response_data.get("chunks")
    if not isinstance(raw_chunks, list):
        raise TypeError("知识库响应的 chunks 必须是数组")

    chunks = [chunk for item in raw_chunks if (chunk := _normalize_chunk(item)) is not None]
    return _build_result(
        status="ok" if chunks else "empty",
        query=query,
        request_id=request_id,
        chunks=chunks,
    )


def _normalize_chunk(item: object) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None

    chunk_id = _required_string(item.get("chunk_id"))
    document_id = _required_string(item.get("document_id"))
    document_name = _required_string(item.get("document_name"))
    content = _required_string(item.get("content"))
    score = item.get("score")
    if not all((chunk_id, document_id, document_name, content)):
        return None
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return None

    normalized_score = float(score)
    if not math.isfinite(normalized_score):
        return None

    return {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "document_name": document_name,
        "section_title": _optional_string(item.get("section_title")),
        "content": content,
        "score": normalized_score,
        "source_type": SOURCE_TYPE,
        "provider": PROVIDER,
    }


def _build_result(
    *,
    status: str,
    query: str,
    request_id: str | None = None,
    chunks: list[dict[str, Any]] | None = None,
    clarification_question: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "provider": PROVIDER,
        "query": query,
        "request_id": request_id,
        "chunks": chunks or [],
        "clarification_question": clarification_question,
        "error": error,
    }


def _format_error(exc: Exception) -> str:
    message = " ".join(str(exc).split())
    if message:
        return f"{type(exc).__name__}: {_truncate(message, _MAX_ERROR_MESSAGE_LENGTH)}"
    return type(exc).__name__


def _required_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _optional_string(value: object) -> str | None:
    return _required_string(value)


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: limit - 3]}..."
