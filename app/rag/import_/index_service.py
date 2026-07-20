"""
入库服务模块，负责创建 Milvus 集合并写入切块数据。
"""
from pymilvus import DataType

from app.shared.runtime.logger import logger, step_log
from app.infra.vector_store.milvus_gateway import milvus_gateway
from app.rag.import_.config import (
    MILVUS_CHUNK_CONTENT_MAX_LENGTH,
    MILVUS_DEFAULT_VARCHAR_MAX_LENGTH,
    MILVUS_VECTOR_DIM,
)


@step_log("require_chunks")
def require_chunks(state: dict) -> list[dict]:
    """
    校验导入状态中是否已经生成切块结果。

    Args:
        state: 导入图当前状态。

    Returns:
        list[dict]: 已通过校验的切块列表。
    """
    chunks = state.get("chunks", [])
    if not chunks:
        logger.error("chunks为空,无法继续业务!!")
        raise ValueError("chunks为空,无法继续业务!!")
    return chunks


@step_log("prepare_chunks_collection")
def prepare_chunks_collection() -> None:
    milvus_client = milvus_gateway.client()
    collection_name = milvus_gateway.chunks_collection
    if milvus_client.has_collection(collection_name=collection_name):
        return

    schema = milvus_client.create_schema(auto_id=True, enable_dynamic_field=True)
    schema.add_field(field_name="chunk_id", datatype=DataType.INT64, is_primary=True, auto_id=True)
    schema.add_field(field_name="file_title", datatype=DataType.VARCHAR, max_length=MILVUS_DEFAULT_VARCHAR_MAX_LENGTH)
    schema.add_field(field_name="item_name", datatype=DataType.VARCHAR, max_length=MILVUS_DEFAULT_VARCHAR_MAX_LENGTH)
    schema.add_field(field_name="title", datatype=DataType.VARCHAR, max_length=MILVUS_DEFAULT_VARCHAR_MAX_LENGTH)
    schema.add_field(field_name="parent_title", datatype=DataType.VARCHAR, max_length=MILVUS_DEFAULT_VARCHAR_MAX_LENGTH)
    schema.add_field(field_name="part", datatype=DataType.INT8)
    schema.add_field(field_name="content", datatype=DataType.VARCHAR, max_length=MILVUS_CHUNK_CONTENT_MAX_LENGTH)
    schema.add_field(field_name="dense_vector", datatype=DataType.FLOAT_VECTOR, dim=MILVUS_VECTOR_DIM)
    schema.add_field(field_name="sparse_vector", datatype=DataType.SPARSE_FLOAT_VECTOR)

    index_params = milvus_client.prepare_index_params()
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
    milvus_client.create_collection(collection_name=collection_name, schema=schema, index_params=index_params)


@step_log("remove_old_chunks")
def remove_old_chunks(item_name: str) -> None:
    milvus_gateway.client().delete(
        collection_name=milvus_gateway.chunks_collection,
        filter=f"item_name=='{item_name}'",
    )


@step_log("insert_chunks")
def insert_chunks(chunks: list[dict]) -> None:
    result = milvus_gateway.client().insert(
        collection_name=milvus_gateway.chunks_collection,
        data=chunks,
    )
    logger.info(f"插入数据成功! 总条数:{result.get('insert_count', 0)}")
    logger.info(f"插入数据主键回显:{result.get('ids', [])}")


@step_log("index_chunks")
def index_chunks(state: dict) -> dict:
    # 先校验切片存在，避免把空数据写入向量库。
    chunks = require_chunks(state)
    # 集合不存在时先自动创建，保证首次导入也能直接跑通。
    prepare_chunks_collection()
    item_name = state.get("item_name", "")
    # 同一主体重复导入时先删旧数据，保持当前导入结果覆盖旧版本。
    if item_name:
        remove_old_chunks(item_name)
    insert_chunks(chunks)
    return state
