"""答案输出节点适配层。"""

from app.rag.query.answer_output_service import produce_answer
from app.shared.runtime.logger import node_log
from app.shared.utils.task_utils import add_done_task, add_running_task


@node_log("node_answer_output")
def node_answer_output(state: dict) -> dict:
    """调用统一答案出口并返回答案、图片、上下文与检索元数据。"""
    session_id = state["session_id"]
    is_stream = state.get("is_stream", False)
    add_running_task(session_id, "node_answer_output", is_stream)
    result = produce_answer(state)
    if not result.get("answer"):
        raise RuntimeError("答案输出节点未生成 answer")
    add_done_task(session_id, "node_answer_output", is_stream)
    return result


if __name__ == "__main__":
    from unittest.mock import patch

    from app.rag.query import answer_output_service

    test_state = {
        "session_id": "debug-answer-output",
        "is_stream": False,
        "original_query": "深圳市再生水现状",
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
        "history": [],
        "reranked_docs": [],
        "answer": "",
    }
    # 节点调试不依赖 MongoDB，仅跳过助手消息落库。
    with patch.object(
        answer_output_service.history_repository,
        "save_message",
        return_value=None,
    ):
        result_state = node_answer_output(test_state)
    print(result_state)
