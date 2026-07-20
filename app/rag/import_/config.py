# MinerU 模型版本配置（vlm = 视觉语言模型，适合PDF/图片高精度解析）
MINERU_MODEL_VERSION = "vlm"
# MinerU 任务轮询最大超时时间（单位：秒），超过则判定任务失败
# 600 -> 一个pdf 约等于 1秒
MINERU_POLL_TIMEOUT_SECONDS = 600
# MinerU 任务轮询间隔时间（单位：秒），每隔多久查询一次任务状态
MINERU_POLL_INTERVAL_SECONDS = 3
# MinerU 文件下载超时时间（单位：秒），下载文件超过此时长则中断
MINERU_DOWNLOAD_TIMEOUT_SECONDS = 30

#定义local_dir对应输出的常来那个
PDF_PARSE_SERVICE_LOCAL_DIR = "output"

#图片后缀
SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}

#文本切块最大长度：单个文本块最多包含1000个
CHUNK_MAX_SIZE = 1000
#文本切块基准长度：单个文本块理想长度
CHUNK_SIZE = 600
#文本块重叠长度：相邻块之间重叠20字符
CHUNK_OVERLAP = 20
#最小碎片阈值：低于这个长度判定为短碎片，需要缝合
CHUNK_MIN = 400


ITEM_NAME_CONTEXT_CHUNK_K = 5
ITEM_NAME_CONTEXT_TOTAL_MAX_CHARS = 10000
MILVUS_DEFAULT_VARCHAR_MAX_LENGTH = 512
MILVUS_CHUNK_CONTENT_MAX_LENGTH = 65535
MILVUS_VECTOR_DIM = 1024

EMBEDDING_BATCH_SIZE = 5
