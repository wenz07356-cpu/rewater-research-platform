"""文档 chunk 向量化节点。"""

from app.process.import_.agent.state import ImportGraphState
from app.rag.import_.embedding_service import generate_chunk_embeddings
from app.shared.runtime.logger import logger, node_log
from app.shared.utils.task_utils import add_done_task, add_running_task


NODE_NAME = "node_bge_embedding"


@node_log(NODE_NAME)
def node_bge_embedding(state: ImportGraphState) -> ImportGraphState:
    """为全部文档 chunks 生成稠密和稀疏向量。

    核心功能：调用向量化 service，并保证任何批次失败都会终止导入。
    输入：包含已定稿 chunks 的导入状态。
    输出：每个 chunk 均写入双向量后的状态。
    步骤：登记运行，生成向量，登记完成并记录向量化数量。
    """
    task_id = str(state.get("task_id") or "-")
    add_running_task(task_id, NODE_NAME)
    result = generate_chunk_embeddings(state)
    add_done_task(task_id, NODE_NAME)
    logger.info(f"向量化节点完成：chunks={len(result.get('chunks') or [])}")
    return result
