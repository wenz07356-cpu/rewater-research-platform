"""精排节点适配层。"""

from app.rag.query.rerank_service import rerank_documents
from app.shared.runtime.logger import node_log
from app.shared.utils.task_utils import add_done_task, add_running_task


@node_log("node_rerank")
def node_rerank(state: dict) -> dict:
    """调用 Reranker service 并返回 reranked_docs 状态增量。"""
    session_id = state["session_id"]
    is_stream = state.get("is_stream", False)
    add_running_task(session_id, "node_rerank", is_stream)
    result = rerank_documents(state)
    if not isinstance(result.get("reranked_docs"), list):
        raise TypeError("reranked_docs 必须为列表")
    add_done_task(session_id, "node_rerank", is_stream)
    return result


if __name__ == "__main__":
    test_state = {
        "session_id": "debug-rerank",
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
        "rrf_chunks": [
            {
                "chunk_id": "debug-chunk-1",
                "file_title": "深圳市再生水利用示例资料",
                "section_title": "发展现状",
                "display_title": "深圳市再生水利用示例资料 / 发展现状",
                "content": "深圳市持续推进再生水设施建设和利用。",
                "context_type": "text",
                "region_names": ["深圳市"],
                "document_type": "规划",
                "topics": ["再生水利用"],
                "keywords": ["设施建设"],
                "score": 0.03,
                "source": "milvus",
                "retrieval_sources": ["embedding", "hyde"],
                "url": "",
            }
        ],
        "web_search_docs": [
            {
                "chunk_id": None,
                "document_id": None,
                "chunk_index": None,
                "file_title": None,
                "section_title": None,
                "display_title": "深圳市再生水利用情况持续提升",
                "content": "深圳市正在扩大再生水应用场景，并持续完善相关设施。",
                "context_type": "text",
                "region_names": [],
                "document_type": None,
                "topics": [],
                "keywords": [],
                "score": 0.0,
                "source": "web",
                "retrieval_source": "web",
                "url": "https://example.com/shenzhen-reclaimed-water",
            }
        ],
    }
    result_state = node_rerank(test_state)
    print(result_state)
