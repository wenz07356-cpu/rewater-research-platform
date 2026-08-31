"""Query HTTP 请求、响应与公开检索元数据模型。"""

from enum import Enum
from typing import Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)

class RetrievalMode(str, Enum):
    BALANCED = "balanced"
    PRECISION = "precision"
    RECALL = "recall"
    CUSTOM = "custom"


class MatchingPreference(str, Enum):
    KEYWORD = "keyword"
    BALANCED = "balanced"
    SEMANTIC = "semantic"


class HydeInfluence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CustomRetrievalOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_top_k: int = Field(ge=5, le=25, strict=True)
    max_reference_count: int = Field(ge=1, le=12, strict=True)
    matching_preference: MatchingPreference
    hyde_enabled: StrictBool
    hyde_influence: HydeInfluence
    # 兼容旧客户端；新客户端应使用 QueryRequest.web_enabled 独立控制联网搜索。
    web_enabled: StrictBool | None = None


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, max_length=2000, description="用户查询内容")
    session_id: str | None = Field(default=None, max_length=200, description="会话ID")
    is_stream: bool = Field(default=False, description="是否使用SSE流式输出")
    retrieval_mode: RetrievalMode | None = None
    retrieval_options: CustomRetrievalOptions | None = None
    web_enabled: StrictBool | None = None

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        value = " ".join(value.split()).strip()
        if not value:
            raise ValueError("query 不能为空")
        return value

    @field_validator("session_id")
    @classmethod
    def normalize_session_id(cls, value: str | None) -> str | None:
        value = str(value or "").strip()
        return value or None

    @model_validator(mode="after")
    def validate_mode_options(self) -> Self:
        if self.retrieval_mode == RetrievalMode.CUSTOM:
            if self.retrieval_options is None:
                raise ValueError("custom 模式必须提供 retrieval_options")
        elif self.retrieval_options is not None:
            raise ValueError("仅 custom 模式允许 retrieval_options")
        return self


class RetrievalSummary(BaseModel):
    search_breadth: str = "适中"
    reference_range: str = ""
    matching_preference: str = "均衡"
    hyde_enabled: bool = True
    web_enabled: bool = True


class RetrievalCounts(BaseModel):
    embedding: int = Field(default=0, ge=0)
    hyde: int = Field(default=0, ge=0)
    local_fused: int = Field(default=0, ge=0)
    web: int = Field(default=0, ge=0)
    final_context: int = Field(default=0, ge=0)


class RetrievalMetadata(BaseModel):
    mode: RetrievalMode
    mode_label: str
    summary: RetrievalSummary = Field(default_factory=RetrievalSummary)
    counts: RetrievalCounts = Field(default_factory=RetrievalCounts)
    degradations: list[str] = Field(default_factory=list)


class QueryResponse(BaseModel):
    message: str
    session_id: str
    answer: str = ""
    done_list: list[str] = Field(default_factory=list)
    image_urls: list[str] = Field(default_factory=list)
    retrieval_metadata: RetrievalMetadata | None = None


class RetrievalRequest(BaseModel):
    """DeepAgent 证据检索请求。"""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=6, ge=1, le=6, strict=True)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        value = " ".join(value.split()).strip()
        if not value:
            raise ValueError("query 不能为空")
        return value


class RetrievalChunk(BaseModel):
    """返回给 DeepAgent 的单条知识库证据。"""

    chunk_id: str
    document_id: str
    document_name: str
    section_title: str = ""
    content: str
    score: float


class RetrievalResponse(BaseModel):
    """DeepAgent 证据检索响应。"""

    status: Literal["ok", "empty", "needs_clarification"]
    request_id: str
    query: str
    clarification_question: str = ""
    chunks: list[RetrievalChunk] = Field(default_factory=list)


class HistoryItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default="", alias="_id")
    session_id: str = ""
    role: str = ""
    text: str = ""
    rewritten_query: str = ""
    item_names: list[str] = Field(default_factory=list)
    query_filters: dict[str, Any] = Field(default_factory=dict)
    image_urls: list[str] = Field(default_factory=list)
    retrieval_metadata: RetrievalMetadata | None = None
    ts: Any = None


class HistoryResponse(BaseModel):
    session_id: str
    items: list[HistoryItem] = Field(default_factory=list)
