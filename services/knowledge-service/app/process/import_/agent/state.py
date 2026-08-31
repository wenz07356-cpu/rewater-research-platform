"""导入 LangGraph 的状态契约与默认值。"""

from __future__ import annotations

import copy
from typing import Any, TypedDict


class ImportGraphState(TypedDict, total=False):
    """导入流程各节点共享的可选状态字段。"""

    task_id: str | None
    local_dir: str | None
    local_file_path: str | None
    is_md_read_enabled: bool
    is_pdf_read_enabled: bool
    file_title: str | None
    pdf_path: str | None
    md_path: str | None
    md_content: str | None
    document_metadata: dict[str, Any] | None
    document_id: str | None
    document_type: str | None
    chunks: list[dict[str, Any]] | None


graph_default_state: ImportGraphState = {
    "task_id": None,
    "local_dir": None,
    "local_file_path": None,
    "is_md_read_enabled": False,
    "is_pdf_read_enabled": False,
    "file_title": None,
    "pdf_path": None,
    "md_path": None,
    "md_content": None,
    "document_metadata": None,
    "document_id": None,
    "document_type": None,
    "chunks": None,
}


def create_default_state(**overrides: Any) -> ImportGraphState:
    """创建互不共享可变字段的默认导入状态。

    核心功能：为 API 和本地测试提供统一状态初始化入口。
    输入：需要覆盖或补充的状态键值。
    输出：深拷贝后的新 ``ImportGraphState``。
    步骤：复制默认状态，再用调用方参数覆盖对应字段。
    """
    state = copy.deepcopy(graph_default_state)
    state.update(overrides)
    return state


def get_default_state() -> ImportGraphState:
    """返回新的默认状态副本，避免跨请求污染。"""
    return copy.deepcopy(graph_default_state)
