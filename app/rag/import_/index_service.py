"""Milvus 文档 chunk 索引服务。"""

from __future__ import annotations

import json
import math
import re
from typing import Any

from pymilvus import DataType

from app.infra.vector_store.milvus_gateway import milvus_gateway
from app.rag.import_.config import (
    KEYWORDS_MAX_COUNT,
    MILVUS_ARRAY_ITEM_MAX_LENGTH,
    MILVUS_CHUNK_CONTENT_MAX_LENGTH,
    MILVUS_DEFAULT_VARCHAR_MAX_LENGTH,
    MILVUS_VECTOR_DIM,
    MILVUS_WRITE_BATCH_SIZE,
    REGION_NAMES_MAX_COUNT,
    TOPICS_MAX_COUNT,
)
from app.rag.import_.item_name_service import DOCUMENT_TYPES
from app.shared.runtime.logger import logger, step_log


CONTEXT_TYPES = {"text", "table", "code"}
_ID_RE = re.compile(r"^[0-9a-f]{64}$")
_RECORD_FIELDS = (
    "chunk_id",
    "document_id",
    "chunk_index",
    "file_title",
    "section_title",
    "content",
    "context_type",
    "region_names",
    "document_type",
    "topics",
    "keywords",
    "token_count",
    "dense_vector",
    "sparse_vector",
)


def _require_milvus_client() -> Any:
    """获取可用 Milvus client。

    输入：无。
    输出：Milvus client。
    步骤：通过 gateway 获取客户端；连接配置缺失或创建失败时显式终止导入。
    """
    client = milvus_gateway.client()
    if client is None:
        logger.error("Milvus client 不可用，请检查连接配置")
        raise RuntimeError("Milvus client 不可用")
    return client


@step_log("require_index_chunks")
def require_chunks(state: dict[str, Any]) -> list[dict[str, Any]]:
    """获取并完成 chunks 第一层结构校验。

    输入：导入状态。
    输出：非空 chunk 字典列表。
    步骤：校验列表非空并逐项检查字典类型，不修改原数据。
    """
    chunks = state.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        logger.error("chunks 为空，无法写入 Milvus")
        raise ValueError("chunks 为空，无法写入 Milvus")
    for index, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            raise ValueError(f"chunks[{index}] 必须是字典")
    return chunks


def _validate_string(
    chunk: dict[str, Any],
    field: str,
    index: int,
    max_length: int,
) -> str:
    """校验单个必填字符串字段并返回清理值。"""
    value = chunk.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"chunks[{index}].{field} 必须是非空字符串")
    normalized = value.strip()
    if len(normalized) > max_length:
        raise ValueError(
            f"chunks[{index}].{field} 超过最大长度 {max_length}"
        )
    return normalized


def _validate_string_array(
    chunk: dict[str, Any],
    field: str,
    index: int,
    max_count: int,
) -> list[str]:
    """校验 Milvus ARRAY<VARCHAR> 字段并返回副本。"""
    values = chunk.get(field)
    if not isinstance(values, list) or len(values) > max_count:
        raise ValueError(
            f"chunks[{index}].{field} 必须是最多 {max_count} 项的数组"
        )
    result: list[str] = []
    for value_index, value in enumerate(values):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"chunks[{index}].{field}[{value_index}] 必须是非空字符串"
            )
        normalized = value.strip()
        if len(normalized) > MILVUS_ARRAY_ITEM_MAX_LENGTH:
            raise ValueError(
                f"chunks[{index}].{field}[{value_index}] 超过最大长度"
            )
        result.append(normalized)
    return result


def _validate_chunk(chunk: dict[str, Any], index: int) -> None:
    """严格校验单个 chunk 入库契约。

    输入：chunk 和其列表索引。
    输出：无；发现非法字段时抛出带定位信息的异常。
    步骤：校验 ID、文本、枚举、数组、统计值以及稠密/稀疏向量。
    """
    chunk_id = _validate_string(chunk, "chunk_id", index, 64)
    document_id = _validate_string(chunk, "document_id", index, 64)
    if not _ID_RE.fullmatch(chunk_id) or not _ID_RE.fullmatch(document_id):
        raise ValueError(f"chunks[{index}] 的 ID 必须是 64 位十六进制字符串")

    _validate_string(
        chunk,
        "file_title",
        index,
        MILVUS_DEFAULT_VARCHAR_MAX_LENGTH,
    )
    _validate_string(
        chunk,
        "section_title",
        index,
        MILVUS_DEFAULT_VARCHAR_MAX_LENGTH,
    )
    _validate_string(
        chunk,
        "content",
        index,
        MILVUS_CHUNK_CONTENT_MAX_LENGTH,
    )
    context_type = _validate_string(chunk, "context_type", index, 32)
    if context_type not in CONTEXT_TYPES:
        raise ValueError(f"chunks[{index}].context_type 不合法：{context_type}")
    document_type = _validate_string(chunk, "document_type", index, 32)
    if document_type not in DOCUMENT_TYPES:
        raise ValueError(f"chunks[{index}].document_type 不合法：{document_type}")

    region_names = _validate_string_array(
        chunk,
        "region_names",
        index,
        REGION_NAMES_MAX_COUNT,
    )
    if not region_names:
        raise ValueError(f"chunks[{index}].region_names 不能为空")
    _validate_string_array(chunk, "topics", index, TOPICS_MAX_COUNT)
    _validate_string_array(chunk, "keywords", index, KEYWORDS_MAX_COUNT)

    for field in ("chunk_index", "token_count"):
        value = chunk.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"chunks[{index}].{field} 必须是非负整数")

    dense = chunk.get("dense_vector")
    if not isinstance(dense, (list, tuple)) or len(dense) != MILVUS_VECTOR_DIM:
        raise ValueError(
            f"chunks[{index}].dense_vector 维度必须为 {MILVUS_VECTOR_DIM}"
        )
    if not all(
        isinstance(value, (int, float)) and math.isfinite(float(value))
        for value in dense
    ):
        raise ValueError(f"chunks[{index}].dense_vector 包含非法数值")

    sparse = chunk.get("sparse_vector")
    if not isinstance(sparse, dict):
        raise ValueError(f"chunks[{index}].sparse_vector 必须是字典")
    if not all(
        isinstance(key, int)
        and key >= 0
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        for key, value in sparse.items()
    ):
        raise ValueError(f"chunks[{index}].sparse_vector 包含非法索引或权重")


def _to_milvus_record(chunk: dict[str, Any]) -> dict[str, Any]:
    """把内部 chunk 转换为严格白名单 record。

    输入：已通过校验的 chunk。
    输出：只包含新版 schema 字段的新字典。
    步骤：复制白名单字段，并规范数组、整数和向量中的 Python 数值类型。
    """
    record = {field: chunk[field] for field in _RECORD_FIELDS}
    for field in (
        "chunk_id",
        "document_id",
        "file_title",
        "section_title",
        "content",
        "context_type",
        "document_type",
    ):
        record[field] = str(record[field]).strip()
    for field in ("region_names", "topics", "keywords"):
        record[field] = [str(value).strip() for value in record[field]]
    record["chunk_index"] = int(record["chunk_index"])
    record["token_count"] = int(record["token_count"])
    record["dense_vector"] = [float(value) for value in record["dense_vector"]]
    record["sparse_vector"] = {
        int(key): float(value) for key, value in record["sparse_vector"].items()
    }
    return record


@step_log("prepare_chunk_records")
def prepare_chunk_records(
    chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """在数据库修改前完成全量校验和 record 转换。

    输入：完成向量化的 chunks。
    输出：可写入 Milvus 的 records。
    步骤：逐项校验和转换，检查 ID 唯一、单文档约束及连续 chunk_index。
    """
    records: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks):
        _validate_chunk(chunk, index)
        records.append(_to_milvus_record(chunk))

    chunk_ids = [record["chunk_id"] for record in records]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError("同一导入批次存在重复 chunk_id")
    document_ids = {record["document_id"] for record in records}
    if len(document_ids) != 1:
        raise ValueError("index_chunks 一次只能写入一个 document_id")
    chunk_indexes = [record["chunk_index"] for record in records]
    if chunk_indexes != list(range(len(records))):
        raise ValueError("chunk_index 必须按列表顺序从 0 连续递增")
    return records


def _schema_fields(description: Any) -> dict[str, dict[str, Any]]:
    """从不同版本的 Milvus collection 描述中提取字段定义。"""
    if not isinstance(description, dict):
        return {}
    fields = description.get("fields")
    if fields is None and isinstance(description.get("schema"), dict):
        fields = description["schema"].get("fields")
    if not isinstance(fields, list):
        return {}
    return {
        str(field["name"]): field
        for field in fields
        if isinstance(field, dict) and field.get("name")
    }


def _collection_schema_matches(client: Any, collection_name: str) -> bool:
    """判断已有 collection 是否包含完整新版字段。

    输入：Milvus client 和 collection 名称。
    输出：是否至少具备新版字段集合。
    步骤：读取描述、提取字段名，比较缺失项并记录错误摘要。
    """
    description = client.describe_collection(collection_name=collection_name)
    fields = _schema_fields(description)
    field_names = set(fields)
    expected = set(_RECORD_FIELDS)
    missing = sorted(expected - field_names)
    legacy = sorted({"item_name", "title", "parent_title", "part"} & field_names)
    expected_types = {
        "chunk_id": DataType.VARCHAR,
        "document_id": DataType.VARCHAR,
        "chunk_index": DataType.INT32,
        "file_title": DataType.VARCHAR,
        "section_title": DataType.VARCHAR,
        "content": DataType.VARCHAR,
        "context_type": DataType.VARCHAR,
        "region_names": DataType.ARRAY,
        "document_type": DataType.VARCHAR,
        "topics": DataType.ARRAY,
        "keywords": DataType.ARRAY,
        "token_count": DataType.INT32,
        "dense_vector": DataType.FLOAT_VECTOR,
        "sparse_vector": DataType.SPARSE_FLOAT_VECTOR,
    }
    wrong_types: list[str] = []
    for name, expected_type in expected_types.items():
        if name not in fields:
            continue
        actual_type = fields[name].get("type", fields[name].get("datatype"))
        try:
            matches = int(actual_type) == int(expected_type)
        except (TypeError, ValueError):
            matches = str(actual_type).upper().endswith(expected_type.name)
        if not matches:
            wrong_types.append(name)

    auto_id = description.get("auto_id") if isinstance(description, dict) else None
    dynamic_enabled = (
        description.get("enable_dynamic_field")
        if isinstance(description, dict)
        else None
    )
    chunk_primary = bool(fields.get("chunk_id", {}).get("is_primary"))
    dense_params = fields.get("dense_vector", {}).get("params") or {}
    dense_dim = dense_params.get("dim")
    wrong_dense_dim = dense_dim is not None and int(dense_dim) != MILVUS_VECTOR_DIM
    if (
        missing
        or legacy
        or wrong_types
        or auto_id is True
        or dynamic_enabled is True
        or not chunk_primary
        or wrong_dense_dim
    ):
        logger.warning(
            "Milvus collection schema 不兼容："
            f"missing={missing}, legacy={legacy}, wrong_types={wrong_types}, "
            f"auto_id={auto_id}, dynamic={dynamic_enabled}, "
            f"chunk_id_primary={chunk_primary}, dense_dim={dense_dim}"
        )
        return False
    return True


def _versioned_collection_name(collection_name: str) -> str:
    """根据配置集合名生成下一个非破坏性 schema 版本名。

    输入：当前配置的 collection 名称。
    输出：以 ``_v2`` 起步的版本化名称。
    步骤：普通名称追加 ``_v2``；已有 ``_vN`` 后缀时将版本号递增。
    """
    match = re.fullmatch(r"(.+)_v(\d+)", collection_name)
    if match:
        return f"{match.group(1)}_v{int(match.group(2)) + 1}"
    return f"{collection_name}_v2"


def _resolve_chunks_collection_name(client: Any, configured_name: str) -> str:
    """选择兼容新版 schema 的 Milvus collection 名称。

    输入：Milvus client 和配置的基础集合名。
    输出：可复用或待创建的 collection 名称。
    步骤：优先使用配置集合；结构不兼容时保留旧数据并选择下一版本名称。
    """
    collection_name = str(configured_name or "").strip()
    if not collection_name:
        raise ValueError("CHUNKS_COLLECTION 不能为空")
    if not client.has_collection(collection_name=collection_name):
        return collection_name
    if _collection_schema_matches(client, collection_name):
        return collection_name

    versioned_name = _versioned_collection_name(collection_name)
    if client.has_collection(collection_name=versioned_name):
        if _collection_schema_matches(client, versioned_name):
            logger.warning(
                f"配置集合 {collection_name} 为旧 schema，"
                f"本次改用已有新版集合 {versioned_name}"
            )
            return versioned_name
        raise RuntimeError(
            f"Milvus 集合 {collection_name} 和 {versioned_name} 均与新版 schema "
            "不兼容。请检查集合配置，系统不会自动删除已有数据。"
        )

    logger.warning(
        f"配置集合 {collection_name} 为旧 schema，将保留原数据并创建 "
        f"{versioned_name}"
    )
    return versioned_name


def _create_chunks_collection(
    client: Any,
    collection_name: str,
) -> None:
    """按新版字段契约创建 Milvus collection 和向量索引。"""
    schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field(
        field_name="chunk_id",
        datatype=DataType.VARCHAR,
        is_primary=True,
        max_length=64,
    )
    schema.add_field(
        field_name="document_id",
        datatype=DataType.VARCHAR,
        max_length=64,
    )
    schema.add_field(field_name="chunk_index", datatype=DataType.INT32)
    schema.add_field(
        field_name="file_title",
        datatype=DataType.VARCHAR,
        max_length=MILVUS_DEFAULT_VARCHAR_MAX_LENGTH,
    )
    schema.add_field(
        field_name="section_title",
        datatype=DataType.VARCHAR,
        max_length=MILVUS_DEFAULT_VARCHAR_MAX_LENGTH,
    )
    schema.add_field(
        field_name="content",
        datatype=DataType.VARCHAR,
        max_length=MILVUS_CHUNK_CONTENT_MAX_LENGTH,
    )
    schema.add_field(
        field_name="context_type",
        datatype=DataType.VARCHAR,
        max_length=32,
    )
    schema.add_field(
        field_name="region_names",
        datatype=DataType.ARRAY,
        element_type=DataType.VARCHAR,
        max_capacity=REGION_NAMES_MAX_COUNT,
        max_length=MILVUS_ARRAY_ITEM_MAX_LENGTH,
    )
    schema.add_field(
        field_name="document_type",
        datatype=DataType.VARCHAR,
        max_length=32,
    )
    schema.add_field(
        field_name="topics",
        datatype=DataType.ARRAY,
        element_type=DataType.VARCHAR,
        max_capacity=TOPICS_MAX_COUNT,
        max_length=MILVUS_ARRAY_ITEM_MAX_LENGTH,
    )
    schema.add_field(
        field_name="keywords",
        datatype=DataType.ARRAY,
        element_type=DataType.VARCHAR,
        max_capacity=KEYWORDS_MAX_COUNT,
        max_length=MILVUS_ARRAY_ITEM_MAX_LENGTH,
    )
    schema.add_field(field_name="token_count", datatype=DataType.INT32)
    schema.add_field(
        field_name="dense_vector",
        datatype=DataType.FLOAT_VECTOR,
        dim=MILVUS_VECTOR_DIM,
    )
    schema.add_field(
        field_name="sparse_vector",
        datatype=DataType.SPARSE_FLOAT_VECTOR,
    )

    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="dense_vector",
        index_type="AUTOINDEX",
        index_name="dense_vector_index",
        metric_type="IP",
    )
    index_params.add_index(
        field_name="sparse_vector",
        index_type="SPARSE_INVERTED_INDEX",
        index_name="sparse_vector_index",
        metric_type="IP",
        params={"inverted_index_algo": "DAAT_MAXSCORE"},
    )
    client.create_collection(
        collection_name=collection_name,
        schema=schema,
        index_params=index_params,
    )


@step_log("prepare_chunks_collection")
def prepare_chunks_collection() -> str:
    """解析、创建或复用新版 chunks collection。

    输入：无，使用 gateway 配置。
    输出：本次导入实际使用的 collection 名称。
    步骤：优先复用配置集合；旧 schema 自动切换版本名并创建，不删除旧集合。
    """
    client = _require_milvus_client()
    collection_name = _resolve_chunks_collection_name(
        client,
        milvus_gateway.chunks_collection,
    )
    if client.has_collection(collection_name=collection_name):
        logger.info(f"Milvus collection 已存在且 schema 合法：{collection_name}")
        return collection_name

    _create_chunks_collection(client, collection_name)
    logger.info(f"Milvus 新版 chunks collection 创建完成：{collection_name}")
    return collection_name


def _validate_document_id(document_id: str) -> str:
    """校验并返回可安全用于过滤表达式的文档 ID。"""
    normalized = str(document_id).strip().lower()
    if not _ID_RE.fullmatch(normalized):
        raise ValueError("document_id 必须是 64 位十六进制字符串")
    return normalized


@step_log("get_existing_chunk_ids")
def get_existing_chunk_ids(
    document_id: str,
    *,
    collection_name: str | None = None,
) -> set[str]:
    """查询同一文档已经存在的 chunk IDs。

    输入：稳定 document_id 和可选的实际 collection 名称。
    输出：已有 chunk ID 集合。
    步骤：校验 ID，按 document_id 分页 query，只读取 chunk_id，直到结果不足一页。
    """
    normalized = _validate_document_id(document_id)
    client = _require_milvus_client()
    target_collection = collection_name or milvus_gateway.chunks_collection
    page_size = 1000
    offset = 0
    result: set[str] = set()
    while True:
        rows = client.query(
            collection_name=target_collection,
            filter=f'document_id == "{normalized}"',
            output_fields=["chunk_id"],
            limit=page_size,
            offset=offset,
        )
        if not rows:
            break
        result.update(
            str(row["chunk_id"])
            for row in rows
            if isinstance(row, dict) and row.get("chunk_id")
        )
        if len(rows) < page_size:
            break
        offset += page_size
    return result


@step_log("upsert_chunks")
def upsert_chunks(
    records: list[dict[str, Any]],
    *,
    batch_size: int = MILVUS_WRITE_BATCH_SIZE,
    collection_name: str | None = None,
) -> int:
    """分批 upsert 当前文档的全部 records。

    输入：Milvus records、批大小和可选的实际 collection 名称。
    输出：成功 upsert 数量。
    步骤：逐批调用 client.upsert，累计服务端计数，失败立即抛出且不清理旧数据。
    """
    if not records:
        raise ValueError("records 不能为空")
    if batch_size <= 0:
        raise ValueError("batch_size 必须大于 0")
    client = _require_milvus_client()
    target_collection = collection_name or milvus_gateway.chunks_collection
    total = 0
    for start in range(0, len(records), batch_size):
        batch = records[start : start + batch_size]
        response = client.upsert(
            collection_name=target_collection,
            data=batch,
        )
        count = int(
            (response or {}).get("upsert_count")
            or (response or {}).get("insert_count")
            or len(batch)
        )
        if count != len(batch):
            raise RuntimeError(
                f"Milvus upsert 数量异常：expected={len(batch)}, actual={count}"
            )
        total += count
        logger.info(
            f"Milvus chunk upsert 完成：start={start}, batch={count}, "
            f"total={len(records)}"
        )
    return total


@step_log("remove_stale_chunks")
def remove_stale_chunks(
    stale_chunk_ids: set[str],
    *,
    collection_name: str | None = None,
) -> int:
    """删除重新导入后已失效的旧 chunks。

    输入：确认失效的 chunk ID 集合和可选的实际 collection 名称。
    输出：请求删除的 ID 数量。
    步骤：校验全部主键，分批构造 JSON 字符串列表并按主键精确删除。
    """
    if not stale_chunk_ids:
        return 0
    normalized_ids = sorted(_validate_document_id(item) for item in stale_chunk_ids)
    client = _require_milvus_client()
    target_collection = collection_name or milvus_gateway.chunks_collection
    deleted = 0
    for start in range(0, len(normalized_ids), MILVUS_WRITE_BATCH_SIZE):
        batch = normalized_ids[start : start + MILVUS_WRITE_BATCH_SIZE]
        client.delete(
            collection_name=target_collection,
            filter=f"chunk_id in {json.dumps(batch)}",
        )
        deleted += len(batch)
    logger.info(f"已清理失效 Milvus chunks：count={deleted}")
    return deleted


@step_log("index_chunks")
def index_chunks(state: dict[str, Any]) -> dict[str, Any]:
    """完成单篇文档的校验、幂等写入和旧数据清理。

    输入：包含已向量化 chunks 的导入状态。
    输出：索引完成后的原状态。
    步骤：全量预校验，准备集合，查询旧 ID，upsert 当前数据，成功后删除差集。
    """
    chunks = require_chunks(state)
    records = prepare_chunk_records(chunks)
    collection_name = prepare_chunks_collection()

    document_id = records[0]["document_id"]
    existing_ids = get_existing_chunk_ids(
        document_id,
        collection_name=collection_name,
    )
    current_ids = {record["chunk_id"] for record in records}
    upserted = upsert_chunks(records, collection_name=collection_name)
    stale_count = remove_stale_chunks(
        existing_ids - current_ids,
        collection_name=collection_name,
    )
    logger.info(
        f"文档 Milvus 索引完成：document_id={document_id}, "
        f"upserted={upserted}, stale_removed={stale_count}, "
        f"collection={collection_name}"
    )
    return state
