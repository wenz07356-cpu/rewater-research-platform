import asyncio
import re
import time
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener, getproxies, proxy_bypass, urlopen

from loguru import logger

REQUEST_TIMEOUT_SECONDS = 30
DIRECT_FALLBACK_TIMEOUT_SECONDS = 10
RETRY_DELAY_SECONDS = 0.5
DEFAULT_MAX_CHARS = 12000
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0 Safari/537.36"
)
RETRYABLE_HTTP_STATUS_CODES = {429, 500, 502, 503, 504}


async def read_web_page(url: str, max_chars: int = DEFAULT_MAX_CHARS) -> dict[str, Any]:
    """读取网页正文和基础元数据。

    输入为 URL；输出为标题、发布时间线索、正文摘要和读取状态。该工具只做轻量解析，
    不对网页内容做事实判断。
    """

    normalized_url = url.strip()
    if not normalized_url.startswith(("http://", "https://")):
        return {
            "status": "error",
            "url": url,
            "title": None,
            "published_at": None,
            "content": "",
            "error": "仅支持 http 或 https URL",
        }

    try:
        html, final_url, content_type = await asyncio.to_thread(_fetch_html, normalized_url)
    except (HTTPError, URLError, TimeoutError, UnicodeDecodeError, OSError) as exc:
        logger.warning("网页读取失败，url={}, error={}", normalized_url, exc)
        return {
            "status": "error",
            "url": normalized_url,
            "title": None,
            "published_at": None,
            "content": "",
            "error": str(exc),
        }

    parser = _ReadableHtmlParser()
    parser.feed(html)
    content = _normalize_space(" ".join(parser.text_parts))
    limited_content = content[: max(500, min(max_chars, 30000))]
    title = parser.title or _extract_title(html)
    published_at = parser.published_at or _extract_published_at(html)

    logger.info("网页读取完成，url={}, chars={}", final_url, len(limited_content))
    return {
        "status": "ok",
        "url": final_url,
        "title": title,
        "published_at": published_at,
        "content_type": content_type,
        "content": limited_content,
        "truncated": len(content) > len(limited_content),
        "source_type": "public_web",
    }


def _fetch_html(url: str) -> tuple[str, str, str | None]:
    routes: list[tuple[str, bool, int]] = [
        ("environment_proxy", True, REQUEST_TIMEOUT_SECONDS)
    ]
    if _has_environment_proxy(url):
        routes.append(("direct_fallback", False, DIRECT_FALLBACK_TIMEOUT_SECONDS))
        routes.append(("environment_proxy_retry", True, REQUEST_TIMEOUT_SECONDS))
    else:
        routes.append(("direct_retry", False, REQUEST_TIMEOUT_SECONDS))

    last_error: Exception | None = None
    for attempt, (route, use_environment_proxy, timeout) in enumerate(routes, start=1):
        try:
            return _fetch_html_once(
                url,
                use_environment_proxy=use_environment_proxy,
                timeout=timeout,
            )
        except (HTTPError, URLError, TimeoutError, UnicodeDecodeError, OSError) as exc:
            last_error = exc
            if not _is_retryable_fetch_error(exc) or attempt == len(routes):
                raise
            logger.debug(
                "网页请求尝试失败，url={}，route={}，attempt={}/{}，error={}",
                url,
                route,
                attempt,
                len(routes),
                exc,
            )
            time.sleep(RETRY_DELAY_SECONDS)

    if last_error is not None:
        raise last_error
    raise OSError("网页请求未执行")


def _fetch_html_once(
    url: str,
    *,
    use_environment_proxy: bool,
    timeout: int,
) -> tuple[str, str, str | None]:
    request = Request(
        url=url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
            "Cache-Control": "no-cache",
        },
    )
    if use_environment_proxy:
        response_context = urlopen(request, timeout=timeout)
    else:
        response_context = build_opener(ProxyHandler({})).open(request, timeout=timeout)

    with response_context as response:
        raw = response.read()
        content_type = response.headers.get("Content-Type")
        encoding = response.headers.get_content_charset() or "utf-8"
        return raw.decode(encoding, errors="replace"), response.geturl(), content_type


def _has_environment_proxy(url: str) -> bool:
    parsed = urlsplit(url)
    if not parsed.hostname or proxy_bypass(parsed.hostname):
        return False
    proxies = getproxies()
    return bool(proxies.get(parsed.scheme) or proxies.get("all"))


def _is_retryable_fetch_error(exc: Exception) -> bool:
    if isinstance(exc, HTTPError):
        return exc.code in RETRYABLE_HTTP_STATUS_CODES
    return isinstance(exc, (URLError, TimeoutError, OSError)) and not isinstance(
        exc,
        UnicodeDecodeError,
    )


class _ReadableHtmlParser(HTMLParser):
    """轻量 HTML 正文提取器，跳过脚本、样式和导航噪音标签。"""

    def __init__(self) -> None:
        super().__init__()
        self.text_parts: list[str] = []
        self.title: str | None = None
        self.published_at: str | None = None
        self._ignored_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg", "nav", "footer"}:
            self._ignored_depth += 1
            return
        if tag == "title":
            self._in_title = True
            return
        if tag == "meta":
            self._handle_meta(attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg", "nav", "footer"}:
            self._ignored_depth = max(0, self._ignored_depth - 1)
            return
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        normalized = _normalize_space(data)
        if not normalized:
            return
        if self._in_title:
            self.title = normalized
            return
        if self._ignored_depth == 0:
            self.text_parts.append(normalized)

    def _handle_meta(self, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): value for key, value in attrs if value is not None}
        meta_key = (attr_map.get("property") or attr_map.get("name") or "").lower()
        content = attr_map.get("content")
        if meta_key in {"article:published_time", "datepublished", "pubdate", "date"} and content:
            self.published_at = content


def _extract_title(html: str) -> str | None:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return _normalize_space(re.sub(r"<[^>]+>", " ", match.group(1)))


def _extract_published_at(html: str) -> str | None:
    patterns = [
        r'"datePublished"\s*:\s*"([^"]+)"',
        r'"dateModified"\s*:\s*"([^"]+)"',
        r"(\d{4}-\d{2}-\d{2}(?:[T ][0-9:]+(?:Z|[+-]\d{2}:?\d{2})?)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
