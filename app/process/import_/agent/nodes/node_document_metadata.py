"""文档 metadata 抽取节点。"""

from app.process.import_.agent.state import ImportGraphState
from app.rag.import_.item_name_service import extract_document_metadata
from app.shared.runtime.logger import logger, node_log
from app.shared.utils.task_utils import add_done_task, add_running_task


NODE_NAME = "node_document_metadata"


@node_log(NODE_NAME)
def node_document_metadata(state: ImportGraphState) -> ImportGraphState:
    """调用 LLM 抽取文档级 metadata。

    核心功能：在切分之前生成地域、中文文种、主题、关键词和稳定文档 ID。
    输入：包含 ``task_id/file_title/md_content`` 的导入状态。
    输出：写入 ``document_metadata`` 后的状态。
    步骤：登记运行任务，调用 service，成功后登记完成并记录文档摘要。
    """
    task_id = str(state.get("task_id") or "-")
    add_running_task(task_id, NODE_NAME)
    result = extract_document_metadata(state)
    add_done_task(task_id, NODE_NAME)
    logger.info(
        f"文档 metadata 节点完成：document_id={result.get('document_id')}, "
        f"document_type={result.get('document_type')}"
    )
    return result
