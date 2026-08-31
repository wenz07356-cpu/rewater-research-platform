"""HyDE 检索节点适配层。"""

from app.rag.query.search_embedding_hyde_service import search_chunks_with_hyde
from app.shared.runtime.logger import node_log
from app.shared.utils.task_utils import add_done_task, add_running_task


@node_log("node_search_embedding_hyde")
def node_search_embedding_hyde(state: dict) -> dict:
    """调用 HyDE service 并返回单层状态增量。"""
    session_id = state["session_id"]
    is_stream = state.get("is_stream", False)
    add_running_task(session_id, "node_search_embedding_hyde", is_stream)
    result = search_chunks_with_hyde(state)
    if not isinstance(result.get("hyde_embedding_chunks"), list):
        raise TypeError("hyde_embedding_chunks 必须为列表")
    add_done_task(session_id, "node_search_embedding_hyde", is_stream)
    return result


if __name__ == "__main__":
    test_state = {
        "session_id": "debug-search-embedding-hyde",
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
    result_state = node_search_embedding_hyde(test_state)
    print(result_state)
