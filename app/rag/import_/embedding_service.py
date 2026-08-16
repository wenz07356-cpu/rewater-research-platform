"""文档 chunk 稠密与稀疏向量生成服务。"""

from __future__ import annotations

import math
from typing import Any

from app.infra.llm.providers import llm_provider
from app.rag.import_.config import EMBEDDING_BATCH_SIZE, MILVUS_VECTOR_DIM
from app.shared.runtime.logger import logger, step_log


@step_log("require_embedding_chunks")
def require_chunks(state: dict[str, Any]) -> list[dict[str, Any]]:
    """校验状态中存在待向量化 chunks。

    核心功能：在调用模型前阻止空列表和非法元素进入批处理。
    输入：导入状态。
    输出：非空 chunk 字典列表。
    步骤：检查列表非空、逐项为字典且有非空 content/embedding_text。
    """
    chunks = state.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        logger.error("chunks 为空，无法生成向量")
        raise ValueError("chunks 为空，无法生成向量")
    for index, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            raise ValueError(f"chunks[{index}] 必须是字典")
        text = chunk.get("embedding_text") or chunk.get("content")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"chunks[{index}] 缺少可向量化文本")
    return chunks


def _validate_embedding_result(result: Any, expected_count: int) -> None:
    """校验单批模型向量结果的数量和数值。

    输入：模型结果和期望条数。
    输出：无；非法时抛出 ``ValueError``。
    步骤：检查 dense/sparse 数量，验证稠密维度及全部权重为有限数。
    """
    if not isinstance(result, dict):
        raise ValueError("Embedding 模型结果必须是字典")
    dense = result.get("dense")
    sparse = result.get("sparse")
    if not isinstance(dense, list) or len(dense) != expected_count:
        raise ValueError("稠密向量数量与输入 chunk 数量不一致")
    if not isinstance(sparse, list) or len(sparse) != expected_count:
        raise ValueError("稀疏向量数量与输入 chunk 数量不一致")

    for index, vector in enumerate(dense):
        if not isinstance(vector, (list, tuple)) or len(vector) != MILVUS_VECTOR_DIM:
            raise ValueError(
                f"dense[{index}] 维度必须为 {MILVUS_VECTOR_DIM}"
            )
        if not all(
            isinstance(value, (int, float)) and math.isfinite(float(value))
            for value in vector
        ):
            raise ValueError(f"dense[{index}] 包含非法数值")

    for index, vector in enumerate(sparse):
        if not isinstance(vector, dict):
            raise ValueError(f"sparse[{index}] 必须是字典")
        if not all(
            isinstance(key, int)
            and key >= 0
            and isinstance(value, (int, float))
            and math.isfinite(float(value))
            for key, value in vector.items()
        ):
            raise ValueError(f"sparse[{index}] 包含非法索引或权重")


@step_log("embed_chunks")
def embed_chunks(
    chunks: list[dict[str, Any]],
    *,
    step: int = EMBEDDING_BATCH_SIZE,
) -> list[dict[str, Any]]:
    """分批为全部 chunks 生成向量。

    核心功能：保证输入和输出一一对应，不再静默跳过失败批次。
    输入：chunks 和批大小。
    输出：复制后带 ``dense_vector/sparse_vector`` 的完整 chunk 列表。
    步骤：构造批文本，调用模型，严格校验结果，写入副本并移除临时字段。
    """
    if step <= 0:
        raise ValueError("Embedding 批大小必须大于 0")
    embedded_chunks: list[dict[str, Any]] = []
    total = len(chunks)

    for start in range(0, total, step):
        batch = chunks[start : start + step]
        texts = [
            str(chunk.get("embedding_text") or chunk.get("content") or "")
            for chunk in batch
        ]
        logger.info(
            f"开始生成 chunk 向量：start={start}, batch={len(batch)}, total={total}"
        )
        try:
            result = llm_provider.embed_documents(texts)
            _validate_embedding_result(result, len(batch))
        except Exception as exc:
            logger.error(f"chunk 向量生成失败：start={start}, error={exc}")
            raise RuntimeError(
                f"chunk 向量生成失败，批次起始索引={start}"
            ) from exc

        for offset, chunk in enumerate(batch):
            enriched = chunk.copy()
            enriched["dense_vector"] = [
                float(value) for value in result["dense"][offset]
            ]
            enriched["sparse_vector"] = {
                int(key): float(value)
                for key, value in result["sparse"][offset].items()
            }
            enriched.pop("embedding_text", None)
            embedded_chunks.append(enriched)

    if len(embedded_chunks) != total:
        raise RuntimeError("向量化结果数量与原 chunks 数量不一致")
    logger.info(f"全部 chunk 向量生成完成：total={total}")
    return embedded_chunks


@step_log("generate_chunk_embeddings")
def generate_chunk_embeddings(state: dict[str, Any]) -> dict[str, Any]:
    """向量化状态中的 chunks 并写回。

    输入：包含最终切分 chunks 的导入状态。
    输出：写入全部向量后的原状态。
    步骤：校验 chunks，批量向量化，确认数量不变后更新状态。
    """
    chunks = require_chunks(state)
    state["chunks"] = embed_chunks(chunks)
    return state
