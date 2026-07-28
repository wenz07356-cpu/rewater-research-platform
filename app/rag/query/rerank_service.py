"""
重排服务模块，负责多路召回结果整理、打分与动态截断。
"""
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser

from app.shared.runtime.logger import logger, step_log
from app.shared.runtime.load_prompt import load_prompt
from app.infra.llm import providers


RERANK_MAX_TOPK: int = 10
RERANK_MIN_TOPK: int = 1
RERANK_GAP_RATIO: float = 2
RERANK_GAP_ABS: float = 2
RERANK_MAX_INPUT_TOKENS: int = 512
RERANK_SUMMARY_CHAR_RATIO: float = 1.3
RERANK_MIN_SUMMARY_CHARS: int = 50


@step_log("validate_rerank_inputs")
def validate_rerank_inputs(state: dict) -> tuple[list[dict], list[dict]]:
    """
    读取重排阶段所需的两路输入数据。

    Args:
        state: 查询图当前状态，可能包含 RRF 结果与 WebSearch 结果。

    Returns:
        tuple[list[dict], list[dict]]: 依次返回 RRF 切块列表与联网搜索文档列表。
    """
    return state.get("rrf_chunks", []), state.get("web_search_docs", [])


@step_log("merge_rrf_and_web")
def merge_rrf_and_web(rrf_chunks: list[dict], web_search_docs: list[dict]) -> list[dict]:
    """
    将本地召回结果与联网搜索结果整理成统一格式。

    Args:
        rrf_chunks: 本地向量召回经 RRF 融合后的切块列表。
        web_search_docs: 联网搜索返回的文档列表。

    Returns:
        list[dict]: 统一后的候选文档列表，便于后续重排模型打分。
    """
    # 先把本地召回和联网结果都整理成统一结构，方便交给同一个重排模型打分。
    final_chunk_list: list[dict] = []
    for chunk in rrf_chunks or []:
        final_chunk_list.append(
            {
                "title": chunk.get("title"),
                "text": chunk.get("content"),
                "url": None,
                "type": chunk.get("type", "milvus"),
                "score": chunk.get("score", 0.0),
            }
        )
    for doc in web_search_docs or []:
        final_chunk_list.append(
            {
                "title": doc.get("title"),
                "text": doc.get("snippet"),
                "url": doc.get("url"),
                "type": "web",
                "score": 0.0,
            }
        )
    logger.info(
        f"完成了两路数据统一格式处理,rrf路原数据条数:{len(rrf_chunks)},web_mcp路原数据条数:{len(web_search_docs)},合并后数据:{len(final_chunk_list)}条"
    )
    return final_chunk_list


@step_log("summarize_long_rerank_text")
def summarize_long_rerank_text(question: str, answer: str, limit: int) -> str:
    """
    当候选文本超出重排模型上下文上限时，先调用大模型做精炼。

    Args:
        question: 当前用于重排的问题文本。
        answer: 候选文档正文。
        limit: 精炼后允许的最大字数。

    Returns:
        str: 精炼后的候选文本。
    """
    prompt = load_prompt(
        "rerank_text_refine",
        question=question,
        answer=answer,
        limit=limit,
    )
    messages = [
        SystemMessage(content="你现在是文本精简提炼专家。根据用户发送的文本完成文本精炼要求。"),
        HumanMessage(content=prompt),
    ]
    refined_answer = (providers.chat() | StrOutputParser()).invoke(messages)
    logger.debug(f"重排前文本精炼完成,原始长度:{len(answer)},精炼后长度:{len(refined_answer)}")
    return refined_answer


@step_log("build_question_pairs")
def build_question_pairs(question: str, final_chunk_list: list[dict], reranker) -> list[list[str]]:
    """
    构造重排模型需要的问答对列表，并在必要时对超长文本做精炼。

    Args:
        question: 当前问题文本。
        final_chunk_list: 已统一结构的候选文档列表。
        reranker: 当前重排模型实例，用于复用其 tokenizer。

    Returns:
        list[list[str]]: 可直接送入重排模型的问答对列表。
    """
    tokenizer = reranker.tokenizer
    query_tokens = tokenizer.encode(question, add_special_tokens=False)
    question_pairs: list[list[str]] = []
    for item in final_chunk_list:
        answer = item.get("text") or ""
        answer_for_rerank = answer
        answer_tokens = tokenizer.encode(answer, add_special_tokens=False)
        total_tokens = len(query_tokens) + len(answer_tokens) + 3
        if total_tokens > RERANK_MAX_INPUT_TOKENS:
            limit = max(
                RERANK_MIN_SUMMARY_CHARS,
                int((RERANK_MAX_INPUT_TOKENS - len(query_tokens) - 3) / RERANK_SUMMARY_CHAR_RATIO),
            )
            logger.info(f"候选文本超出重排上下文限制,开始精炼后再打分,token总数:{total_tokens},限制:{RERANK_MAX_INPUT_TOKENS}")
            answer_for_rerank = summarize_long_rerank_text(question=question, answer=answer, limit=limit)
        question_pairs.append([question, answer_for_rerank])
    return question_pairs


@step_log("score_and_sort_chunks")
def score_and_sort_chunks(state: dict, final_chunk_list: list[dict]) -> list[dict]:
    """
    调用重排模型对候选文档打分并按分数降序排序。

    Args:
        state: 查询图当前状态，用于读取改写问题或原始问题。
        final_chunk_list: 已统一格式的候选文档列表。

    Returns:
        list[dict]: 写入了分数字段且按分数降序排列的候选列表。
    """
    if not final_chunk_list:
        return []
    rewritten_query = state.get("rewritten_query") or state.get("original_query") or ""
    reranker = providers.reranker_model()
    question_pairs = build_question_pairs(rewritten_query, final_chunk_list, reranker)
    score_list = reranker.compute_score(question_pairs, normalize=True)
    for score, chunk in zip(score_list, final_chunk_list):
        chunk["score"] = round(score, 4)
    final_chunk_list.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return final_chunk_list


@step_log("dynamic_topk")
def dynamic_topk(chunk_list_score_sorted: list[dict]) -> list[dict]:
    """
    根据相邻文档分差动态截断 TopK。

    Args:
        chunk_list_score_sorted: 已按分数降序排列的候选列表。

    Returns:
        list[dict]: 经过动态截断后保留的最终候选列表。
    """
    # 这里不是写死 topk，而是根据相邻分数差动态截断，尽量保留高质量候选。
    min_topk = RERANK_MIN_TOPK
    max_topk = min(RERANK_MAX_TOPK, len(chunk_list_score_sorted))
    gap_ratio = RERANK_GAP_RATIO
    max_gap = RERANK_GAP_ABS
    topk = max_topk
    if topk > min_topk:
        for index in range(min_topk - 1, max_topk - 1):
            score_1 = chunk_list_score_sorted[index].get("score", 0.0)
            score_2 = chunk_list_score_sorted[index + 1].get("score", 0.0)
            abs_score = score_1 - score_2
            ratio_score = abs_score / (score_1 + 1e-7)
            if abs_score > max_gap or ratio_score > gap_ratio:
                topk = index + 1
                break
    return chunk_list_score_sorted[:topk]


@step_log("rerank_documents")
def rerank_documents(state: dict) -> list[dict]:
    """
    执行完整的重排流程。

    Args:
        state: 查询图当前状态，需包含 RRF 结果或联网搜索结果。

    Returns:
        list[dict]: 最终保留的重排文档列表。
    """
    rrf_chunks, web_search_docs = validate_rerank_inputs(state)
    merged = merge_rrf_and_web(rrf_chunks, web_search_docs)
    sorted_docs = score_and_sort_chunks(state, merged)
    return dynamic_topk(sorted_docs)
