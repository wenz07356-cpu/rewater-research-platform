from pathlib import Path

from app.shared.runtime.logger import logger, step_log
from app.process.import_.agent.state import ImportGraphState


# 常量抽离，便于后续维护
SUPPORT_MD_SUFFIX = ".md"
SUPPORT_PDF_SUFFIX = ".pdf"
NODE_NAME = "node_entry"


@step_log("resolve_input_file")
def resolve_input_file(state: ImportGraphState) -> ImportGraphState:
    """
    文件类型识别与状态初始化节点（导入流程入口）
    核心功能：根据本地文件路径识别文件类型，自动装配对应状态字段，为后续流程路由提供依据

    业务逻辑：
        1. 校验文件路径非空且文件真实存在
        2. 根据后缀识别 MD / PDF 文件（不区分大小写）
        3. 自动填充对应路径、路由开关、文件标题
        4. 不支持的文件类型记录告警并返回
    Args:
        state: 导入流程全局状态，必须包含 local_file_path 字段
    Returns:
        ImportGraphState: 状态增量字典，仅返回发生变化的字段
    """

    # 1. 获取并校验文件路径
    local_file_path = state.get("local_file_path")
    if not local_file_path:
        logger.error(f"节点:{NODE_NAME}, 文件路径为空，终止导入流程")
        raise ValueError("文件路径不能为空")

    file_path = Path(local_file_path)
    if not file_path.exists() or not file_path.is_file():
        logger.error(f"节点:{NODE_NAME}, 文件不存在或不是有效文件: {local_file_path}")
        raise FileNotFoundError(f"文件不存在: {local_file_path}")

    # 2. 识别文件类型（不区分大小写）
    suffix = file_path.suffix.lower()

    if suffix == SUPPORT_MD_SUFFIX:
        state["md_path"] = local_file_path
        state["is_md_read_enabled"] = True
        state["is_pdf_read_enabled"] = False

    elif suffix == SUPPORT_PDF_SUFFIX:
        state["pdf_path"] = local_file_path
        state["is_pdf_read_enabled"] = True
        state["is_md_read_enabled"] = False

    else:
        logger.warning(f"节点:{NODE_NAME}, 不支持的文件类型: {local_file_path}，终止流程")
        return state

    # 3. 提取文件标题
    state["file_title"] = file_path.stem


    # 返回增量，由LangGraph自动合并到全局状态
    return state