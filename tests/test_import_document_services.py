"""新版文档导入 service 的核心契约测试。"""

from __future__ import annotations

import unittest
from unittest.mock import ANY, Mock, patch

from app.rag.import_.embedding_service import embed_chunks
from app.rag.import_.index_service import (
    _resolve_chunks_collection_name,
    index_chunks,
    prepare_chunk_records,
)
from app.rag.import_.item_name_service import (
    MetadataValidationError,
    _build_document_id,
    _build_metadata_context,
    _normalize_llm_metadata,
    extract_document_metadata,
)
from app.rag.import_.split_service import split_document


DOCUMENT_ID = "a" * 64
STALE_CHUNK_ID = "b" * 64


def _document_metadata(
    *,
    document_type: str = "技术文件",
) -> dict:
    """构造通过完整校验的测试 metadata。"""
    return {
        "document_id": DOCUMENT_ID,
        "region_names": ["深圳市"],
        "document_type": document_type,
        "topics": ["再生水利用"],
        "keywords": ["再生水厂", "工程设计"],
    }


def _split_state(content: str, title: str = "测试文档") -> dict:
    """构造无需调用外部 LLM 的切分状态。"""
    return {
        "md_content": content,
        "file_title": title,
        "md_path": None,
        "document_metadata": _document_metadata(),
        "document_id": DOCUMENT_ID,
        "document_type": "技术文件",
    }


def _embed_result(count: int) -> dict:
    """构造符合 BGE/Milvus 维度契约的向量结果。"""
    return {
        "dense": [[0.1] * 1024 for _ in range(count)],
        "sparse": [{1: 0.5, 10: 0.2} for _ in range(count)],
    }


class MetadataServiceTest(unittest.TestCase):
    """验证 LLM metadata 的输入边界和字段契约。"""

    def test_metadata_context_is_simple_first_10000_characters(self) -> None:
        content = "甲" * 10000 + "正文尾部不得进入上下文"

        context = _build_metadata_context(content)

        self.assertEqual(len(context), 10000)
        self.assertEqual(context, "甲" * 10000)

    def test_metadata_normalization_uses_chinese_document_type(self) -> None:
        metadata = _normalize_llm_metadata(
            {
                "region_names": ["深圳市", "深圳市"],
                "document_type": "技术文件",
                "topics": ["工程设计"],
                "keywords": ["工程设计", "用地指标"],
                "unexpected": "ignored",
            }
        )

        self.assertEqual(metadata["region_names"], ["深圳市"])
        self.assertEqual(metadata["document_type"], "技术文件")
        self.assertEqual(metadata["keywords"], ["用地指标"])
        self.assertNotIn("unexpected", metadata)

    def test_region_special_values_are_exclusive(self) -> None:
        with self.assertRaises(MetadataValidationError):
            _normalize_llm_metadata(
                {
                    "region_names": ["全国", "深圳市"],
                    "document_type": "政策",
                    "topics": [],
                    "keywords": [],
                }
            )

    def test_document_id_ignores_random_upload_directories(self) -> None:
        first = _build_document_id(
            {"local_file_path": "output/20260815/task-a/标准.md"},
            "标准",
        )
        second = _build_document_id(
            {"local_file_path": "output/20260816/task-b/标准.md"},
            "标准",
        )

        self.assertEqual(first, second)

    @patch("app.rag.import_.item_name_service.extract_metadata_by_llm")
    def test_extract_document_metadata_writes_minimal_fields(self, mock_extract) -> None:
        mock_extract.return_value = {
            "region_names": ["北京市"],
            "document_type": "政策",
            "topics": ["管理要求"],
            "keywords": ["再生水管理"],
        }
        state = {
            "md_content": "# 北京市再生水管理办法\n适用于北京市行政区域。",
            "file_title": "北京市再生水管理办法",
            "local_file_path": "documents/北京市再生水管理办法.md",
        }

        result = extract_document_metadata(state)
        metadata = result["document_metadata"]

        self.assertEqual(metadata["document_type"], "政策")
        self.assertEqual(metadata["region_names"], ["北京市"])
        self.assertEqual(len(metadata["document_id"]), 64)
        self.assertEqual(
            set(metadata),
            {
                "document_id",
                "region_names",
                "document_type",
                "topics",
                "keywords",
            },
        )
        mock_extract.assert_called_once()


class SplitServiceTest(unittest.TestCase):
    """验证通用 Markdown 标题、表格、代码和最终字段。"""

    def test_split_uses_only_markdown_headings_and_emits_context_types(self) -> None:
        content = """# 水质要求
第一条 这只是普通正文，不是专属法规标题。

表 1 水质指标
| 项目 | 限值 |
| --- | --- |
| 浊度 | 5 |

## 计算示例
```python
limit = 5
print(limit)
```
"""

        chunks = split_document(_split_state(content))["chunks"]
        context_types = {chunk["context_type"] for chunk in chunks}

        self.assertEqual(context_types, {"text", "table", "code"})
        self.assertTrue(
            any("第一条" in chunk["content"] for chunk in chunks)
        )
        self.assertTrue(
            any(chunk["section_title"] == "表 1 水质指标" for chunk in chunks)
        )

    def test_final_chunks_only_keep_new_contract_fields(self) -> None:
        chunks = split_document(
            _split_state("# 第一节\n再生水工程设计内容。")
        )["chunks"]
        required = {
            "chunk_id",
            "document_id",
            "chunk_index",
            "file_title",
            "section_title",
            "content",
            "context_type",
            "token_count",
            "embedding_text",
            "region_names",
            "document_type",
            "topics",
            "keywords",
        }
        removed = {
            "item_name",
            "title",
            "parent_title",
            "part",
            "page_start",
            "page_end",
            "region_codes",
            "clause_number",
            "content_type",
        }

        self.assertEqual(set(chunks[0]), required)
        self.assertFalse(set(chunks[0]) & removed)
        self.assertEqual(chunks[0]["document_type"], "技术文件")
        self.assertGreater(chunks[0]["token_count"], 0)

    def test_oversized_text_is_not_silently_truncated(self) -> None:
        sentences = [f"第{index}句包含再生水工程设计内容。" for index in range(200)]
        content = "# 超长章节\n" + "".join(sentences)

        chunks = split_document(_split_state(content))["chunks"]

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk["content"]) <= 1000 for chunk in chunks))
        self.assertTrue(any("第199句" in chunk["content"] for chunk in chunks))


class EmbeddingAndIndexServiceTest(unittest.TestCase):
    """验证向量化完整性和索引幂等编排。"""

    def _chunks(self) -> list[dict]:
        chunks = split_document(
            _split_state("# 第一节\n再生水工程设计内容。")
        )["chunks"]
        with patch(
            "app.rag.import_.embedding_service.llm_provider.embed_documents",
            return_value=_embed_result(len(chunks)),
        ):
            return embed_chunks(chunks)

    def test_embedding_removes_transient_text_and_preserves_count(self) -> None:
        chunks = self._chunks()

        self.assertEqual(len(chunks), 1)
        self.assertNotIn("embedding_text", chunks[0])
        self.assertEqual(len(chunks[0]["dense_vector"]), 1024)
        self.assertIn("sparse_vector", chunks[0])

    def test_embedding_failure_does_not_skip_batch(self) -> None:
        chunks = split_document(
            _split_state("# 第一节\n再生水工程设计内容。")
        )["chunks"]
        with patch(
            "app.rag.import_.embedding_service.llm_provider.embed_documents",
            side_effect=OSError("model unavailable"),
        ):
            with self.assertRaises(RuntimeError):
                embed_chunks(chunks)

    def test_prepare_records_drops_internal_extra_fields(self) -> None:
        chunks = self._chunks()
        chunks[0]["diagnostic_only"] = True

        records = prepare_chunk_records(chunks)

        self.assertNotIn("diagnostic_only", records[0])
        self.assertNotIn("embedding_text", records[0])
        self.assertEqual(records[0]["chunk_index"], 0)

    @patch(
        "app.rag.import_.index_service._collection_schema_matches",
        return_value=False,
    )
    def test_incompatible_collection_uses_non_destructive_v2_name(
        self,
        mock_schema_matches,
    ) -> None:
        client = Mock()
        client.has_collection.side_effect = (
            lambda *, collection_name: collection_name == "kb_chunks"
        )

        result = _resolve_chunks_collection_name(client, "kb_chunks")

        self.assertEqual(result, "kb_chunks_v2")
        mock_schema_matches.assert_called_once_with(client, "kb_chunks")

    @patch("app.rag.import_.index_service.remove_stale_chunks")
    @patch("app.rag.import_.index_service.upsert_chunks")
    @patch("app.rag.import_.index_service.get_existing_chunk_ids")
    @patch("app.rag.import_.index_service.prepare_chunks_collection")
    def test_index_upserts_before_removing_stale_chunks(
        self,
        mock_prepare,
        mock_existing,
        mock_upsert,
        mock_remove,
    ) -> None:
        chunks = self._chunks()
        current_id = chunks[0]["chunk_id"]
        mock_prepare.return_value = "kb_chunks_v2"
        mock_existing.return_value = {current_id, STALE_CHUNK_ID}
        mock_upsert.return_value = 1
        mock_remove.return_value = 1

        state = {"chunks": chunks, "document_id": DOCUMENT_ID}
        result = index_chunks(state)

        self.assertIs(result, state)
        mock_prepare.assert_called_once_with()
        mock_existing.assert_called_once_with(
            DOCUMENT_ID,
            collection_name="kb_chunks_v2",
        )
        mock_upsert.assert_called_once_with(
            ANY,
            collection_name="kb_chunks_v2",
        )
        mock_remove.assert_called_once_with(
            {STALE_CHUNK_ID},
            collection_name="kb_chunks_v2",
        )


if __name__ == "__main__":
    unittest.main()
