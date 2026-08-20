"""联网搜索节点适配层。"""

from app.rag.query.web_search_service import search_web_documents
from app.shared.runtime.logger import node_log
from app.shared.utils.task_utils import add_done_task, add_running_task


@node_log("node_web_search_mcp")
def node_web_search_mcp(state: dict) -> dict:
    """调用 WebSearch service 并返回 web_search_docs 状态增量。"""
    session_id = state["session_id"]
    is_stream = state.get("is_stream", False)
    add_running_task(session_id, "node_web_search_mcp", is_stream)
    result = (
        {"web_search_docs": []}
        if state.get("eval_disable_web")
        else search_web_documents(state)
    )
    if not isinstance(result.get("web_search_docs"), list):
        raise TypeError("web_search_docs 必须为列表")
    add_done_task(session_id, "node_web_search_mcp", is_stream)
    return result


if __name__ == "__main__":
    test_state = {
        "session_id": "debug-web-search",
        "is_stream": False,
        "rewritten_query": "深圳市再生水现状",
        "query_filters": {
            "file_titles": [],
            "region_names": ["深圳市"],
            "document_types": [],
            "topics": ["再生水现状"],
            "keywords": ["再生水"],
            "hard_fields": [],
            "strict": False,
        },
    }
    result_state = node_web_search_mcp(test_state)
    print(result_state)
