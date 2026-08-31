"""文档 chunks 写入 Milvus 的图节点。"""

from app.process.import_.agent.state import ImportGraphState
from app.rag.import_.index_service import index_chunks
from app.shared.runtime.logger import logger, node_log
from app.shared.utils.task_utils import add_done_task, add_running_task


NODE_NAME = "node_import_milvus"


@node_log(NODE_NAME)
def node_import_milvus(state: ImportGraphState) -> ImportGraphState:
    """幂等写入单篇文档的全部 chunks。

    核心功能：调用索引 service 完成预校验、upsert 和失效旧块清理。
    输入：包含已向量化 chunks 的导入状态。
    输出：索引完成后的状态。
    步骤：登记运行，执行入库，成功后登记完成并记录 document_id。
    """
    task_id = str(state.get("task_id") or "-")
    add_running_task(task_id, NODE_NAME)
    result = index_chunks(state)
    add_done_task(task_id, NODE_NAME)
    logger.info(f"Milvus 入库节点完成：document_id={result.get('document_id')}")
    return result
