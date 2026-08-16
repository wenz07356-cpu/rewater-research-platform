"""导入流程的集中配置常量。"""

# MinerU PDF 解析配置。
MINERU_MODEL_VERSION = "vlm"
MINERU_POLL_TIMEOUT_SECONDS = 600
MINERU_POLL_INTERVAL_SECONDS = 3
MINERU_DOWNLOAD_TIMEOUT_SECONDS = 30
PDF_PARSE_SERVICE_LOCAL_DIR = "output"

# Markdown 图片处理配置。
SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}

# 文本切块配置，单位均为字符数。
CHUNK_MAX_SIZE = 1000
CHUNK_SIZE = 600
CHUNK_OVERLAP = int(CHUNK_SIZE * 0.05)
CHUNK_MIN = 300
TABLE_MAX_SIZE = CHUNK_MAX_SIZE
CODE_MAX_SIZE = CHUNK_MAX_SIZE
CHUNK_BACKUP_ENABLED = True

# 文档 metadata 只使用正文前 10000 个字符。
METADATA_CONTEXT_MAX_CHARS = 10000
METADATA_LLM_RETRY = 1
REGION_NAMES_MAX_COUNT = 8
TOPICS_MAX_COUNT = 5
KEYWORDS_MAX_COUNT = 10
METADATA_ITEM_MAX_LENGTH = 128

# Milvus 字段和批处理配置。
MILVUS_DEFAULT_VARCHAR_MAX_LENGTH = 512
MILVUS_CHUNK_CONTENT_MAX_LENGTH = 65535
MILVUS_VECTOR_DIM = 1024
MILVUS_ARRAY_ITEM_MAX_LENGTH = 128
MILVUS_WRITE_BATCH_SIZE = 100

# Embedding 批处理配置。
EMBEDDING_BATCH_SIZE = 5


def validate_import_config() -> None:
    """校验导入核心参数之间的约束。

    核心功能：在模块加载或测试时尽早发现无法工作的切块配置。
    输入：无，读取本模块常量。
    输出：无；配置非法时抛出 ``ValueError``。
    步骤：校验 overlap、最小长度、目标长度和最大长度的递增关系。
    """
    if not 0 <= CHUNK_OVERLAP < CHUNK_MIN <= CHUNK_SIZE <= CHUNK_MAX_SIZE:
        raise ValueError("切块参数必须满足 0 <= overlap < min <= size <= max")
    if METADATA_CONTEXT_MAX_CHARS <= 0:
        raise ValueError("METADATA_CONTEXT_MAX_CHARS 必须大于 0")
    if EMBEDDING_BATCH_SIZE <= 0 or MILVUS_WRITE_BATCH_SIZE <= 0:
        raise ValueError("批处理大小必须大于 0")


validate_import_config()
