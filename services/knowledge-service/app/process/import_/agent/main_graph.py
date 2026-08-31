"""文档导入 LangGraph 编排。"""

from langgraph.graph import END, StateGraph

from app.process.import_.agent.nodes.node_bge_embedding import node_bge_embedding
from app.process.import_.agent.nodes.node_document_metadata import (
    node_document_metadata,
)
from app.process.import_.agent.nodes.node_document_split import node_document_split
from app.process.import_.agent.nodes.node_entry import node_entry
from app.process.import_.agent.nodes.node_import_milvus import node_import_milvus
from app.process.import_.agent.nodes.node_md_img import node_md_img
from app.process.import_.agent.nodes.node_pdf_to_md import node_pdf_to_md
from app.process.import_.agent.state import ImportGraphState
from app.shared.runtime.logger import logger


def node_entry_after(state: ImportGraphState) -> str:
    """根据入口识别出的文件类型选择下一节点。

    输入：入口节点更新后的状态。
    输出：Markdown 图片节点、PDF 解析节点或 ``END``。
    步骤：优先检查 Markdown 开关，再检查 PDF 开关；均未开启时告警结束。
    """
    file_path = state.get("local_file_path")
    if state.get("is_md_read_enabled", False):
        logger.info(f"文件已识别为 Markdown：{file_path}")
        return "node_md_img"
    if state.get("is_pdf_read_enabled", False):
        logger.info(f"文件已识别为 PDF：{file_path}")
        return "node_pdf_to_md"
    logger.warning(f"文件类型不受支持，导入流程结束：{file_path}")
    return END


def build_import_graph():
    """构建并编译文档导入图。

    核心功能：集中声明节点与边，保证 metadata、切分、向量化和索引顺序一致。
    输入：无。
    输出：已编译、可 invoke/stream 的 LangGraph 应用。
    步骤：注册节点，设置入口和类型路由，再连接静态处理链。
    """
    builder = StateGraph(ImportGraphState)
    builder.add_node("node_entry", node_entry)
    builder.add_node("node_pdf_to_md", node_pdf_to_md)
    builder.add_node("node_md_img", node_md_img)
    builder.add_node("node_document_metadata", node_document_metadata)
    builder.add_node("node_document_split", node_document_split)
    builder.add_node("node_bge_embedding", node_bge_embedding)
    builder.add_node("node_import_milvus", node_import_milvus)
    builder.set_entry_point("node_entry")

    builder.add_conditional_edges(
        "node_entry",
        node_entry_after,
        {
            "node_md_img": "node_md_img",
            "node_pdf_to_md": "node_pdf_to_md",
            END: END,
        },
    )
    builder.add_edge("node_pdf_to_md", "node_md_img")
    builder.add_edge("node_md_img", "node_document_metadata")
    builder.add_edge("node_document_metadata", "node_document_split")
    builder.add_edge("node_document_split", "node_bge_embedding")
    builder.add_edge("node_bge_embedding", "node_import_milvus")
    builder.add_edge("node_import_milvus", END)
    return builder.compile()


import_app = build_import_graph()
