"""再生水行业文档 metadata 抽取服务。

文件名暂时保留以兼容既有导入代码。模块只负责通过大模型抽取文档级 metadata，
不再执行商品名称识别、规则分类、文档切分、向量化或 Milvus 写入。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from app.rag.import_.config import (
    KEYWORDS_MAX_COUNT,
    METADATA_CONTEXT_MAX_CHARS,
    METADATA_ITEM_MAX_LENGTH,
    METADATA_LLM_RETRY,
    REGION_NAMES_MAX_COUNT,
    TOPICS_MAX_COUNT,
)
from app.shared.runtime.logger import logger, step_log


DOCUMENT_TYPES = {"政策", "标准", "规划", "技术文件", "其他"}
DOCUMENT_METADATA_FIELDS = (
    "region_names",
    "document_type",
    "topics",
    "keywords",
)
_DOCUMENT_ID_RE = re.compile(r"^[0-9a-f]{64}$")
_WHITESPACE_RE = re.compile(r"\s+")


class MetadataValidationError(ValueError):
    """表示模型 metadata 的结构或业务取值不合法。"""


def _unique_strings(
    values: Any,
    max_count: int,
    *,
    field_name: str,
) -> list[str]:
    """规范化字符串列表并保持首次出现顺序。

    核心功能：完成列表类型、单项类型、长度、去空和去重校验。
    输入：模型原始值、最大数量和字段名。
    输出：规范化后的字符串列表。
    步骤：校验列表，清理空白，拒绝非字符串和超长项，最后有序去重。
    """
    if not isinstance(values, list):
        raise MetadataValidationError(f"{field_name} 必须是字符串数组")

    result: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(values):
        if not isinstance(value, str):
            raise MetadataValidationError(
                f"{field_name}[{index}] 必须是字符串"
            )
        normalized = _WHITESPACE_RE.sub(" ", value).strip()
        if not normalized:
            continue
        if len(normalized) > METADATA_ITEM_MAX_LENGTH:
            raise MetadataValidationError(
                f"{field_name}[{index}] 超过 {METADATA_ITEM_MAX_LENGTH} 字符"
            )
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)

    if len(result) > max_count:
        logger.warning(
            f"metadata 字段 {field_name} 返回 {len(result)} 项，"
            f"仅保留前 {max_count} 项"
        )
        result = result[:max_count]
    return result


def _build_metadata_context(
    content: str,
    max_chars: int = METADATA_CONTEXT_MAX_CHARS,
) -> str:
    """构造提供给 metadata 模型的正文上下文。

    核心功能：按用户指定的简单策略，只截取 Markdown 正文前 10000 字符。
    输入：完整正文和可覆盖的最大字符数。
    输出：统一换行、去除 BOM 后的正文前缀。
    步骤：校验参数，规范换行，截取 ``content[:max_chars]`` 并返回。
    """
    if not isinstance(content, str) or not content.strip():
        raise ValueError("content 为空，无法构造 metadata 上下文")
    if max_chars <= 0:
        raise ValueError("max_chars 必须大于 0")

    normalized = content.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    context = normalized[:max_chars]
    if len(normalized) > max_chars:
        logger.info(
            f"metadata 正文已按上限截取：原长度={len(normalized)}，"
            f"使用长度={len(context)}"
        )
    return context


def _normalize_region_names(values: Any) -> list[str]:
    """校验并规范化文件主体地域。

    核心功能：保证地域为非空列表，并处理“全国”和“不限”的互斥关系。
    输入：模型输出的 ``region_names``。
    输出：合法、去重后的主体地域列表。
    步骤：规范列表，校验必填项，再检查两个特殊值不能与其他地域并存。
    """
    region_names = _unique_strings(
        values,
        REGION_NAMES_MAX_COUNT,
        field_name="region_names",
    )
    if not region_names:
        raise MetadataValidationError(
            "region_names 不能为空，主体地域不明确时应返回 ['不限']"
        )
    for exclusive_value in ("全国", "不限"):
        if exclusive_value in region_names and region_names != [exclusive_value]:
            raise MetadataValidationError(
                f"{exclusive_value} 不能与其他 region_names 同时出现"
            )
    return region_names


def _normalize_llm_metadata(raw: Any) -> dict[str, Any]:
    """严格校验大模型返回的文档 metadata。

    核心功能：只接受四个业务字段，并统一其类型、枚举、数量和空白格式。
    输入：JSON parser 返回的任意对象。
    输出：只包含四个白名单字段的新字典。
    步骤：校验对象和必填字段，规范文种、地域、主题及关键词，记录未知字段。
    """
    if not isinstance(raw, dict):
        raise MetadataValidationError("metadata 模型返回值必须是 JSON 对象")

    allowed_input_fields = set(DOCUMENT_METADATA_FIELDS) | {"document_id"}
    unknown_fields = sorted(set(raw) - allowed_input_fields)
    if unknown_fields:
        logger.warning(f"metadata 模型返回未知字段，已忽略：{unknown_fields}")

    document_type = str(raw.get("document_type") or "").strip()
    if document_type not in DOCUMENT_TYPES:
        allowed = "、".join(sorted(DOCUMENT_TYPES))
        raise MetadataValidationError(
            f"document_type={document_type!r} 不合法，允许值：{allowed}"
        )

    topics = _unique_strings(
        raw.get("topics"),
        TOPICS_MAX_COUNT,
        field_name="topics",
    )
    keywords = _unique_strings(
        raw.get("keywords"),
        KEYWORDS_MAX_COUNT,
        field_name="keywords",
    )
    topic_set = set(topics)
    keywords = [item for item in keywords if item not in topic_set]

    return {
        "region_names": _normalize_region_names(raw.get("region_names")),
        "document_type": document_type,
        "topics": topics,
        "keywords": keywords,
    }


def _invoke_metadata_model(prompt: str) -> dict[str, Any]:
    """调用 JSON 模式聊天模型并解析结果。

    核心功能：隔离 LangChain 依赖，使模型调用易于测试和替换。
    输入：完整 metadata prompt。
    输出：模型返回的 JSON 字典。
    步骤：创建消息，组合 JSON parser，调用模型并校验顶层对象类型。
    """
    from langchain_core.messages import HumanMessage
    from langchain_core.output_parsers import JsonOutputParser

    from app.infra.llm.providers import llm_provider

    chain = llm_provider.chat(json_mode=True) | JsonOutputParser()
    result = chain.invoke([HumanMessage(content=prompt)])
    if not isinstance(result, dict):
        raise MetadataValidationError("metadata 模型返回值不是 JSON 对象")
    return result


@step_log("extract_metadata_by_llm")
def extract_metadata_by_llm(*, content: str, file_title: str) -> dict[str, Any]:
    """直接调用大模型抽取文档级 metadata。

    核心功能：使用标题和正文前 10000 字符抽取地域、文种、主题和关键词。
    输入：完整 Markdown 正文和文件标题。
    输出：通过严格校验的四字段 metadata。
    步骤：构造上下文和 prompt，调用模型；失败时携带错误原因重试一次。
    """
    from app.shared.runtime.load_prompt import load_prompt

    context = _build_metadata_context(content)
    base_prompt = load_prompt(
        "document_metadata_extraction",
        file_title=file_title,
        context=context,
    )
    last_error: Exception | None = None

    for attempt in range(METADATA_LLM_RETRY + 1):
        prompt = base_prompt
        if last_error is not None:
            prompt += (
                "\n\n上一次输出未通过校验。请修正后重新输出 JSON。"
                f"校验错误：{last_error}"
            )
            logger.warning(
                f"metadata 抽取第 {attempt} 次重试，原因：{last_error}"
            )
        try:
            return _normalize_llm_metadata(_invoke_metadata_model(prompt))
        except Exception as exc:
            last_error = exc

    logger.error(f"metadata 大模型抽取失败：{last_error}")
    raise RuntimeError("metadata 大模型抽取失败，导入已终止") from last_error


def _build_document_id(state: dict[str, Any], file_title: str) -> str:
    """生成同一来源重复导入时稳定的文档 ID。

    核心功能：优先复用合法 ID，否则根据来源路径或标题生成 SHA-256 标识。
    输入：导入状态和文件标题。
    输出：64 位十六进制 ``document_id``。
    步骤：检查显式 ID，选择原始文件名或标题，规范大小写后计算摘要。
    """
    explicit_id = str(state.get("document_id") or "").strip().lower()
    if explicit_id:
        if not _DOCUMENT_ID_RE.fullmatch(explicit_id):
            raise ValueError("state.document_id 必须是 64 位十六进制字符串")
        return explicit_id

    source = state.get("local_file_path") or state.get("md_path")
    if source:
        # 上传接口会把同一文件放入不同日期/任务 ID 目录。只使用原始文件名，
        # 才能保证重复上传收敛到同一 document_id。
        source_key = f"filename:{Path(str(source)).name.casefold()}"
        logger.warning(
            "document_id 根据文件名生成；同名不同文档应由调用方显式提供 document_id"
        )
    else:
        source_key = _WHITESPACE_RE.sub(" ", file_title).strip().casefold()
        logger.warning("缺少来源路径，document_id 将仅根据 file_title 生成")
    return hashlib.sha256(source_key.encode("utf-8")).hexdigest()


def validate_document_metadata(metadata: Any) -> dict[str, Any]:
    """校验包含基础设施 ID 的完整文档 metadata。

    核心功能：为复用已有 metadata 和跨 service 传递提供统一契约校验。
    输入：待校验对象。
    输出：复制后的合法 metadata。
    步骤：校验四个业务字段，再验证 64 位 document_id。
    """
    normalized = _normalize_llm_metadata(metadata)
    document_id = str(metadata.get("document_id") or "").strip().lower()
    if not _DOCUMENT_ID_RE.fullmatch(document_id):
        raise MetadataValidationError("document_id 必须是 64 位十六进制字符串")
    return {"document_id": document_id, **normalized}


def apply_document_metadata(
    chunks: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    """将文档级 metadata 下沉到每个 chunk。

    核心功能：保证所有 chunk 使用完全一致的文档级过滤字段。
    输入：chunk 列表和完整 metadata。
    输出：原列表，其中每个 chunk 已写入文档级字段。
    步骤：校验 metadata，检查冲突，复制列表值后写入每个 chunk。
    """
    normalized = validate_document_metadata(metadata)
    for chunk_index, chunk in enumerate(chunks):
        for field, value in normalized.items():
            current = chunk.get(field)
            if current not in (None, "", []) and current != value:
                raise ValueError(
                    f"chunk[{chunk_index}].{field} 与文档 metadata 冲突"
                )
            chunk[field] = value.copy() if isinstance(value, list) else value
    return chunks


@step_log("extract_document_metadata")
def extract_document_metadata(
    state: dict[str, Any],
    *,
    force: bool = False,
) -> dict[str, Any]:
    """抽取文档 metadata 并更新导入状态。

    核心功能：加载正文，直接调用 LLM，生成稳定文档 ID，并同步已有 chunks。
    输入：导入状态；``force`` 控制是否忽略已有合法 metadata。
    输出：写入 ``document_metadata/document_id/document_type`` 后的原状态。
    步骤：复用合法结果或读取正文，调用模型，补 ID，写回状态并记录摘要日志。
    """
    existing = state.get("document_metadata")
    if existing and not force:
        try:
            metadata = validate_document_metadata(existing)
            state["document_metadata"] = metadata
            state["document_id"] = metadata["document_id"]
            state["document_type"] = metadata["document_type"]
            if state.get("chunks"):
                apply_document_metadata(state["chunks"], metadata)
            logger.info("复用状态中已有的合法 document_metadata")
            return state
        except MetadataValidationError as exc:
            logger.warning(f"已有 document_metadata 无效，将重新抽取：{exc}")

    content = str(state.get("md_content") or "")
    md_path = state.get("md_path")
    if not content and md_path and Path(str(md_path)).is_file():
        content = Path(str(md_path)).read_text(encoding="utf-8")
        state["md_content"] = content
        logger.info(f"已从 Markdown 文件加载 metadata 正文：{md_path}")
    if not content.strip():
        logger.error("md_content 为空，无法执行文档 metadata 抽取")
        raise ValueError("md_content 为空，无法执行文档 metadata 抽取")

    file_title = str(
        state.get("file_title")
        or (Path(str(md_path)).stem if md_path else "未命名文档")
    ).strip()
    extracted = extract_metadata_by_llm(content=content, file_title=file_title)
    metadata = {
        "document_id": _build_document_id(state, file_title),
        **extracted,
    }

    state["file_title"] = file_title
    state["document_metadata"] = metadata
    state["document_id"] = metadata["document_id"]
    state["document_type"] = metadata["document_type"]
    if state.get("chunks"):
        apply_document_metadata(state["chunks"], metadata)

    logger.info(
        "文档 metadata 抽取完成："
        f"document_id={metadata['document_id']}, "
        f"document_type={metadata['document_type']}, "
        f"regions={metadata['region_names']}, "
        f"topics={len(metadata['topics'])}, keywords={len(metadata['keywords'])}"
    )
    return state


@step_log("recognize_and_index_item_name")
def recognize_and_index_item_name(state: dict[str, Any]) -> dict[str, Any]:
    """兼容旧调用名称并转发到 metadata 抽取。

    核心功能：避免旧调用方立即报错，不再生成或索引 ``item_name``。
    输入：旧导入状态。
    输出：完成文档 metadata 抽取的状态。
    步骤：记录废弃告警，然后调用 ``extract_document_metadata``。
    """
    logger.warning(
        "recognize_and_index_item_name 已废弃，请迁移到 extract_document_metadata"
    )
    return extract_document_metadata(state)
