"""查询理解节点适配层。"""

from app.rag.query.item_name_confirm_service import understand_query
from app.shared.runtime.logger import node_log
from app.shared.utils.task_utils import add_done_task, add_running_task


@node_log("node_item_name_confirm")
def node_item_name_confirm(state: dict) -> dict:
    """登记进度、调用查询理解 service，并原样返回状态增量。"""
    session_id = state["session_id"]
    is_stream = state.get("is_stream", False)
    add_running_task(session_id, "node_item_name_confirm", is_stream)
    result = understand_query(state)
    if not result.get("rewritten_query") and not result.get("answer"):
        raise RuntimeError("查询理解节点未生成 rewritten_query 或澄清回答")
    add_done_task(session_id, "node_item_name_confirm", is_stream)
    return result


if __name__ == "__main__":
    test_state = {
        "session_id": "debug-query-understanding",
        "is_stream": False,
        "original_query": "深圳市再生水现状",
    }
    result_state = node_item_name_confirm(test_state)
    print(result_state)
