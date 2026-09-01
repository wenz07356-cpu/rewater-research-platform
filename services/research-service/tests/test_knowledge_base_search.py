import asyncio
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

import app.tools.knowledge_base_search as knowledge_search

RESULT_KEYS = {
    "status",
    "provider",
    "query",
    "request_id",
    "chunks",
    "clarification_question",
    "error",
}


def _settings(
    *,
    enabled: bool = True,
    base_url: str | None = "http://knowledge-service:8001",
    top_k: int = 6,
) -> SimpleNamespace:
    return SimpleNamespace(
        enable_knowledge_service=enabled,
        knowledge_service_base_url=base_url,
        knowledge_service_top_k=top_k,
    )


def _valid_chunk(**overrides: Any) -> dict[str, Any]:
    chunk = {
        "chunk_id": "chunk-1",
        "document_id": "doc-1",
        "document_name": "深圳市再生水利用规划",
        "section_title": "再生水利用方向",
        "content": "知识库原始证据。",
        "score": 0.89,
        "internal_debug": "不得透传",
    }
    chunk.update(overrides)
    return chunk


def _install_fake_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    response_data: object | None = None,
    post_error: Exception | None = None,
    json_error: Exception | None = None,
) -> dict[str, Any]:
    calls: dict[str, Any] = {"created": 0, "posts": []}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> object:
            if json_error is not None:
                raise json_error
            return response_data

    class FakeAsyncClient:
        def __init__(self, *, timeout: int) -> None:
            calls["created"] += 1
            calls["timeout"] = timeout

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(
            self,
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, Any],
        ) -> FakeResponse:
            calls["posts"].append({"url": url, "headers": headers, "json": json})
            if post_error is not None:
                raise post_error
            return FakeResponse()

    monkeypatch.setattr(knowledge_search.httpx, "AsyncClient", FakeAsyncClient)
    return calls


def _assert_common_result(result: dict[str, Any]) -> None:
    assert set(result) == RESULT_KEYS
    assert result["provider"] == "knowledge_service"


def test_empty_query_returns_error_without_http_call(monkeypatch):
    calls = _install_fake_client(monkeypatch)

    def fail_get_settings() -> None:
        raise AssertionError("空查询不应读取配置")

    monkeypatch.setattr(knowledge_search, "get_settings", fail_get_settings)

    result = asyncio.run(knowledge_search.knowledge_base_search(" \t\n "))

    _assert_common_result(result)
    assert result["status"] == "error"
    assert result["query"] == ""
    assert result["chunks"] == []
    assert result["request_id"] is None
    assert result["clarification_question"] is None
    assert result["error"] == "query 不能为空"
    assert calls["created"] == 0
    assert calls["posts"] == []


def test_disabled_service_returns_skipped(monkeypatch):
    calls = _install_fake_client(monkeypatch)
    monkeypatch.setattr(
        knowledge_search,
        "get_settings",
        lambda: _settings(enabled=False),
    )

    result = asyncio.run(knowledge_search.knowledge_base_search("深圳市再生水"))

    _assert_common_result(result)
    assert result["status"] == "skipped"
    assert "ENABLE_KNOWLEDGE_SERVICE" in result["error"]
    assert calls["created"] == 0
    assert calls["posts"] == []


def test_missing_base_url_returns_skipped(monkeypatch):
    calls = _install_fake_client(monkeypatch)
    monkeypatch.setattr(
        knowledge_search,
        "get_settings",
        lambda: _settings(base_url=None),
    )

    result = asyncio.run(knowledge_search.knowledge_base_search("深圳市再生水"))

    _assert_common_result(result)
    assert result["status"] == "skipped"
    assert "KNOWLEDGE_SERVICE_BASE_URL" in result["error"]
    assert calls["created"] == 0
    assert calls["posts"] == []


def test_ok_response_posts_expected_payload_and_normalizes_chunks(monkeypatch):
    response_data = {
        "status": "ok",
        "request_id": "request-1",
        "query": "ignored upstream query",
        "chunks": [_valid_chunk(content="  知识库原始证据。  ")],
        "upstream_debug": "不得透传",
    }
    calls = _install_fake_client(monkeypatch, response_data=response_data)
    monkeypatch.setattr(
        knowledge_search,
        "get_settings",
        lambda: _settings(base_url="http://knowledge-service:8001/", top_k=4),
    )

    result = asyncio.run(
        knowledge_search.knowledge_base_search("  深圳市   再生水利用规划  ")
    )

    _assert_common_result(result)
    assert calls["created"] == 1
    assert calls["timeout"] == knowledge_search.REQUEST_TIMEOUT_SECONDS
    assert calls["posts"] == [
        {
            "url": "http://knowledge-service:8001/retrieval",
            "headers": {
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            "json": {"query": "深圳市 再生水利用规划", "top_k": 4},
        }
    ]
    assert result == {
        "status": "ok",
        "provider": "knowledge_service",
        "query": "深圳市 再生水利用规划",
        "request_id": "request-1",
        "chunks": [
            {
                "chunk_id": "chunk-1",
                "document_id": "doc-1",
                "document_name": "深圳市再生水利用规划",
                "section_title": "再生水利用方向",
                "content": "知识库原始证据。",
                "score": 0.89,
                "source_type": "internal_knowledge_base",
                "provider": "knowledge_service",
            }
        ],
        "clarification_question": None,
        "error": None,
    }
    assert "internal_debug" not in result["chunks"][0]
    assert "upstream_debug" not in result


def test_empty_response_preserves_empty_status(monkeypatch):
    calls = _install_fake_client(
        monkeypatch,
        response_data={
            "status": "empty",
            "request_id": "request-empty",
            "chunks": [_valid_chunk()],
        },
    )
    monkeypatch.setattr(knowledge_search, "get_settings", _settings)

    result = asyncio.run(knowledge_search.knowledge_base_search("深圳市再生水"))

    _assert_common_result(result)
    assert result["status"] == "empty"
    assert result["request_id"] == "request-empty"
    assert result["chunks"] == []
    assert result["clarification_question"] is None
    assert result["error"] is None
    assert len(calls["posts"]) == 1


def test_clarification_response_preserves_question(monkeypatch):
    calls = _install_fake_client(
        monkeypatch,
        response_data={
            "status": "needs_clarification",
            "request_id": "request-clarify",
            "clarification_question": "请补充需要查询的地区。",
            "chunks": [_valid_chunk()],
        },
    )
    monkeypatch.setattr(knowledge_search, "get_settings", _settings)

    result = asyncio.run(knowledge_search.knowledge_base_search("当地再生水情况"))

    _assert_common_result(result)
    assert result["status"] == "needs_clarification"
    assert result["request_id"] == "request-clarify"
    assert result["chunks"] == []
    assert result["clarification_question"] == "请补充需要查询的地区。"
    assert result["error"] is None
    assert len(calls["posts"]) == 1


def test_http_error_returns_error_without_raising(monkeypatch):
    request = httpx.Request(
        "POST",
        "http://knowledge-service:8001/retrieval",
        headers={"Authorization": "Bearer secret-token"},
    )
    error = httpx.ConnectError("连接失败，不得包含知识库正文", request=request)
    calls = _install_fake_client(monkeypatch, post_error=error)
    monkeypatch.setattr(knowledge_search, "get_settings", _settings)

    result = asyncio.run(knowledge_search.knowledge_base_search("深圳市再生水"))

    _assert_common_result(result)
    assert result["status"] == "error"
    assert result["chunks"] == []
    assert "ConnectError" in result["error"]
    assert "secret-token" not in result["error"]
    assert len(result["error"]) <= 260
    assert len(calls["posts"]) == 1


def test_invalid_json_returns_protocol_error(monkeypatch):
    calls = _install_fake_client(
        monkeypatch,
        json_error=ValueError("response is not valid JSON"),
    )
    monkeypatch.setattr(knowledge_search, "get_settings", _settings)

    result = asyncio.run(knowledge_search.knowledge_base_search("深圳市再生水"))

    _assert_common_result(result)
    assert result["status"] == "error"
    assert "ValueError" in result["error"]
    assert result["chunks"] == []
    assert len(calls["posts"]) == 1


def test_unknown_upstream_status_returns_protocol_error(monkeypatch):
    calls = _install_fake_client(
        monkeypatch,
        response_data={"status": "partial", "chunks": [_valid_chunk()]},
    )
    monkeypatch.setattr(knowledge_search, "get_settings", _settings)

    result = asyncio.run(knowledge_search.knowledge_base_search("深圳市再生水"))

    _assert_common_result(result)
    assert result["status"] == "error"
    assert "未知 status" in result["error"]
    assert "partial" in result["error"]
    assert result["chunks"] == []
    assert len(calls["posts"]) == 1


def test_invalid_chunks_are_filtered(monkeypatch):
    invalid_chunks = [
        _valid_chunk(chunk_id=""),
        _valid_chunk(document_id=None),
        _valid_chunk(document_name="   "),
        _valid_chunk(content="   "),
        _valid_chunk(score=float("nan")),
        _valid_chunk(score=float("inf")),
        _valid_chunk(score=True),
        _valid_chunk(score="0.89"),
        "not-an-object",
    ]
    calls = _install_fake_client(
        monkeypatch,
        response_data={"status": "ok", "request_id": "request-invalid", "chunks": invalid_chunks},
    )
    monkeypatch.setattr(knowledge_search, "get_settings", _settings)

    result = asyncio.run(knowledge_search.knowledge_base_search("深圳市再生水"))

    _assert_common_result(result)
    assert result["status"] == "empty"
    assert result["request_id"] == "request-invalid"
    assert result["chunks"] == []
    assert result["error"] is None
    assert len(calls["posts"]) == 1


@pytest.mark.parametrize(
    ("requested_top_k", "expected_top_k"),
    [(0, 1), (6, 6), (10, 6)],
)
def test_top_k_is_bounded_to_upstream_contract(
    monkeypatch,
    requested_top_k,
    expected_top_k,
):
    calls = _install_fake_client(
        monkeypatch,
        response_data={"status": "empty", "request_id": "request-top-k", "chunks": []},
    )
    monkeypatch.setattr(knowledge_search, "get_settings", _settings)

    result = asyncio.run(
        knowledge_search.knowledge_base_search("深圳市再生水", top_k=requested_top_k)
    )

    assert result["status"] == "empty"
    sent_top_k = calls["posts"][0]["json"]["top_k"]
    assert sent_top_k == expected_top_k
    assert type(sent_top_k) is int


@pytest.mark.parametrize("invalid_top_k", ["not-a-number", 1.5, True])
def test_invalid_top_k_returns_error_without_http_call(monkeypatch, invalid_top_k):
    calls = _install_fake_client(monkeypatch)
    monkeypatch.setattr(knowledge_search, "get_settings", _settings)

    result = asyncio.run(
        knowledge_search.knowledge_base_search("深圳市再生水", top_k=invalid_top_k)
    )

    _assert_common_result(result)
    assert result["status"] == "error"
    assert "top_k" in result["error"]
    assert calls["created"] == 0
    assert calls["posts"] == []
