"""Markdown 文档切分节点。"""

from app.process.import_.agent.state import ImportGraphState
from app.rag.import_.split_service import split_document
from app.shared.runtime.logger import logger, node_log
from app.shared.utils.task_utils import add_done_task, add_running_task


NODE_NAME = "node_document_split"


@node_log(NODE_NAME)
def node_document_split(state: ImportGraphState) -> ImportGraphState:
    """按 Markdown 标题切分文档并生成最终 chunk 字段。

    核心功能：调用统一切分 service，不根据文种选择策略。
    输入：包含正文、标题和 document_metadata 的导入状态。
    输出：写入最终 chunks 的状态。
    步骤：登记运行，执行切分，登记完成并记录 chunk 数量。
    """
    task_id = str(state.get("task_id") or "-")
    add_running_task(task_id, NODE_NAME)
    result = split_document(state)
    add_done_task(task_id, NODE_NAME)
    logger.info(f"文档切分节点完成：chunks={len(result.get('chunks') or [])}")
    return result
