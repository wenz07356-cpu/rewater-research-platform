"""DashScope MCP 联网检索服务。"""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Coroutine
from urllib.parse import urlsplit, urlunsplit

from agents.mcp.server import MCPServerStreamableHttp

from app.process.query.agent.state import QueryGraphState
from app.rag.query.config import (
    WEB_CONNECT_TIMEOUT_SECONDS,
    WEB_READ_TIMEOUT_SECONDS,
    WEB_SEARCH_TOP_K,
)
from app.rag.query.search_embedding_service import normalize_query_filters
from app.shared.config.bailian_mcp_config import mcp_config
from app.shared.runtime.logger import logger, step_log


def validate_web_search_inputs(
    state: QueryGraphState,
) -> tuple[str, dict[str, Any]]:
    """校验 Web 搜索输入并返回改写问题和规范化过滤结构。"""
    rewritten_query = str(state.get("rewritten_query") or "").strip()
    if not rewritten_query:
        logger.error("Web 搜索缺少 rewritten_query")
        raise ValueError("rewritten_query 不能为空")
    return rewritten_query, normalize_query_filters(state.get("query_filters"))


def build_web_search_query(
    rewritten_query: str,
    query_filters: dict[str, Any],
) -> str:
    """生成简短的搜索引擎查询文本。"""
    parts = [rewritten_query]
    for field in ("file_titles", "region_names", "document_types"):
        values = [
            item
            for item in query_filters.get(field, [])
            if item not in rewritten_query
        ]
        if values:
            parts.append(" ".join(values))
    return " ".join(parts)[:500]


async def call_web_search_mcp(query: str, count: int) -> Any:
    """连接 MCP、调用 WebSearch，并保证连接最终清理。"""
    if not mcp_config.mcp_base_url or not mcp_config.api_key:
        raise ValueError("DashScope MCP URL 或 API Key 未配置")
    server = MCPServerStreamableHttp(
        name="query_web_search_mcp",
        client_session_timeout_seconds=WEB_CONNECT_TIMEOUT_SECONDS,
        params={
            "url": mcp_config.mcp_base_url,
            "headers": {"Authorization": mcp_config.api_key},
            "timeout": WEB_CONNECT_TIMEOUT_SECONDS,
            "sse_read_timeout": WEB_READ_TIMEOUT_SECONDS,
        },
    )
    try:
        await server.connect()
        return await server.call_tool(
            tool_name="bailian_web_search",
            arguments={"query": query, "count": count},
        )
    finally:
        await server.cleanup()


def _run_coroutine(coroutine: Coroutine[Any, Any, Any]) -> Any:
    """在同步 LangGraph 节点中安全执行协程。

    FastAPI 的 async 路由可能已经存在运行中的事件循环；此时把 asyncio.run
    放到短生命周期工作线程，避免嵌套事件循环异常。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coroutine).result()


def _normalize_url(value: Any) -> str:
    """移除 URL fragment，用于展示和稳定去重。"""
    url = str(value or "").strip()
    if not url:
        return ""
    try:
        parts = urlsplit(url)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))
    except ValueError:
        return url


def parse_web_search_response(
    mcp_result: Any,
    limit: int = WEB_SEARCH_TOP_K,
) -> list[dict[str, Any]]:
    """解析 MCP 响应，规范化并去重 Web 候选。"""
    blocks = getattr(mcp_result, "content", None) or []
    text = next(
        (
            getattr(block, "text", "")
            for block in blocks
            if getattr(block, "text", "")
        ),
        "",
    )
    if not text:
        logger.warning("WebSearch MCP 响应中没有文本内容")
        return []
    payload = json.loads(text)
    pages = payload.get("pages", []) if isinstance(payload, dict) else []
    if not isinstance(pages, list):
        raise ValueError("WebSearch pages 必须为列表")

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page in pages:
        if not isinstance(page, dict):
            continue
        title = str(page.get("title") or "").strip()
        content = str(page.get("snippet") or page.get("content") or "").strip()
        url = _normalize_url(page.get("url"))
        if not title and not content:
            continue
        key = url or f"{title}\n{content}"
        if key in seen:
            continue
        seen.add(key)
        result.append(
            {
                "chunk_id": None,
                "document_id": None,
                "chunk_index": None,
                "file_title": None,
                "section_title": None,
                "display_title": title or "网络搜索结果",
                "content": content,
                "context_type": "text",
                "region_names": [],
                "document_type": None,
                "topics": [],
                "keywords": [],
                "score": 0.0,
                "source": "web",
                "retrieval_source": "web",
                "url": url,
            }
        )
        if len(result) >= limit:
            break
    return result


@step_log("search_web_documents")
def search_web_documents(
    state: QueryGraphState,
    count: int = WEB_SEARCH_TOP_K,
) -> dict[str, list[dict[str, Any]]]:
    """执行联网搜索。

    输入：包含 rewritten_query/query_filters 的状态和结果数量上限。
    输出：仅包含 web_search_docs 的状态增量。
    步骤：校验输入、构造查询、同步运行 MCP 协程、解析候选；外部异常时
    记录日志并返回空列表。
    """
    rewritten_query, filters = validate_web_search_inputs(state)
    try:
        query = build_web_search_query(rewritten_query, filters)
        raw_result = _run_coroutine(call_web_search_mcp(query, count))
        documents = parse_web_search_response(raw_result, count)
        logger.info(f"Web 搜索完成：query_length={len(query)}, hits={len(documents)}")
        return {"web_search_docs": documents}
    except Exception as exc:
        logger.exception(f"Web 搜索失败，降级为空结果：error={exc}")
        return {"web_search_docs": []}
