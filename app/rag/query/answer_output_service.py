"""查询链路统一答案出口。"""

import re
from typing import Any
from urllib.parse import urlsplit

from langchain_core.messages import HumanMessage

from app.infra.llm.providers import llm_provider
from app.infra.persistence.history_repository import history_repository
from app.process.query.agent.state import QueryGraphState
from app.rag.query.config import (
    ANSWER_MAX_CONTEXT_CHARS,
    QUERY_HISTORY_MAX_CHARS,
    SUPPORTED_IMAGE_EXTENSIONS,
)
from app.rag.query.search_embedding_hyde_service import build_query_scope_text
from app.rag.query.search_embedding_service import normalize_query_filters
from app.shared.runtime.load_prompt import load_prompt
from app.shared.runtime.logger import logger, step_log
from app.shared.utils.sse_utils import SSEEvent, push_to_session
from app.shared.utils.task_utils import set_task_result

_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_LEGACY_SOURCE_RE = re.compile(r"\[来源(\d+)\]")


def handle_prebuilt_answer(state: QueryGraphState) -> tuple[bool, str]:
    """识别并推送查询理解阶段已生成的澄清回答。"""
    answer = str(state.get("answer") or "").strip()
    if not answer:
        return False, ""
    if state.get("is_stream"):
        push_to_session(
            state["session_id"], SSEEvent.DELTA, {"delta": answer}
        )
    logger.info("使用查询理解阶段生成的澄清回答")
    return True, answer


def validate_answer_inputs(
    state: QueryGraphState,
) -> tuple[str, list[dict[str, Any]]]:
    """校验答案生成问题和精排证据列表。"""
    question = str(
        state.get("rewritten_query") or state.get("original_query") or ""
    ).strip()
    documents = state.get("reranked_docs") or []
    if not question:
        raise ValueError("答案生成缺少查询问题")
    if not isinstance(documents, list):
        raise TypeError("reranked_docs 必须为列表")
    return question, documents


def build_source_label(document: dict[str, Any]) -> str:
    """生成用户可直接理解的统一来源标签。

    输入：一条本地或 Web 精排候选。
    输出：本地为 ``[本地知识库/file_title/section_title]``，Web 为
    ``[网络搜索/url]``。
    步骤：先按 source 判断来源；本地缺少章节时回退到文件标题，Web 缺少
    URL 时使用明确占位文本，避免重新退化为不可解释的数字编号。
    """
    if document.get("source") == "web":
        url = str(document.get("url") or "未提供URL").strip()
        return f"[网络搜索/{url}]"

    file_title = str(
        document.get("file_title") or "未命名文件"
    ).strip()
    section_title = str(
        document.get("section_title") or file_title
    ).strip()
    return f"[本地知识库/{file_title}/{section_title}]"


def build_evidence_context(reranked_docs: list[dict[str, Any]]) -> str:
    """构造包含可读来源标签的答案证据。

    输入：最终精排候选列表。
    输出：供答案模型使用的多段证据文本。
    步骤：逐条生成统一来源标签和 metadata，按完整候选控制总长度；不再
    生成 ``[来源1]`` 一类需要二次查找的编号。
    """
    sections: list[str] = []
    length = 0
    for document in reranked_docs:
        source = "网络搜索" if document.get("source") == "web" else "本地知识库"
        source_label = build_source_label(document)
        metadata: list[str] = []
        if document.get("source") != "web":
            if document.get("document_type"):
                metadata.append(f"文档类型：{document['document_type']}")
            if document.get("region_names"):
                metadata.append(
                    f"地域：{'、'.join(document['region_names'])}"
                )
            if document.get("context_type"):
                metadata.append(f"内容类型：{document['context_type']}")
        elif document.get("url"):
            metadata.append(f"URL：{document['url']}")
        section = (
            f"来源标识：{source_label}\n"
            f"标题：{document.get('display_title') or '未命名来源'}\n"
            f"来源：{source}\n"
            f"{'；'.join(metadata)}\n"
            f"内容：{document.get('content') or ''}"
        ).strip()
        if sections and length + len(section) > ANSWER_MAX_CONTEXT_CHARS:
            logger.warning("答案证据达到上下文长度上限，停止追加低排名候选")
            break
        sections.append(section)
        length += len(section)
    return "\n\n".join(sections)


def replace_legacy_source_labels(
    answer: str,
    reranked_docs: list[dict[str, Any]],
) -> str:
    """把模型偶尔生成的旧数字来源转换为新版可读标签。

    输入：模型答案和与 Prompt 顺序一致的精排候选。
    输出：不含可解析旧 ``[来源N]`` 的答案。
    步骤：按 N 的一基索引查找对应候选并替换；索引越界时保留原文本，
    避免错误绑定到其他来源。
    """
    def replace(match: re.Match[str]) -> str:
        index = int(match.group(1)) - 1
        if 0 <= index < len(reranked_docs):
            return build_source_label(reranked_docs[index])
        return match.group(0)

    return _LEGACY_SOURCE_RE.sub(replace, answer)


def build_answer_history_context(state: QueryGraphState) -> str:
    """构造只用于指代和语气衔接的近期历史文本。"""
    messages = state.get("history") or []
    if not isinstance(messages, list) or not messages:
        return "无历史对话"
    lines: list[str] = []
    for message in messages:
        role = "用户" if message.get("role") == "user" else "助手"
        text = (
            message.get("rewritten_query")
            if role == "用户"
            else message.get("text")
        ) or message.get("text") or ""
        lines.append(f"{role}：{str(text)[:300]}")
    result = "\n".join(lines)
    return result[-QUERY_HISTORY_MAX_CHARS:]


def load_answer_prompt(
    state: QueryGraphState,
    evidence_context: str,
    history_text: str,
) -> str:
    """使用问题、范围、证据和历史渲染最终答案 Prompt。"""
    filters = normalize_query_filters(state.get("query_filters"))
    return load_prompt(
        "answer_out",
        question=state.get("rewritten_query") or state.get("original_query"),
        query_scope=build_query_scope_text(filters),
        context=evidence_context,
        history=history_text,
    )


def generate_answer_by_llm(
    state: QueryGraphState,
    prompt_text: str,
) -> str:
    """按流式或非流式模式调用模型，并返回完整答案。"""
    client = llm_provider.chat()
    messages = [HumanMessage(content=prompt_text)]
    answer = ""
    if state.get("is_stream"):
        for chunk in client.stream(messages):
            delta = str(getattr(chunk, "content", "") or "")
            if not delta:
                continue
            answer += delta
            push_to_session(
                state["session_id"], SSEEvent.DELTA, {"delta": delta}
            )
    else:
        response = client.invoke(messages)
        answer = str(getattr(response, "content", "") or "")
    answer = answer.strip()
    if not answer:
        raise RuntimeError("答案模型返回空文本")
    return answer


def _is_image_url(url: str) -> bool:
    """忽略 query/fragment 后判断 URL 路径是否为支持的图片格式。"""
    try:
        path = urlsplit(url).path.lower()
    except ValueError:
        path = url.lower()
    return path.endswith(SUPPORTED_IMAGE_EXTENSIONS)


def extract_image_urls(reranked_docs: list[dict[str, Any]]) -> list[str]:
    """从最终证据正文和 Web 地址提取有序、去重的图片 URL。"""
    result: list[str] = []
    for document in reranked_docs:
        candidates = _IMAGE_RE.findall(str(document.get("content") or ""))
        url = str(document.get("url") or "").strip()
        if url and _is_image_url(url):
            candidates.append(url)
        for candidate in candidates:
            candidate = candidate.strip()
            if candidate and candidate not in result:
                result.append(candidate)
    return result


def save_answer_history(
    state: QueryGraphState,
    answer: str,
    image_urls: list[str],
) -> None:
    """保存助手消息；落库失败记录错误但不丢弃已生成答案。"""
    try:
        history_repository.save_message(
            session_id=state["session_id"],
            role="assistant",
            text=answer,
            rewritten_query=state.get("rewritten_query") or "",
            query_filters=normalize_query_filters(
                state.get("query_filters")
            ),
            item_names=[],
            image_urls=image_urls,
        )
    except Exception as exc:
        logger.exception(f"助手回答历史保存失败：error={exc}")


@step_log("produce_answer")
def produce_answer(state: QueryGraphState) -> dict[str, Any]:
    """统一处理澄清、无结果和证据回答。

    输入：查询图最终状态或入口澄清状态。
    输出：answer、image_urls 和 prompt 状态增量。
    步骤：优先使用固定回答；无证据固定兜底；有证据才调用模型。
    """
    has_answer, answer = handle_prebuilt_answer(state)
    prompt_text = ""
    documents: list[dict[str, Any]] = []
    if not has_answer:
        _, documents = validate_answer_inputs(state)
        if not documents:
            answer = "未检索到足以回答该问题的参考内容。"
            if state.get("is_stream"):
                push_to_session(
                    state["session_id"],
                    SSEEvent.DELTA,
                    {"delta": answer},
                )
            logger.warning("所有检索候选为空，使用固定无结果回答")
        else:
            evidence = build_evidence_context(documents)
            history = build_answer_history_context(state)
            prompt_text = load_answer_prompt(state, evidence, history)
            answer = generate_answer_by_llm(state, prompt_text)
            answer = replace_legacy_source_labels(answer, documents)

    image_urls = extract_image_urls(documents)
    if not state.get("eval_disable_history"):
        save_answer_history(state, answer, image_urls)
    set_task_result(state["session_id"], "answer", answer)
    logger.info(
        f"答案输出完成：answer_length={len(answer)}, "
        f"evidence_count={len(documents)}, images={len(image_urls)}"
    )
    return {
        "answer": answer,
        "image_urls": image_urls,
        "prompt": prompt_text,
    }


generate_answer = produce_answer
