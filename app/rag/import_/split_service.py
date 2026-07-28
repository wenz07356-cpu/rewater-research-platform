"""
文档切块服务模块，负责 Markdown 清洗、标题切分与二次细分。
"""
import json
import re
from pathlib import Path
from typing import Any, Dict

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.shared.runtime.logger import logger, step_log
from app.rag.import_.config import CHUNK_MAX_SIZE, CHUNK_SIZE, CHUNK_OVERLAP, CHUNK_MIN


@step_log("load_markdown_content")
def load_markdown_content(state: dict) -> tuple[str, str]:
    """
    参数校验和获取
    :param state:
    :return:
    """
    md_content = state.get("md_content")
    file_title = state.get("file_title")
    md_path = state.get("md_path")

    if not md_content:
        logger.warning("没有从state读取到md_content内容,我们使用md_path尝试再次读取!")
        if md_path and Path(md_path).exists():
            logger.warning(f"md_content内容为空，从备份地址：{md_path}再次读取数据！！")
            md_content = Path(md_path).read_text(encoding="utf-8")
            state["md_content"] = md_content
        if not md_content:
            logger.error(f"md_content为空，尝试从md_path拉取失败，业务无法进行，提前终止")
            raise ValueError(f"md_content为空，尝试从md_path拉取失败，业务无法进行，提前终止")

    if not file_title:
        if md_path and Path(md_path).exists():
            file_title = Path(md_path).stem
        if not file_title:
            file_title = "default"
        state["file_title"] = file_title
        logger.warning(f"file_title为空，启动默认值机制，赋值后：{file_title}")

    md_content = md_content.replace("\r\n", "\n").replace("\r", "\n")
    state["md_content"] = md_content
    return md_content, file_title


@step_log("split_by_titles")
def split_by_titles(md_content: str, file_title: str) -> list[dict[str, str]]:
    """
    根据Markdown标题对文档进行语义分块；
    重点考虑三个地方：代码串（不能删空行）、开头（没标题，赋值）、结尾（）。
    :param md_content: Markdown格式的文档内容
    :param file_title: 文档整体标题，用于前言内容的兜底标题
    :return: 分块列表，每个块包含 content、title、file_title 三个字段
    """

    # 正则
    title_pattern = re.compile(r"^\s*#{1,6}\s+.+")
    lines = md_content.split("\n")

    chunks: list[dict[str, str]] = []
    #状态变量
    current_title: str | None = None
    current_lines: list[str] = []
    in_code_block = False
    # 记录每个级别最后出现的标题，用于维护父子关系


    for raw_line in lines:
        # 仅用strip后的字符串做逻辑判断，原始行完整保留，不破坏格式
        stripped_line = raw_line.strip()

        # 1. 识别代码块边界，翻转状态
        if stripped_line.startswith("```") or stripped_line.startswith("~~~"):
            in_code_block = not in_code_block
            current_lines.append(raw_line)
            continue

        # 2. 仅跳过非代码块内的空行，代码块内空行完整保留
        if not stripped_line:
            current_lines.append(raw_line)
            continue

        # 3. 匹配到有效标题且不在代码块内：提交上一分块，开启新分块
        if title_pattern.match(stripped_line) and not in_code_block:
            # 提交上一个分块（包含第一个标题前的前言内容）
            if current_lines and len(current_lines) > 1:
                block_title = current_title if current_title else file_title
                chunks.append({
                    "content": "\n".join(current_lines),
                    "title": block_title,
                    "file_title": file_title,
                    "parent_title": block_title,
                })

            # 初始化新分块，保留原始标题行；如需纯标题可替换为 clean_title(stripped_line)
            current_title = stripped_line
            current_lines = [raw_line]
            continue

        # 4. 普通正文/代码块内容：直接追加原始行
        current_lines.append(raw_line)

    # 循环结束，提交最后一个分块
    if current_lines:
        block_title = current_title if current_title else file_title
        chunks.append({
            "content": "\n".join(current_lines),
            "title": block_title,
            "file_title": file_title,
            "parent_title": block_title,
        })

    # 极端兜底：无任何有效分块时返回默认块
    if not chunks:
        chunks.append({"content": md_content, "title": "default", "file_title": file_title})
        logger.warning(f"切割完成，触发兜底，分块数量1个")
    logger.info(f"完成语义切割，分块数量：{len(chunks)}，前3块标题：{[c['title'] for c in chunks[:3]]}")
    return chunks


def _split_long_section(section: dict[str, Any]) -> list[dict[str, Any]]:
    """
    【辅助函数】超长章节二次切分（核心适配LangChain分割器）
    功能：单个章节内容超限时，按「段落→句子→空格」从粗到细切分，保留语义
    切分规则：1.先按空行(段落) 2.再按换行 3.最后按中英文标点/空格
    :param section: 原始章节字典，必须包含content键，可选title/file_title等
    :return: 切分后的子章节列表，每个子章节带父标题/序号等元信息
    """
    # 内容空值兜底：无内容直接返回原章节
    content = section.get("content", "") or ""
    # 长度未超限，无需切分，直接返回原章节（列表格式保持统一）
    if len(content) <= CHUNK_MAX_SIZE:
        return [section]

    # 标准化预处理：统一换行符，避免不同系统(\r\n/\n)导致的切分异常
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    # 提取章节标题，用于组装子Chunk前缀（保留标题上下文）
    title = section.get("title", "") or ""
    # 标题前缀：带空行分隔，与正文区分开
    prefix = f"{title}\n\n" if title else ""
    # 计算正文可用长度：总长度 - 标题前缀长度（避免标题占满Chunk额度）
    available_len = CHUNK_MAX_SIZE - len(prefix)
    # 极端情况：标题长度超过阈值，无法切分，返回原章节
    if available_len <= 30:
        logger.warning(f"章节标题过长，无法切分：{title[:20]}...")
        return [section]

    # 清理正文重复标题：避免原章节中正文开头重复标题，导致子Chunk内容冗余
    body = content
    if title and body.lstrip().startswith(title):
        body = body[len(title):].lstrip()

    # 初始化LangChain递归分割器（核心工具：按优先级分隔符切分，保留语义）
    # separators：分割符优先级（从粗到细），优先按大语义单元切分，最后才硬拆
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE - len(prefix),  # 正文部分最大长度（已扣除标题）
        chunk_overlap=0,           # 无重叠：按标题切分后语义完整，无需重叠
        # 分割符优先级：空行(段落)→换行→中文标点→英文标点→空格，最后硬拆
        separators=["\n\n", "\n", "。", "！", "？", "；", ".", "!", "?", ";"],
    )

    # 切分正文并组装子章节（带完整元信息，便于溯源）
    sub_sections: list[dict[str, Any]] = []
    for idx, chunk in enumerate(splitter.split_text(body), start=1):
        # 清理空内容：跳过切分后的空字符串
        text = chunk.strip("\n")
        if not text:
           continue
        # 组装子Chunk完整内容：标题前缀 + 切分后的正文
        full_text = (prefix + text).strip("\n")
        # 子章节元信息：保留父级关联，添加序号，便于后续检索/溯源
        sub_sections.append({
            "title": f"{title}-{idx}" if title else f"chunk-{idx}",  # 子Chunk标题（带序号）
            "content": full_text,                                     # 切分后的完整内容
            "parent_title": title,                                    # 父章节标题（用于后续合并）
            "part": idx,                                              # 子Chunk序号
            "file_title": section.get("file_title"),                  # 所属文件标题
        })

    logger.debug(f"超长章节切分完成：{title} → 生成{len(sub_sections)}个子Chunk")
    return sub_sections

def _merge_short_sections(sections: list[dict[str, Any]],
    min_length: int = CHUNK_MIN,
    max_length: int = CHUNK_MAX_SIZE,
) -> list[dict[str, Any]]:

    """
    先指向一个基础（pre），作为参照！
    如果base小于300，尝试将后面的合并入。
    合并的前提：base < 300 同一个parent_title 合并后小于1000

    【辅助函数】过短章节合并（减少碎片化，提升检索效果）
    核心规则：仅合并「同父标题」且「当前块长度不足阈值」的相邻Chunk，避免跨章节合并
    :param sections: 待合并的Chunk列表（通常是_split_long_section切分后的结果）
    :param min_length: 最小长度阈值，低于此值的Chunk会被合并
    :return: 合并后的Chunk列表，长度适中，保留元信息
    """
    # 边界处理：空列表直接返回，避免后续索引报错
    if not sections:
        logger.debug("待合并Chunk列表为空，直接返回")
        return []

    merged_sections: list[dict[str, Any]] = []  # 最终合并结果
    current_chunk: dict[str, Any] | None = None  # 迭代累加器：保存当前待合并的Chunk

    for sec in sections:
        # 初始化：第一个Chunk直接作为当前待合并块
        if current_chunk is None:
            current_chunk = sec
            logger.info(f"短合并第一次进入，设置base_chunk内容！")
            continue

        # 合并条件：1.当前块长度不足阈值 2.与下一块同父标题（同属一个原章节）
        current_content = current_chunk.get("content", "")
        is_current_short = len(current_content) < min_length
        is_same_parent = current_chunk.get("parent_title") == sec.get("parent_title")

        if is_current_short and is_same_parent:
            # 合并前清理：去掉下一块开头重复的父标题，避免内容冗余
            parent_title = sec.get("parent_title", "")
            next_content = sec["content"]
            if parent_title and next_content.startswith(parent_title):
                next_content = next_content[len(parent_title):].lstrip()
            # 合并时额外校验长度，避免“先切短再合并”后重新超过最大阈值。
            merged_content = current_content + "\n\n" + next_content
            will_exceed_max = max_length > 0 and len(merged_content) > max_length
            if will_exceed_max:
                merged_sections.append(current_chunk)
                current_chunk = sec
                continue

            # 合并内容：空行分隔，保证格式整洁
            current_chunk["content"] = merged_content
            # 更新子Chunk序号：保留最新序号，便于溯源
            if "part" in sec:
                current_chunk["part"] = sec["part"]
            logger.debug(f"合并短Chunk：{current_chunk.get('parent_title')} → 累计长度{len(current_chunk['content'])}")
        else:
            # 不满足合并条件：将当前块加入结果，切换为新的待合并块
            merged_sections.append(current_chunk)
            current_chunk = sec

    # 循环结束后，将最后一个待合并块加入结果
    if current_chunk is not None:
        merged_sections.append(current_chunk)

    logger.debug(f"短Chunk合并完成：原{len(sections)}个 → 合并后{len(merged_sections)}个")
    return merged_sections

@step_log("refine_chunks")
def refine_chunks(
    sections: list[dict],
    max_len: int = CHUNK_MAX_SIZE,
    min_len: int = CHUNK_MIN,
) -> list[dict]:
    """
        【步骤4】Chunk精细化处理（核心：长切短合，适配大模型/检索）
        执行流程：1.切分超长章节 2.合并过短章节 3.父标题兜底（适配Milvus向量库schema）
        :param sections: 步骤3处理后的章节列表
        :param max_len: 单个Chunk最大字符长度
        :return: 长度适中、低碎片化的最终Chunk列表
    """
    # 边界处理：最大长度无效（空/≤0），直接返回原章节，避免切分异常
    if not max_len or max_len <= 0:
        logger.warning(f"步骤4：Chunk最大长度配置无效（{max_len}），跳过精细化处理")
        return sections

    # 阶段1：切分超长章节 → 所有章节长度控制在max_len内
    refined_split = []
    for sec in sections:
        # 对每个章节执行超长切分，结果平铺加入列表（避免嵌套）
        # extend 的作用就是： 把另一个列表（或可迭代对象）里的“元素”，一个个拆出来，直接追加到当前列表的尾部
        refined_split.extend(_split_long_section(sec))
    logger.info(f"步骤4-1：超长章节切分完成，共生成{len(refined_split)}个初始子Chunk")

    # 阶段2：合并过短章节 → 减少碎片化，提升后续检索/大模型调用效果
    final_sections = _merge_short_sections(refined_split, min_length=min_len, max_length=max_len)
    logger.info(f"步骤4-2：过短章节合并完成，最终得到{len(final_sections)}个Chunk")

    # 阶段3：父标题兜底 → 适配Milvus向量库schema（parent_title为必填字段）
    # 兜底规则：无parent_title则用自身title，title也无则填空字符串
    for sec in final_sections:
        if not isinstance(sec, dict):
            continue

        # 补全缺失的part字段（默认0），适配Milvus schema
        if "part" not in sec:
            sec["part"] = 0

        if not sec.get("parent_title"):
            sec["parent_title"] = sec.get("title") or ""
    logger.debug(f"步骤4-3：父标题兜底完成，所有Chunk均包含parent_title字段")

    return final_sections


@step_log("backup_chunks")
def backup_chunks(chunks: list[dict], md_path: str) -> None:
    chunks_json_path = Path(md_path).parent / f"{Path(md_path).stem}.json"
    chunks_json_path.write_text(json.dumps(chunks, ensure_ascii=False, indent=4), encoding="utf-8")


@step_log("split_document")
def split_document(state: dict) -> dict:
    # 先准备好切分所需的 Markdown 正文和文件标题。
    md_content, file_title = load_markdown_content(state)
    # 第一步按标题做语义级粗切，尽量保证一个主题块落在一起。
    chunks = split_by_titles(md_content, file_title)
    # 第二步再按长度细切，避免单块过长影响后续 embedding 和检索。
    chunks = refine_chunks(chunks, max_len=CHUNK_MAX_SIZE, min_len=CHUNK_SIZE)
    # 切分结果额外落一份 chunks.json，方便排查切片质量。
    backup_chunks(chunks, state["md_path"])
    state["chunks"] = chunks
    return state
