"""查询链路的集中配置常量。"""

DOCUMENT_TYPES = ("政策", "标准", "规划", "技术文件", "其他")
HARD_FILTER_FIELDS = ("region_names", "document_types")

QUERY_HISTORY_MESSAGE_LIMIT = 6
QUERY_HISTORY_MAX_CHARS = 4000
ORIGINAL_QUERY_MAX_CHARS = 2000
REWRITTEN_QUERY_MAX_CHARS = 200
QUERY_FILTER_MAX_VALUES = 10
RETRIEVAL_QUERY_MAX_CHARS = 500

SEARCH_ANN_LIMIT = 20
SEARCH_TOP_K = 10
DENSE_WEIGHT = 0.6
SPARSE_WEIGHT = 0.4

HYDE_MAX_CHARS = 300
WEB_SEARCH_TOP_K = 5
WEB_CONNECT_TIMEOUT_SECONDS = 30
WEB_READ_TIMEOUT_SECONDS = 60

RRF_K = 60
RRF_EMBEDDING_WEIGHT = 1.0
RRF_HYDE_WEIGHT = 0.8
RRF_TOP_K = 12

RERANK_MAX_TOPK = 6
RERANK_MIN_TOPK = 2
RERANK_GAP_RATIO = 0.2
RERANK_GAP_ABS = 0.2
RERANK_MAX_INPUT_TOKENS = 512
RERANK_SUMMARY_CHAR_RATIO = 1.3
RERANK_MIN_SUMMARY_CHARS = 50
RERANK_MAX_PER_DOCUMENT = 2

ANSWER_MAX_CONTEXT_CHARS = 20_000
SUPPORTED_IMAGE_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".webp",
)

LOCAL_OUTPUT_FIELDS = [
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
]


def default_query_filters() -> dict:
    """返回独立的空查询过滤结构，避免共享可变默认值。"""
    return {
        "file_titles": [],
        "region_names": [],
        "document_types": [],
        "topics": [],
        "keywords": [],
        "hard_fields": [],
        "strict": False,
    }
