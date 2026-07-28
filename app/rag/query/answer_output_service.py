"""
答案生成服务模块，负责 Prompt 组装、模型生成与结果回写。
"""
import re
import time

from app.shared.runtime.load_prompt import load_prompt
from app.shared.runtime.logger import logger, step_log
from app.infra.llm.providers import llm_provider
from app.infra.persistence.history_repository import history_repository
from app.shared.utils.sse_utils import SSEEvent, push_to_session
from app.shared.utils.task_utils import set_task_result


@step_log("try_return_existing_answer")
def try_return_existing_answer(state: dict) -> bool:
    """
    优先返回状态中已经存在的答案，避免重复调用模型。

    Args:
        state: 查询图当前状态，可能已经提前写入 `answer` 字段。

    Returns:
        bool: 如果已经存在可直接返回的答案则返回 True，否则返回 False。
    """
    # 某些分支会提前产出澄清答案，此时直接复用，避免重复调用大模型。
    answer = state.get("answer")
    # ???????????????????????????
    is_stream = state.get("is_stream", False)
    session_id = state.get("session_id")
    if not answer:
        return False
    if is_stream:
        for ch in answer:
            push_to_session(session_id, SSEEvent.DELTA, {"delta": ch})
            time.sleep(0.3)
    set_task_result(session_id, "answer", answer)
    return True


@step_log("validate_generation_inputs")
def validate_generation_inputs(state: dict) -> tuple[list[dict], list[str], str, list[dict]]:
    """
    校验答案生成阶段必需的输入是否齐全。

    Args:
        state: 查询图当前状态，需包含重排结果、主体信息和问题文本。

    Returns:
        tuple[list[dict], list[str], str, list[dict]]: 依次返回重排文档、主体列表、查询文本和历史消息。
    """
    history = state.get("history", [])
    reranked_docs = state.get("reranked_docs", [])
    item_names = state.get("item_names", [])
    rewritten_query = state.get("rewritten_query") or state.get("original_query")
    if not reranked_docs or not rewritten_query:
        logger.error("reranked_docs或者rewritten_query为空,无法使用模型进行答案匹配!")
        raise ValueError("reranked_docs或者rewritten_query为空,无法使用模型进行答案匹配!")
    return reranked_docs, item_names, rewritten_query, history


@step_log("build_history_text")
def build_history_text(history_messages: list[dict]) -> str:
    """
    将历史消息拼接为适合 Prompt 使用的纯文本。

    Args:
        history_messages: 历史消息列表，包含角色、文本、改写问题和关联主体等字段。

    Returns:
        str: 拼接后的历史上下文文本。
    """
    if not history_messages:
        return "没有历史聊天记录!"

    lines: list[str] = []
    for msg in history_messages:
        content = msg.get("rewritten_query") if msg.get("role") == "user" else msg.get("text")
        item_names = "、".join(msg.get("item_names", []))
        lines.append(f"角色:{msg.get('role', '')},内容:{content},关联主体: {item_names}")
    return "\n".join(lines)


@step_log("build_answer_prompt")
def build_answer_prompt(
    reranked_docs: list[dict],
    rewritten_query: str,
    item_names: list[str],
    history: list[dict],
) -> str:
    """
    构建答案生成 Prompt。

    Args:
        reranked_docs: 重排后的文档列表，作为回答时的主要上下文。
        rewritten_query: 改写后的查询文本。
        item_names: 当前问题关联的主体名称列表。
        history: 最近历史消息列表，用于增强多轮问答上下文。

    Returns:
        str: 可直接送入大模型的最终 Prompt 文本。
    """
    # ???????????????????????????
    context_chunk_list = []
    for number, chunk in enumerate(reranked_docs, start=1):
        context_chunk_list.append(
            f"第{number}块: 标题:{chunk['title']} 匹配度得分:{chunk['score']} 来源:{'网络搜索' if chunk['type'] == 'web' else '向量查询'}\n内容:{chunk['text']}"
        )
    context_chunk_str = "\n\n".join(context_chunk_list)

    history_text = build_history_text(history)

    item_name_str = "本次关联主体:" + ",".join(item_names) if item_names else "没有关联主体"
    return load_prompt(
        "answer_out",
        context=context_chunk_str,
        history=history_text,
        item_names=item_name_str,
        question=rewritten_query,
    )


@step_log("generate_answer")
def generate_answer(state: dict, prompt: str) -> str:
    """
    调用大模型生成答案，并根据模式决定是否推送流式增量。

    Args:
        state: 查询图当前状态，需包含会话 ID 与流式开关。
        prompt: 已组装完成的回答 Prompt。

    Returns:
        str: 大模型生成的最终答案文本。
    """
    print("----node_answer_output 节点处理开始---")
    is_stream = state.get("is_stream", False)
    session_id = state.get("session_id")
    base_answer = state.get("answer") or f"这是关于「{state.get('original_query', '当前问题')}」的测试回答，正在演示]"
    lm_client = llm_provider.chat()
    final_result = ""
    if is_stream:
        for chunk in lm_client.stream(prompt):
            delta_content = chunk.content
            final_result += delta_content
            push_to_session(session_id, SSEEvent.DELTA, {"delta": delta_content})
            time.sleep(0.03)
        image_urls = ["https://www.baidu.com/img/bd_logo.png"]
        push_to_session(
            session_id,
            SSEEvent.FINAL,
            {
                "answer": final_result,
                "status":"completed",
                "image_urls": image_urls
            }
        )
        logger.info(f"流式输出完成，总长度：{len(final_result)}")
    else:
        response = lm_client.invoke(prompt)
        final_result = response.content

    set_task_result(session_id, "answer", final_result)
    state["answer"] = final_result
    print("----node_answer_output  节点处理结束----")
    return {
        "session_id": session_id,  # 必须带回去
        "answer": final_result,
        "image_urls": image_urls,
        "is_stream": state.get("is_stream")
    }


@step_log("extract_image_urls")
def extract_image_urls(reranked_docs: list[dict]) -> list[str]:
    """
    从重排文档中提取可用于前端展示的图片链接。

    Args:
        reranked_docs: 重排后的文档列表，可能包含网页直链或 Markdown 图片语法。

    Returns:
        list[str]: 去重后的图片 URL 列表。
    """
    image_urls: list[str] = []
    reg = re.compile(r"\!\[.*?\]\((.*?)\)")
    for doc in reranked_docs:
        url = doc.get("url")
        text = doc.get("text")
        if url and url.endswith((".png", ".jpg", ".gif", ".jpeg", ".svg")) and url not in image_urls:
            image_urls.append(url)
        if text:
            for image_url in reg.findall(text):
                if image_url not in image_urls:
                    image_urls.append(image_url)
    return image_urls


@step_log("save_assistant_message")
def save_assistant_message(state: dict) -> None:
    """
    将助手回答写入历史记录。

    Args:
        state: 查询图当前状态，需包含会话 ID、最终答案、改写问题和图片链接等信息。
    """
    history_repository.save_message(
        session_id=state["session_id"],
        role="assistant",
        text=state.get("answer"),
        rewritten_query=state.get("rewritten_query") or state.get("original_query"),
        item_names=state.get("item_names", []),
        image_urls=state.get("image_urls", []),
    )


@step_log("produce_answer")
def produce_answer(state: dict) -> dict:
    """
    执行答案生成主流程，并将结果写回状态与历史记录。

    Args:
        state: 查询图当前状态。

    Returns:
        dict: 写回最终答案与图片链接后的最新状态。
    """
    # 只有当前 state 里还没有答案时，才真正进入 Prompt 构建和模型生成阶段。
    if not try_return_existing_answer(state):
        reranked_docs, item_names, rewritten_query, history = validate_generation_inputs(state)
        prompt = build_answer_prompt(reranked_docs, rewritten_query, item_names, history)
        generate_answer(state, prompt)
        state["image_urls"] = extract_image_urls(reranked_docs)
    save_assistant_message(state)
    return state
