"""旧 metadata 节点名称的兼容层。"""

from app.process.import_.agent.nodes.node_document_metadata import (
    node_document_metadata,
)
from app.process.import_.agent.state import ImportGraphState
from app.shared.runtime.logger import logger


def node_item_name_recognition(state: ImportGraphState) -> ImportGraphState:
    """转发旧节点调用，不再识别 ``item_name``。

    输入：旧调用方传入的导入状态。
    输出：完成文档 metadata 抽取的状态。
    步骤：记录废弃告警并调用新版 ``node_document_metadata``。
    """
    logger.warning(
        "node_item_name_recognition 已废弃，请迁移到 node_document_metadata"
    )
    return node_document_metadata(state)
