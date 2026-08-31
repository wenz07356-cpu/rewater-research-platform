"""
查询服务 HTTP 入口模块，直接承载查询接口与相关接口业务逻辑。
"""
from dataclasses import replace
import sys
import uuid
from mimetypes import guess_type
from pathlib import Path

# 兼容直接以 `python query_server.py` 方式启动，提前把项目根目录加入模块搜索路径。
if __package__ in (None, ""):
    bootstrap_root = Path(__file__).resolve().parents[3]
    if str(bootstrap_root) not in sys.path:
        sys.path.insert(0, str(bootstrap_root))

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

from app.api.schemas.query import (
    HistoryItem,
    HistoryResponse,
    QueryRequest,
    QueryResponse,
    RetrievalRequest,
    RetrievalResponse,
    RetrievalMetadata,
)
from app.shared.runtime.logger import PROJECT_ROOT, logger
from app.infra.config import settings
from app.infra.persistence.history_repository import history_repository
from app.process.query.agent.main_graph import query_app as query_graph_app
from app.process.query.agent.state import create_query_default_state
from app.rag.query.retrieval_config import (
    EffectiveRetrievalConfig, build_retrieval_metadata, resolve_retrieval_config,
)
from app.rag.query.evidence_retrieval_service import (
    build_retrieval_chunks,
    retrieve_evidence,
)
from app.shared.utils.sse_utils import SSEEvent, create_sse_queue, push_to_session, sse_generator
from app.shared.utils.task_utils import (
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_PROCESSING,
    clear_task,
    get_done_task_list,
    get_task_result,
    update_task_status,
)


app = FastAPI(
    title=settings.query_app_name,
    description="企业化 RAG 查询服务，负责问答、SSE 输出与历史记录查询。",
    version="0.2.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins) or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount(
    "/query-assets",
    StaticFiles(
        directory=(
            PROJECT_ROOT / "app" / "process" / "query" / "page" / "assets"
        )
    ),
    name="query-assets",
)


def new_session_id() -> str:
    """
    生成新的会话 ID。

    Returns:
        str: 基于 UUID 生成的唯一会话标识。
    """
    return str(uuid.uuid4())


def invoke_query(
    session_id: str,
    query: str,
    is_stream: bool,
    *,
    retrieval_config: EffectiveRetrievalConfig | None = None,
) -> dict:
    """
    调用查询主图并维护统一的任务状态。

    Args:
        session_id: 当前会话 ID。
        query: 用户原始问题。
        is_stream: 是否为流式模式。

    Returns:
        dict: 查询图执行后的最终状态。
    """
    clear_task(session_id)
    update_task_status(session_id, TASK_STATUS_PROCESSING, is_stream)
    initial_state = create_query_default_state(
        session_id=session_id,
        original_query=query,
        is_stream=is_stream,
        retrieval_config=retrieval_config or resolve_retrieval_config(),
    )
    state = query_graph_app.invoke(initial_state)
    update_task_status(session_id, TASK_STATUS_COMPLETED, is_stream)
    return state


def run_stream_query_background(
    session_id: str, query: str, prepared: dict,
) -> None:
    """
    在后台执行一次流式查询任务。

    Args:
        session_id: 当前流式查询对应的会话 ID。
        query: 用户原始问题。
    """
    try:
        state = invoke_query(
            session_id=session_id, query=query, is_stream=True, **prepared
        )
        push_to_session(
            session_id,
            SSEEvent.FINAL,
            {
                "answer": get_task_result(session_id, "answer") or state.get("answer", ""),
                "status": "completed",
                "image_urls": state.get("image_urls", []),
                "retrieval_metadata": state.get("retrieval_metadata")
                or build_retrieval_metadata(state),
            },
        )

    except Exception as exc:
        logger.exception(f"流式查询执行失败，session_id={session_id}, error={exc}")
        update_task_status(session_id, TASK_STATUS_FAILED, True)
        push_to_session(
            session_id,
            SSEEvent.ERROR,
            {"message": "查询执行失败，请检查日志或稍后重试。"},
        )


def start_stream_query(
    background_tasks: BackgroundTasks,
    query: str,
    session_id: str | None = None,
    prepared: dict | None = None,
) -> QueryResponse:
    """
    启动一条流式查询任务。

    Args:
        background_tasks: FastAPI 后台任务对象。
        query: 用户原始问题。
        session_id: 可选会话 ID；为空时自动生成。

    Returns:
        QueryResponse: 返回处理中提示与当前会话 ID。
    """
    final_session_id = session_id or new_session_id()
    create_sse_queue(final_session_id)
    background_tasks.add_task(
        run_stream_query_background,
        final_session_id,
        query,
        prepared or {},
    )
    initial_state = create_query_default_state(**(prepared or {}))
    return QueryResponse(
        message="结果正在处理中...", session_id=final_session_id,
        retrieval_metadata=build_retrieval_metadata(initial_state),
    )


def execute_query(
    query: str, session_id: str | None = None, *, prepared: dict | None = None,
) -> QueryResponse:
    """
    以非流式方式执行查询。

    Args:
        query: 用户原始问题。
        session_id: 可选会话 ID；为空时自动生成。

    Returns:
        QueryResponse: 包含最终答案和已完成节点的响应对象。
    """
    final_session_id = session_id or new_session_id()
    state = invoke_query(
        session_id=final_session_id, query=query, is_stream=False,
        **(prepared or {}),
    )
    answer = get_task_result(final_session_id, "answer") or state.get("answer", "")
    return QueryResponse(
        message="处理完成！",
        session_id=final_session_id,
        answer=answer,
        done_list=get_done_task_list(final_session_id),
        image_urls=state.get("image_urls", []),
        retrieval_metadata=state.get("retrieval_metadata")
        or build_retrieval_metadata(state),
    )


def build_history_response(session_id: str, limit: int = 10) -> HistoryResponse:
    """
    查询并组装指定会话的历史记录。

    Args:
        session_id: 目标会话 ID。
        limit: 返回记录条数上限。

    Returns:
        HistoryResponse: 组装后的历史消息集合。
    """
    records = history_repository.list_recent(session_id, limit=limit)
    def public_metadata(record: dict) -> RetrievalMetadata | None:
        metadata = record.get("retrieval_metadata")
        if not metadata:
            return None
        try:
            return RetrievalMetadata.model_validate(metadata)
        except Exception as exc:
            logger.warning(f"忽略无效的旧检索元数据：error={exc}")
            return None

    items = [
        HistoryItem(
            _id=str(record.get("_id")) if record.get("_id") is not None else "",
            session_id=record.get("session_id", ""),
            role=record.get("role", ""),
            text=record.get("text", ""),
            rewritten_query=record.get("rewritten_query", ""),
            item_names=record.get("item_names") or [],
            query_filters=record.get("query_filters") or {},
            image_urls=record.get("image_urls") or [],
            retrieval_metadata=public_metadata(record),
            ts=record.get("ts"),
        )
        for record in records
    ]
    return HistoryResponse(session_id=session_id, items=items)


def prepare_query_request(request: QueryRequest) -> dict:
    """在进入后台线程前解析本次请求的不可变检索配置。"""
    mode = request.retrieval_mode.value if request.retrieval_mode else "balanced"
    options = (
        request.retrieval_options.model_dump(mode="json", exclude_none=True)
        if request.retrieval_options else None
    )
    try:
        retrieval_config = resolve_retrieval_config(mode, options)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # 联网搜索是独立的请求级选择；省略时保留模式预设或旧 custom 配置。
    if request.web_enabled is not None:
        retrieval_config = replace(
            retrieval_config, web_enabled=request.web_enabled
        )

    return {"retrieval_config": retrieval_config}


def clear_query_history(session_id: str) -> dict:
    """
    清空指定会话的历史记录。

    Args:
        session_id: 目标会话 ID。

    Returns:
        dict: 删除结果说明。
    """
    delete_count = history_repository.clear_session(session_id)
    return {
        "message": f"删除:{session_id}会话对应的聊天记录成功!!",
        "deleted_count": delete_count,
    }


@app.get("/health")
def health():
    """
    返回查询服务健康检查结果。

    Returns:
        dict: 包含当前服务名称、环境与模块信息。
    """
    return {
        "ok": True,
        "app": settings.query_app_name,
        "env": settings.app_env,
        "module": "query",
    }


@app.get("/")
def index():
    """
    返回查询服务首页导航信息。

    Returns:
        dict: 包含页面地址、查询接口、流式接口与历史接口导航信息。
    """
    return {
        "message": "Enterprise RAG Query Service",
        "docs": "/docs",
        "openapi": "/openapi.json",
        "routes": {
            "html": "/html",
            "query": "/query",
            "retrieval": "/retrieval",
            "stream": "/stream/{session_id}",
            "history": "/history/{session_id}",
        },
    }


@app.get("/html")
def query_html():
    """
    返回查询演示页面。

    Returns:
        FileResponse: 本地聊天演示页面文件响应。
    """
    html_path = PROJECT_ROOT / "app" / "process" / "query" / "page" / "chat.html"
    return FileResponse(
        path=html_path,
        media_type=guess_type(html_path.name)[0],
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest, background_tasks: BackgroundTasks):
    """
    统一处理普通问答与流式问答请求。

    Args:
        request: 查询请求体，包含问题文本、是否流式输出和可选会话 ID。
        background_tasks: FastAPI 后台任务对象，流式模式下用于异步启动查询任务。

    Returns:
        QueryResponse: 非流式时返回完整答案；流式时返回会话 ID 与处理中提示。
    """
    final_session_id = request.session_id or new_session_id()
    prepared = prepare_query_request(request)
    if request.is_stream:
        return start_stream_query(
            background_tasks=background_tasks,
            query=request.query,
            session_id=final_session_id,
            prepared=prepared,
        )
    return execute_query(
        query=request.query, session_id=final_session_id, prepared=prepared
    )


@app.post("/retrieval", response_model=RetrievalResponse)
def retrieval(request: RetrievalRequest) -> RetrievalResponse:
    """为 DeepAgent 返回内部知识库的精排证据，不生成答案。"""
    request_id = str(uuid.uuid4())
    state = retrieve_evidence(request.query, request_id)

    clarification_question = str(state.get("answer") or "").strip()
    if clarification_question:
        return RetrievalResponse(
            status="needs_clarification",
            request_id=request_id,
            query=request.query,
            clarification_question=clarification_question,
            chunks=[],
        )

    chunks = build_retrieval_chunks(
        state.get("reranked_docs") or [],
        request.top_k,
    )
    return RetrievalResponse(
        status="ok" if chunks else "empty",
        request_id=request_id,
        query=request.query,
        chunks=chunks,
    )


@app.get("/stream/{session_id}")
async def stream_query_result(session_id: str, request: Request):
    """
    建立指定会话的 SSE 结果流。

    Args:
        session_id: 目标会话 ID。
        request: 当前 HTTP 请求对象，用于感知客户端断开连接。

    Returns:
        StreamingResponse: 基于 SSE 协议的流式响应对象。
    """
    return StreamingResponse(
        sse_generator(session_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/history/{session_id}", response_model=HistoryResponse)
def history(session_id: str, limit: int = 10):
    """
    查询会话历史记录。

    Args:
        session_id: 目标会话 ID。
        limit: 返回记录条数上限。

    Returns:
        HistoryResponse: 当前会话最近的历史消息集合。
    """
    return build_history_response(session_id=session_id, limit=limit)


@app.delete("/history/{session_id}")
def clear_history(session_id: str):
    """
    清空指定会话的历史记录。

    Args:
        session_id: 目标会话 ID。

    Returns:
        dict: 删除结果说明。
    """
    return clear_query_history(session_id)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.app_host, port=settings.query_app_port)
