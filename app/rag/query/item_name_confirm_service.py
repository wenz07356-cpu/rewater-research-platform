"""查询理解服务：问题改写、范围抽取、澄清判断和用户历史保存。"""

import re
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import JsonOutputParser

from app.infra.llm.providers import llm_provider
from app.infra.persistence.history_repository import history_repository
from app.process.query.agent.state import QueryGraphState
from app.rag.query.config import (
    DOCUMENT_TYPES,
    ORIGINAL_QUERY_MAX_CHARS,
    QUERY_FILTER_MAX_VALUES,
    QUERY_HISTORY_MAX_CHARS,
    QUERY_HISTORY_MESSAGE_LIMIT,
    REWRITTEN_QUERY_MAX_CHARS,
    default_query_filters,
)
from app.shared.runtime.load_prompt import load_prompt
from app.shared.runtime.logger import logger, step_log

_WHITESPACE_RE = re.compile(r"\s+")


@step_log("validate_query_input")
def validate_query_input(state: QueryGraphState) -> tuple[str, str]:
    """校验查询入口。

    输入：包含 session_id 和 original_query 的查询状态。
    输出：规范化后的 session_id、original_query。
    步骤：检查类型和空值，清洗连续空白，并限制异常超长输入。
    """
    session_id = str(state.get("session_id") or "").strip()
    original_query = _WHITESPACE_RE.sub(
        " ", str(state.get("original_query") or "")
    ).strip()
    if not session_id:
        logger.error("查询入口缺少 session_id")
        raise ValueError("session_id 不能为空")
    if not original_query:
        logger.error("查询入口缺少 original_query")
        raise ValueError("original_query 不能为空")
    if len(original_query) > ORIGINAL_QUERY_MAX_CHARS:
        logger.error(
            f"original_query 超过长度限制：length={len(original_query)}, "
            f"limit={ORIGINAL_QUERY_MAX_CHARS}"
        )
        raise ValueError(
            f"original_query 不能超过 {ORIGINAL_QUERY_MAX_CHARS} 个字符"
        )
    return session_id, original_query


@step_log("load_recent_query_history")
def load_recent_history(session_id: str) -> list[dict[str, Any]]:
    """读取近期历史。

    输入：会话 ID。
    输出：按时间正序排列的消息列表。
    步骤：读取最近消息并反转 MongoDB 的倒序结果；不按 item_names 过滤。
    """
    messages = history_repository.list_recent(
        session_id=session_id,
        limit=QUERY_HISTORY_MESSAGE_LIMIT,
    )
    if not messages:
        logger.info(f"会话无历史记录：session_id={session_id}")
        return []
    return list(reversed(messages))


def build_history_context(messages: list[dict[str, Any]]) -> str:
    """构造受长度控制的历史上下文。

    输入：按时间正序的历史消息。
    输出：仅用于指代消解的文本。
    步骤：格式化角色、问题摘要和查询范围，从最近内容向前截取。
    """
    if not messages:
        return "无历史对话"

    lines: list[str] = []
    for message in messages:
        role = "用户" if message.get("role") == "user" else "助手"
        if role == "用户":
            text = message.get("rewritten_query") or message.get("text") or ""
        else:
            text = str(message.get("text") or "")[:300]
        filters = message.get("query_filters") or {}
        legacy_titles = message.get("item_names") or []
        suffix = ""
        if filters:
            suffix = f"；查询范围={filters}"
        elif legacy_titles:
            suffix = f"；旧版文件标题线索={legacy_titles}"
        lines.append(f"{role}：{str(text).strip()}{suffix}")

    selected: list[str] = []
    length = 0
    for line in reversed(lines):
        if length + len(line) > QUERY_HISTORY_MAX_CHARS:
            break
        selected.append(line)
        length += len(line)
    return "\n".join(reversed(selected)) or "无历史对话"


@step_log("call_llm_query_understanding")
def call_llm_query_understanding(
    original_query: str,
    history_text: str,
) -> dict[str, Any]:
    """调用 JSON 模式大模型理解查询。

    输入：当前问题、历史上下文。
    输出：模型生成的原始字典。
    步骤：渲染查询理解 Prompt，调用模型，并严格解析 JSON。
    """
    prompt = load_prompt(
        "query_understanding",
        query=original_query,
        history_text=history_text,
    )
    chain = llm_provider.chat(json_mode=True) | JsonOutputParser()
    result = chain.invoke([HumanMessage(content=prompt)])
    if not isinstance(result, dict):
        raise ValueError("查询理解模型返回值必须为 JSON 对象")
    return result


def _unique_strings(value: Any) -> list[str]:
    """将模型字段规范化为有序、去重、限长的字符串列表。"""
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = _WHITESPACE_RE.sub(" ", str(item or "")).strip()
        if text and text not in result:
            result.append(text)
        if len(result) >= QUERY_FILTER_MAX_VALUES:
            break
    return result


def normalize_query_understanding(
    raw_result: dict[str, Any],
    original_query: str,
) -> dict[str, Any]:
    """规范化查询理解结果。

    输入：模型原始结果和原问题。
    输出：可信 rewritten_query、query_filters 和澄清字段。
    步骤：清洗列表和枚举，限制硬过滤资格，并校验澄清状态。
    """
    rewritten_query = _WHITESPACE_RE.sub(
        " ", str(raw_result.get("rewritten_query") or original_query)
    ).strip()
    if len(rewritten_query) > REWRITTEN_QUERY_MAX_CHARS:
        logger.warning(
            "查询改写超过长度限制，优先回退原问题并按边界限制长度："
            f"length={len(rewritten_query)}"
        )
        rewritten_query = original_query[:REWRITTEN_QUERY_MAX_CHARS].rstrip()

    filters = default_query_filters()
    for field in (
        "file_titles",
        "region_names",
        "document_types",
        "topics",
        "keywords",
    ):
        filters[field] = _unique_strings(raw_result.get(field))
    filters["document_types"] = [
        item for item in filters["document_types"] if item in DOCUMENT_TYPES
    ]
    filters["strict"] = bool(raw_result.get("strict", False))

    # 不采信模型直接给出的 hard_fields；只依据规范化 strict 和白名单字段生成。
    filters["hard_fields"] = [
        field for field in ("region_names", "document_types")
        if filters["strict"] and filters.get(field)
    ]

    needs_clarification = bool(raw_result.get("needs_clarification", False))
    clarification = str(raw_result.get("clarification_question") or "").strip()
    if needs_clarification and not clarification:
        clarification = "当前问题中的指代或限定范围不明确，请补充具体问题。"
    if not needs_clarification:
        clarification = ""

    return {
        "rewritten_query": rewritten_query,
        "query_filters": filters,
        "needs_clarification": needs_clarification,
        "clarification_question": clarification,
    }


def apply_query_understanding(
    state: QueryGraphState,
    result: dict[str, Any],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    """生成查询理解节点的状态增量。"""
    return {
        "rewritten_query": result["rewritten_query"],
        "query_filters": result["query_filters"],
        "history": history,
        "answer": (
            result["clarification_question"]
            if result["needs_clarification"]
            else ""
        ),
    }


def save_user_query_history(
    state: QueryGraphState,
    state_update: dict[str, Any],
) -> None:
    """保存用户问题；历史存储失败不阻断本轮查询。"""
    try:
        history_repository.save_message(
            session_id=state["session_id"],
            role="user",
            text=state["original_query"],
            rewritten_query=state_update["rewritten_query"],
            query_filters=state_update["query_filters"],
            item_names=[],
            image_urls=[],
        )
    except Exception as exc:
        logger.exception(
            f"用户查询历史保存失败，将继续本轮查询：error={exc}"
        )


@step_log("understand_query")
def understand_query(state: QueryGraphState) -> dict[str, Any]:
    """编排查询理解流程。

    输入：查询图状态。
    输出：rewritten_query、query_filters、history、answer 状态增量。
    步骤：校验、读取历史、LLM 理解、规范化、保存历史。
    """
    session_id, original_query = validate_query_input(state)
    history = (
        []
        if state.get("eval_disable_history")
        else load_recent_history(session_id)
    )
    history_text = build_history_context(history)
    try:
        raw_result = call_llm_query_understanding(
            original_query, history_text
        )
        result = normalize_query_understanding(raw_result, original_query)
    except Exception as exc:
        logger.exception(
            "查询理解模型失败，回退为原问题全库检索："
            f"error={exc}"
        )
        result = {
            "rewritten_query": original_query[:REWRITTEN_QUERY_MAX_CHARS],
            "query_filters": default_query_filters(),
            "needs_clarification": False,
            "clarification_question": "",
        }
    update = apply_query_understanding(state, result, history)
    if not state.get("eval_disable_history"):
        save_user_query_history(state, update)
    logger.info(
        "查询理解完成："
        f"session_id={session_id}, rewritten_length="
        f"{len(update['rewritten_query'])}, hard_fields="
        f"{update['query_filters']['hard_fields']}, "
        f"needs_clarification={bool(update['answer'])}"
    )
    return update


# 旧节点调用方兼容；新版业务统一使用 understand_query。
confirm_item_name = understand_query
