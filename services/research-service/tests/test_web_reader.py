from urllib.error import HTTPError, URLError

import pytest

import app.tools.web_reader as web_reader


def _http_error(status_code: int) -> HTTPError:
    return HTTPError(
        url="https://example.test/page",
        code=status_code,
        msg="test error",
        hdrs=None,
        fp=None,
    )


def test_fetch_html_uses_environment_route_first(monkeypatch):
    calls = []

    def fake_fetch_once(url, *, use_environment_proxy, timeout):
        calls.append((url, use_environment_proxy, timeout))
        return "<html>ok</html>", url, "text/html"

    monkeypatch.setattr(web_reader, "_has_environment_proxy", lambda _url: True)
    monkeypatch.setattr(web_reader, "_fetch_html_once", fake_fetch_once)

    result = web_reader._fetch_html("https://example.test/page")

    assert result == ("<html>ok</html>", "https://example.test/page", "text/html")
    assert calls == [
        ("https://example.test/page", True, web_reader.REQUEST_TIMEOUT_SECONDS)
    ]


def test_fetch_html_falls_back_to_direct_after_proxy_502(monkeypatch):
    calls = []

    def fake_fetch_once(url, *, use_environment_proxy, timeout):
        calls.append((use_environment_proxy, timeout))
        if len(calls) == 1:
            raise _http_error(502)
        return "<html>direct</html>", url, "text/html"

    monkeypatch.setattr(web_reader, "_has_environment_proxy", lambda _url: True)
    monkeypatch.setattr(web_reader, "_fetch_html_once", fake_fetch_once)
    monkeypatch.setattr(web_reader.time, "sleep", lambda _seconds: None)

    result = web_reader._fetch_html("https://example.test/page")

    assert result[0] == "<html>direct</html>"
    assert calls == [
        (True, web_reader.REQUEST_TIMEOUT_SECONDS),
        (False, web_reader.DIRECT_FALLBACK_TIMEOUT_SECONDS),
    ]


def test_fetch_html_retries_proxy_when_direct_fallback_fails(monkeypatch):
    calls = []

    def fake_fetch_once(url, *, use_environment_proxy, timeout):
        calls.append((use_environment_proxy, timeout))
        if len(calls) == 1:
            raise URLError("proxy TLS EOF")
        if len(calls) == 2:
            raise URLError("direct connection blocked")
        return "<html>proxy retry</html>", url, "text/html"

    monkeypatch.setattr(web_reader, "_has_environment_proxy", lambda _url: True)
    monkeypatch.setattr(web_reader, "_fetch_html_once", fake_fetch_once)
    monkeypatch.setattr(web_reader.time, "sleep", lambda _seconds: None)

    result = web_reader._fetch_html("https://example.test/page")

    assert result[0] == "<html>proxy retry</html>"
    assert calls == [
        (True, web_reader.REQUEST_TIMEOUT_SECONDS),
        (False, web_reader.DIRECT_FALLBACK_TIMEOUT_SECONDS),
        (True, web_reader.REQUEST_TIMEOUT_SECONDS),
    ]


@pytest.mark.parametrize("status_code", [400, 403, 404])
def test_fetch_html_does_not_retry_non_retryable_http_errors(monkeypatch, status_code):
    calls = []

    def fake_fetch_once(url, *, use_environment_proxy, timeout):
        calls.append((use_environment_proxy, timeout))
        raise _http_error(status_code)

    monkeypatch.setattr(web_reader, "_has_environment_proxy", lambda _url: True)
    monkeypatch.setattr(web_reader, "_fetch_html_once", fake_fetch_once)

    with pytest.raises(HTTPError) as exc_info:
        web_reader._fetch_html("https://example.test/page")

    assert exc_info.value.code == status_code
    assert calls == [(True, web_reader.REQUEST_TIMEOUT_SECONDS)]
