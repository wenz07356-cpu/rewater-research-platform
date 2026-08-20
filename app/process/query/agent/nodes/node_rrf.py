"""RRF 融合节点适配层。"""

from app.rag.query.rrf_service import fuse_retrieval_results
from app.shared.runtime.logger import node_log
from app.shared.utils.task_utils import add_done_task, add_running_task


@node_log("node_rrf")
def node_rrf(state: dict) -> dict:
    """融合两路本地结果；Web 分支只在此完成并行汇合。"""
    session_id = state["session_id"]
    is_stream = state.get("is_stream", False)
    add_running_task(session_id, "node_rrf", is_stream)
    result = fuse_retrieval_results(state)
    if not isinstance(result.get("rrf_chunks"), list):
        raise TypeError("rrf_chunks 必须为列表")
    add_done_task(session_id, "node_rrf", is_stream)
    return result


if __name__ == "__main__":
    embedding_chunk = {
        "chunk_id": "debug-chunk-1",
        "file_title": "深圳市再生水利用示例资料",
        "section_title": "发展现状",
        "display_title": "深圳市再生水利用示例资料 / 发展现状",
        "content": "深圳市持续推进再生水设施建设和利用。",
        "score": 0.91,
        "source": "milvus",
        "retrieval_source": "embedding",
    }
    hyde_chunk = {
        **embedding_chunk,
        "score": 0.83,
        "retrieval_source": "hyde",
    }
    test_state = {
        "session_id": "debug-rrf",
        "is_stream": False,
        "embedding_chunks": [embedding_chunk],
        "hyde_embedding_chunks": [hyde_chunk],
    }
    result_state = node_rrf(test_state)
    print(result_state)
