"""通用 Markdown 文档切分服务。

所有文种统一按 Markdown 标题建立结构边界。普通文本、表格和 fenced code block
分别细化；文种 metadata 不参与切分策略选择。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from app.rag.import_.config import (
    CHUNK_BACKUP_ENABLED,
    CHUNK_MAX_SIZE,
    CHUNK_MIN,
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    CODE_MAX_SIZE,
    TABLE_MAX_SIZE,
)
from app.rag.import_.item_name_service import (
    apply_document_metadata,
    extract_document_metadata,
    validate_document_metadata,
)
from app.shared.runtime.logger import logger, step_log


_MD_HEADING_RE = re.compile(r"^\s*(#{1,6})\s+(.+?)\s*$")
_MARKDOWN_TABLE_SEPARATOR_RE = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$"
)
_TABLE_CAPTION_RE = re.compile(
    r"^\s*(?:表|Table|Tab\.)\s*[A-Za-z0-9一二三四五六七八九十.-]+.*$",
    re.IGNORECASE,
)
_CODE_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
_HTML_ROW_RE = re.compile(r"<tr\b[^>]*>.*?</tr\s*>", re.IGNORECASE | re.DOTALL)


@step_log("load_markdown_content")
def load_markdown_content(state: dict[str, Any]) -> tuple[str, str]:
    """加载并规范化待切分 Markdown。

    核心功能：从状态正文或文件路径取得内容，并确定非空文件标题。
    输入：可能包含 ``md_content/md_path/file_title`` 的导入状态。
    输出：规范化正文和文件标题。
    步骤：优先读取状态正文，必要时读取文件，校验非空，统一换行并写回状态。
    """
    md_content = state.get("md_content")
    md_path = state.get("md_path")
    if not md_content and md_path:
        path = Path(str(md_path))
        if path.is_file():
            md_content = path.read_text(encoding="utf-8")
            logger.info(f"已从文件加载待切分 Markdown：{path}")
        else:
            logger.error(f"md_path 不存在或不是文件：{path}")

    if not isinstance(md_content, str) or not md_content.strip():
        logger.error("md_content 为空，无法执行文档切分")
        raise ValueError("md_content 为空，无法执行文档切分")

    file_title = str(
        state.get("file_title")
        or (Path(str(md_path)).stem if md_path else "未命名文档")
    ).strip()
    normalized = (
        md_content.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    )
    state["md_content"] = normalized
    state["file_title"] = file_title
    return normalized, file_title


def _clean_heading(text: str) -> str:
    """清理 Markdown 标题文本。

    核心功能：移除闭合井号并压缩无意义空白。
    输入：标题正文。
    输出：可用于展示的标题；清理后为空时返回“未命名章节”。
    步骤：移除尾部井号、清理 HTML 标签、压缩空白并设置兜底值。
    """
    cleaned = re.sub(r"\s+#+\s*$", "", text).strip()
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "未命名章节"


def _set_section_path(path: list[str], level: int, title: str) -> list[str]:
    """按标题层级更新章节路径。

    核心功能：保留父级路径并替换当前及更低层级。
    输入：当前路径、1～6 级标题层级和新标题。
    输出：不修改原列表的新章节路径。
    步骤：限制层级范围，截取父路径并追加新标题。
    """
    normalized_level = min(max(level, 1), 6)
    return [*path[: normalized_level - 1], title]


def _is_markdown_table(lines: list[str], index: int) -> bool:
    """判断指定位置是否为 Markdown 表格起点。

    输入：全文行列表和当前索引。
    输出：当前行是否为“表头 + 分隔行”结构。
    步骤：检查下一行存在、当前行含竖线且下一行匹配分隔行语法。
    """
    return (
        index + 1 < len(lines)
        and "|" in lines[index]
        and bool(_MARKDOWN_TABLE_SEPARATOR_RE.match(lines[index + 1]))
    )


def _consume_markdown_table(
    lines: list[str],
    index: int,
) -> tuple[list[str], int]:
    """读取一个连续 Markdown 表格。

    输入：全文行列表和表头索引。
    输出：表格原始行、下一待处理索引。
    步骤：收集表头及分隔行，再读取所有连续、非空且含竖线的数据行。
    """
    table_lines = [lines[index], lines[index + 1]]
    index += 2
    while index < len(lines) and lines[index].strip() and "|" in lines[index]:
        table_lines.append(lines[index])
        index += 1
    return table_lines, index


def _consume_html_table(
    lines: list[str],
    index: int,
) -> tuple[list[str], int]:
    """读取从 ``<table`` 到 ``</table>`` 的 HTML 表格。

    输入：全文行列表和表格起始索引。
    输出：表格原始行、下一待处理索引。
    步骤：逐行收集并查找闭合标签；未闭合时保留内容并记录告警。
    """
    table_lines: list[str] = []
    closed = False
    while index < len(lines):
        table_lines.append(lines[index])
        index += 1
        if "</table>" in table_lines[-1].lower():
            closed = True
            break
    if not closed:
        logger.warning("检测到未闭合 HTML 表格，已保留至文档末尾")
    return table_lines, index


def _consume_fenced_code(
    lines: list[str],
    index: int,
) -> tuple[list[str], int]:
    """读取一个完整 fenced code block。

    输入：全文行列表和围栏起始索引。
    输出：含围栏的代码行、下一待处理索引。
    步骤：记录围栏字符与长度，读取到匹配闭合围栏；未闭合时记录告警。
    """
    opening = _CODE_FENCE_RE.match(lines[index])
    if opening is None:
        raise ValueError("当前索引不是 fenced code block 起点")
    marker = opening.group(1)
    closing_re = re.compile(
        rf"^\s*{re.escape(marker[0])}{{{len(marker)},}}\s*$"
    )
    code_lines = [lines[index]]
    index += 1
    closed = False
    while index < len(lines):
        code_lines.append(lines[index])
        if closing_re.match(lines[index]):
            index += 1
            closed = True
            break
        index += 1
    if not closed:
        logger.warning("检测到未闭合代码围栏，已保留至文档末尾")
    return code_lines, index


def _parse_markdown_blocks(
    md_content: str,
    file_title: str,
) -> list[dict[str, Any]]:
    """按通用 Markdown 结构解析初始 blocks。

    核心功能：识别标题、表格、代码和普通文本，不使用任何文种专属规则。
    输入：规范化 Markdown 和文件标题。
    输出：按原文顺序排列的内部 block 列表。
    步骤：逐行扫描；代码和表格优先，标题更新路径，普通行累计后按边界刷新。
    """
    lines = md_content.splitlines()
    blocks: list[dict[str, Any]] = []
    section_path: list[str] = []
    section_title = file_title
    heading_level: int | None = None
    current_lines: list[str] = []

    def append_block(
        content: str,
        context_type: str,
        *,
        title: str | None = None,
    ) -> None:
        """把非空内容连同当前章节上下文追加到内部列表。"""
        normalized_content = content.strip()
        if not normalized_content:
            return
        blocks.append(
            {
                "content": normalized_content,
                "context_type": context_type,
                "section_path": section_path.copy(),
                "section_title": title or section_title,
                "heading_level": heading_level,
                "part_index": 0,
            }
        )

    def flush_text() -> None:
        """刷新闭包中累计的普通文本行。"""
        nonlocal current_lines
        append_block("\n".join(current_lines), "text")
        current_lines = []

    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if _CODE_FENCE_RE.match(line):
            flush_text()
            code_lines, index = _consume_fenced_code(lines, index)
            append_block("\n".join(code_lines), "code")
            continue

        is_html_table = "<table" in stripped.lower()
        is_markdown_table = _is_markdown_table(lines, index)
        if is_html_table or is_markdown_table:
            caption: str | None = None
            while current_lines and not current_lines[-1].strip():
                current_lines.pop()
            if current_lines and _TABLE_CAPTION_RE.match(current_lines[-1]):
                caption = current_lines.pop().strip()
            flush_text()
            table_lines, index = (
                _consume_html_table(lines, index)
                if is_html_table
                else _consume_markdown_table(lines, index)
            )
            table_content = "\n".join(
                ([caption] if caption else []) + table_lines
            )
            append_block(table_content, "table", title=caption)
            continue

        heading = _MD_HEADING_RE.match(line)
        if heading:
            flush_text()
            heading_level = len(heading.group(1))
            section_title = _clean_heading(heading.group(2))
            section_path = _set_section_path(
                section_path,
                heading_level,
                section_title,
            )
            current_lines = [line]
        else:
            current_lines.append(line)
        index += 1

    flush_text()
    if blocks:
        return blocks
    return [
        {
            "content": md_content.strip(),
            "context_type": "text",
            "section_path": [],
            "section_title": file_title,
            "heading_level": None,
            "part_index": 0,
        }
    ]


def split_by_titles(md_content: str, file_title: str) -> list[dict[str, Any]]:
    """提供按 Markdown 标题初切的公开入口。

    核心功能：统一所有文种的初步结构切分。
    输入：Markdown 正文和文件标题。
    输出：尚未进行长度细化的 blocks。
    步骤：校验参数并调用 ``_parse_markdown_blocks``；不接收文种参数。
    """
    if not isinstance(md_content, str) or not md_content.strip():
        raise ValueError("md_content 不能为空")
    if not isinstance(file_title, str) or not file_title.strip():
        raise ValueError("file_title 不能为空")
    return _parse_markdown_blocks(md_content, file_title.strip())


def _split_oversized_unit(text: str, target_size: int) -> list[str]:
    """把长文本拆成不超过目标长度的小语义单元。

    输入：连续文本和目标字符数。
    输出：保持原顺序的非空单元。
    步骤：先按句末标点和换行切分，单句仍过长时使用字符窗口硬切。
    """
    if target_size <= 0:
        raise ValueError("target_size 必须大于 0")
    if len(text) <= target_size:
        return [text]

    sentences = [
        part.strip()
        for part in re.split(r"(?<=[。！？；.!?;])\s*|\n+", text)
        if part.strip()
    ]
    units: list[str] = []
    for sentence in sentences:
        units.extend(
            sentence[position : position + target_size]
            for position in range(0, len(sentence), target_size)
        )
    return units


def _split_text_block(
    block: dict[str, Any],
    target_size: int,
    max_size: int,
    overlap: int,
) -> list[dict[str, Any]]:
    """对超长普通文本做段落和句子级细切。

    输入：文本 block、目标长度、最大长度和重叠长度。
    输出：保留章节 metadata 的文本子块。
    步骤：拆语义单元，组合到目标长度，为后续块增加有限 overlap 和标题上下文。
    """
    content = str(block.get("content") or "").strip()
    if len(content) <= max_size:
        return [block.copy()]

    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", content)
        if paragraph.strip()
    ]
    units: list[str] = []
    for paragraph in paragraphs:
        units.extend(_split_oversized_unit(paragraph, target_size))

    pieces: list[str] = []
    current = ""
    for unit in units:
        candidate = f"{current}\n\n{unit}" if current else unit
        if current and len(candidate) > target_size:
            pieces.append(current)
            prefix = current[-overlap:] if overlap > 0 else ""
            current = f"{prefix}\n{unit}".strip() if prefix else unit
        else:
            current = candidate
    if current:
        pieces.append(current)

    heading_line = ""
    first_line = content.splitlines()[0] if content.splitlines() else ""
    if _MD_HEADING_RE.match(first_line):
        heading_line = first_line

    expanded_pieces: list[str] = []
    for source_index, piece in enumerate(pieces):
        if source_index > 0 and heading_line and not piece.startswith(heading_line):
            available = max_size - len(heading_line) - 1
            if available > 0:
                expanded_pieces.extend(
                    f"{heading_line}\n{sub_piece}"
                    for sub_piece in _split_oversized_unit(piece, available)
                )
                continue
            logger.warning("Markdown 标题本身过长，后续文本块不再重复标题行")
        expanded_pieces.extend(_split_oversized_unit(piece, max_size))

    result: list[dict[str, Any]] = []
    for part_index, piece in enumerate(expanded_pieces):
        child = block.copy()
        child["content"] = piece
        child["part_index"] = part_index
        result.append(child)
    return result


def _split_markdown_table(
    block: dict[str, Any],
    max_size: int,
) -> list[dict[str, Any]]:
    """按数据行拆分 Markdown 表格，并在每块重复表名和表头。"""
    lines = str(block["content"]).splitlines()
    separator_index = next(
        (
            index
            for index, line in enumerate(lines)
            if _MARKDOWN_TABLE_SEPARATOR_RE.match(line)
        ),
        None,
    )
    if separator_index is None or separator_index == 0:
        logger.warning("超长表格无法识别 Markdown 表头，将保持原块")
        return [block.copy()]

    header = lines[: separator_index + 1]
    rows = lines[separator_index + 1 :]
    pieces: list[dict[str, Any]] = []
    current = header.copy()
    for row in rows:
        candidate = "\n".join([*current, row])
        if len(candidate) > max_size and len(current) > len(header):
            child = block.copy()
            child["content"] = "\n".join(current)
            child["part_index"] = len(pieces)
            pieces.append(child)
            current = header.copy()
        current.append(row)
        if len("\n".join(current)) > max_size and len(current) == len(header) + 1:
            logger.warning("Markdown 表格存在超过长度上限的单行，已完整保留")
    if len(current) > len(header):
        child = block.copy()
        child["content"] = "\n".join(current)
        child["part_index"] = len(pieces)
        pieces.append(child)
    return pieces or [block.copy()]


def _split_html_table(
    block: dict[str, Any],
    max_size: int,
) -> list[dict[str, Any]]:
    """按 ``tr`` 拆分 HTML 表格，并保持每个子表闭合。"""
    content = str(block["content"])
    rows = list(_HTML_ROW_RE.finditer(content))
    if not rows:
        logger.warning("超长 HTML 表格无法识别 tr 行，将保持原块")
        return [block.copy()]

    prefix = content[: rows[0].start()]
    suffix = content[rows[-1].end() :]
    header_rows = [match.group(0) for match in rows if "<th" in match.group(0).lower()]
    data_rows = [match.group(0) for match in rows if match.group(0) not in header_rows]
    base = prefix + "".join(header_rows)
    pieces: list[dict[str, Any]] = []
    current_rows: list[str] = []
    for row in data_rows:
        candidate = base + "".join([*current_rows, row]) + suffix
        if len(candidate) > max_size and current_rows:
            child = block.copy()
            child["content"] = base + "".join(current_rows) + suffix
            child["part_index"] = len(pieces)
            pieces.append(child)
            current_rows = []
        current_rows.append(row)
        if len(base + row + suffix) > max_size:
            logger.warning("HTML 表格存在超过长度上限的单行，已完整保留")
    if current_rows or not data_rows:
        child = block.copy()
        child["content"] = base + "".join(current_rows) + suffix
        child["part_index"] = len(pieces)
        pieces.append(child)
    return pieces


def _split_table_block(
    block: dict[str, Any],
    max_size: int,
) -> list[dict[str, Any]]:
    """调度 Markdown 或 HTML 表格细切。

    输入：表格 block 和最大字符数。
    输出：可独立理解的表格子块。
    步骤：短表原样返回；HTML 按 tr、Markdown 按数据行切分并重复表头。
    """
    content = str(block.get("content") or "")
    if len(content) <= max_size:
        return [block.copy()]
    if "<table" in content.lower():
        return _split_html_table(block, max_size)
    return _split_markdown_table(block, max_size)


def _split_code_block(
    block: dict[str, Any],
    max_size: int,
) -> list[dict[str, Any]]:
    """按完整代码行拆分超长 fenced code block。

    输入：代码 block 和最大字符数。
    输出：每个子块都带起止围栏的代码 blocks。
    步骤：提取围栏和正文，逐行组合；代码块之间不增加 overlap。
    """
    content = str(block.get("content") or "")
    if len(content) <= max_size:
        return [block.copy()]
    lines = content.splitlines()
    if len(lines) < 2 or _CODE_FENCE_RE.match(lines[0]) is None:
        logger.warning("超长代码块缺少有效围栏，将按行窗口切分")
        opening, closing, body = "```", "```", lines
    else:
        opening = lines[0]
        fence = _CODE_FENCE_RE.match(opening).group(1)
        expected_close = re.compile(
            rf"^\s*{re.escape(fence[0])}{{{len(fence)},}}\s*$"
        )
        if expected_close.match(lines[-1]):
            closing, body = lines[-1], lines[1:-1]
        else:
            closing, body = fence, lines[1:]

    pieces: list[dict[str, Any]] = []
    current: list[str] = []
    for line in body:
        candidate = "\n".join([opening, *current, line, closing])
        if len(candidate) > max_size and current:
            child = block.copy()
            child["content"] = "\n".join([opening, *current, closing])
            child["part_index"] = len(pieces)
            pieces.append(child)
            current = []
        current.append(line)
        if len("\n".join([opening, line, closing])) > max_size:
            logger.warning("代码块存在超过长度上限的单行，已完整保留")
    if current:
        child = block.copy()
        child["content"] = "\n".join([opening, *current, closing])
        child["part_index"] = len(pieces)
        pieces.append(child)
    return pieces or [block.copy()]


def _same_top_level(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """判断两个 block 是否可在同一一级标题范围内合并。"""
    left_path = left.get("section_path") or []
    right_path = right.get("section_path") or []
    if not left_path and not right_path:
        return True
    return bool(left_path and right_path and left_path[0] == right_path[0])


def _merge_short_blocks(
    blocks: list[dict[str, Any]],
    min_size: int,
    max_size: int,
) -> list[dict[str, Any]]:
    """合并兼容的相邻短文本块。

    输入：细切 blocks、短块阈值和最大长度。
    输出：保持原顺序的合并结果。
    步骤：只合并文本；同章节允许吸收短尾块，跨章节仅合并同一级标题下的两个短块。
    """
    merged: list[dict[str, Any]] = []
    for block in blocks:
        if not merged:
            merged.append(block.copy())
            continue
        previous = merged[-1]
        if previous.get("context_type") != "text" or block.get("context_type") != "text":
            merged.append(block.copy())
            continue

        previous_content = str(previous.get("content") or "")
        current_content = str(block.get("content") or "")
        combined = f"{previous_content}\n\n{current_content}".strip()
        same_section = previous.get("section_path") == block.get("section_path")
        both_short = len(previous_content) < min_size and len(current_content) < min_size
        may_merge = (
            same_section
            or (both_short and _same_top_level(previous, block))
        )
        if may_merge and len(combined) <= max_size:
            previous["content"] = combined
            if previous.get("section_title") != block.get("section_title"):
                titles = [
                    title
                    for title in (
                        previous.get("section_title"),
                        block.get("section_title"),
                    )
                    if title
                ]
                previous["section_title"] = "；".join(dict.fromkeys(titles))
                previous["section_path"] = (
                    previous.get("section_path") or []
                )[:-1]
            continue
        merged.append(block.copy())
    return merged


def refine_chunks(
    sections: list[dict[str, Any]],
    max_len: int = CHUNK_MAX_SIZE,
    min_len: int = CHUNK_MIN,
) -> list[dict[str, Any]]:
    """按内容类型细切并合并短 blocks。

    输入：标题初切结果、最大长度和短块阈值。
    输出：待定稿的 blocks。
    步骤：分别调度 text/table/code 处理器，未知类型报错，最后合并短文本。
    """
    refined: list[dict[str, Any]] = []
    for index, section in enumerate(sections):
        context_type = section.get("context_type")
        if context_type == "text":
            refined.extend(
                _split_text_block(
                    section,
                    min(CHUNK_SIZE, max_len),
                    max_len,
                    CHUNK_OVERLAP,
                )
            )
        elif context_type == "table":
            refined.extend(_split_table_block(section, min(TABLE_MAX_SIZE, max_len)))
        elif context_type == "code":
            refined.extend(_split_code_block(section, min(CODE_MAX_SIZE, max_len)))
        else:
            logger.error(f"section[{index}] context_type 不合法：{context_type}")
            raise ValueError(f"不支持的 context_type：{context_type}")
    return _merge_short_blocks(refined, min_len, max_len)


def estimate_token_count(text: str) -> int:
    """轻量估算中英文混合文本 token 数量。

    输入：最终 chunk 正文。
    输出：非负启发式 token 数。
    步骤：汉字、连续英文数字串及非空白符号分别计数。
    """
    return len(re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9]+|[^\s]", text))


def _build_embedding_text(
    chunk: dict[str, Any],
    metadata: dict[str, Any],
    file_title: str,
) -> str:
    """构造供向量化使用的上下文增强文本。

    输入：chunk、文档 metadata 和文件标题。
    输出：标题、分类、地域、主题、关键词和正文组成的文本。
    步骤：跳过空字段，列表用顿号连接，正文始终置于最后。
    """
    parts: list[str] = [file_title]
    section_title = str(chunk.get("section_title") or "").strip()
    if section_title and section_title != file_title:
        parts.append(section_title)
    parts.append(metadata["document_type"])
    for field in ("region_names", "topics", "keywords"):
        values = metadata.get(field) or []
        if values:
            parts.append("、".join(values))
    parts.append(str(chunk["content"]))
    return "\n".join(item for item in parts if item)


def _build_chunk_id(document_id: str, chunk_index: int) -> str:
    """根据文档 ID 和顺序生成稳定 chunk 主键。

    输入：64 位文档 ID 和非负 chunk 顺序。
    输出：64 位 SHA-256 十六进制字符串。
    步骤：校验参数，拼接稳定身份串并计算摘要；正文更新不改变同序号主键。
    """
    if not document_id or chunk_index < 0:
        raise ValueError("document_id 不能为空且 chunk_index 必须非负")
    identity = f"{document_id}|{chunk_index}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _finalize_chunks(
    blocks: list[dict[str, Any]],
    metadata: dict[str, Any],
    file_title: str,
) -> list[dict[str, Any]]:
    """把内部 blocks 转换为最终 chunks。

    输入：细化 blocks、完整文档 metadata 和文件标题。
    输出：包含业务字段、稳定 ID、token 统计及临时向量文本的 chunks。
    步骤：跳过空块，连续编号，生成 chunk 字段，再统一下沉文档 metadata。
    """
    normalized_metadata = validate_document_metadata(metadata)
    chunks: list[dict[str, Any]] = []
    for block in blocks:
        content = str(block.get("content") or "").strip()
        if not content:
            continue
        chunk_index = len(chunks)
        section_title = str(block.get("section_title") or file_title).strip()
        chunk = {
            "chunk_id": _build_chunk_id(
                normalized_metadata["document_id"],
                chunk_index,
            ),
            "document_id": normalized_metadata["document_id"],
            "chunk_index": chunk_index,
            "file_title": file_title,
            "section_title": section_title or file_title,
            "content": content,
            "context_type": block["context_type"],
            "token_count": estimate_token_count(content),
        }
        chunk["embedding_text"] = _build_embedding_text(
            chunk,
            normalized_metadata,
            file_title,
        )
        chunks.append(chunk)
    return apply_document_metadata(chunks, normalized_metadata)


@step_log("backup_chunks")
def backup_chunks(chunks: list[dict[str, Any]], md_path: str | None) -> None:
    """保存可选的切块诊断文件。

    输入：最终 chunks 和源 Markdown 路径。
    输出：无；成功时生成 ``*.chunks.json``。
    步骤：无路径或关闭配置时跳过；写入失败只记录 warning，不中断主导入。
    """
    if not CHUNK_BACKUP_ENABLED or not md_path:
        return
    path = Path(md_path)
    backup_path = path.with_name(f"{path.stem}.chunks.json")
    try:
        backup_path.write_text(
            json.dumps(chunks, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"切块诊断文件已保存：{backup_path}")
    except OSError as exc:
        logger.warning(f"切块诊断文件保存失败，不影响主流程：{exc}")


@step_log("split_document")
def split_document(state: dict[str, Any]) -> dict[str, Any]:
    """执行完整 Markdown 切分流程并更新状态。

    核心功能：串联加载、metadata 校验、标题初切、内容细化和 chunk 定稿。
    输入：包含正文/路径、标题及通常已抽取 metadata 的导入状态。
    输出：写入 ``state['chunks']`` 后的原状态。
    步骤：缺 metadata 时兼容抽取，统一切分，生成最终字段，备份并记录类型统计。
    """
    md_content, file_title = load_markdown_content(state)
    if not state.get("document_metadata"):
        logger.warning("split_document 未收到 metadata，将立即调用大模型抽取")
        extract_document_metadata(state)
    metadata = validate_document_metadata(state["document_metadata"])

    sections = split_by_titles(md_content, file_title)
    blocks = refine_chunks(sections)
    chunks = _finalize_chunks(blocks, metadata, file_title)
    if not chunks:
        logger.error("文档切分结果为空")
        raise ValueError("文档切分结果为空")

    backup_chunks(chunks, state.get("md_path"))
    state["chunks"] = chunks
    type_counts = {
        context_type: sum(
            chunk["context_type"] == context_type for chunk in chunks
        )
        for context_type in ("text", "table", "code")
    }
    logger.info(
        f"Markdown 切分完成：file_title={file_title}, "
        f"chunks={len(chunks)}, context_types={type_counts}"
    )
    return state
