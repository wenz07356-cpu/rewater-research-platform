# query 模块 V1 函数级业务设计

## 1. 目标与边界

本文在 [query.md](./query.md) 的总体方案上，进一步明确 query 各 service、节点和 Prompt 的业务逻辑，为后续编码提供直接依据。

本版本只描述函数职责、输入、输出、步骤和参数选择，不提供实现代码。总体框架和现有资源保持不变：

```text
查询理解
  -> 普通混合检索 ─┐
  -> HyDE 混合检索 ├-> RRF -> Reranker -> 答案输出
  -> Web Search ────┘
```

继续使用 LangGraph、大模型、BGE-M3、Milvus、BGE Reranker、DashScope MCP、MongoDB 和 SSE。

## 2. 统一业务契约

### 2.1 节点与 service 返回原则

- service 入口返回该节点负责的状态增量。
- node 只负责进度日志、调用 service、原样返回状态增量，不能再次包装。
- 并行检索节点不得修改完整共享 state，只返回自己拥有的字段。
- 参数缺失、schema 错误属于不可恢复错误，应抛出异常。
- 某一路外部检索失败或没有命中属于可恢复情况，应记录日志并返回空列表。

节点输出约定：

| 节点 | service 入口 | 节点输出 |
| --- | --- | --- |
| `node_item_name_confirm` | `understand_query` | `rewritten_query/query_filters/history/answer` |
| `node_search_embedding` | `search_chunks` | `embedding_chunks` |
| `node_search_embedding_hyde` | `search_chunks_with_hyde` | `hyde_embedding_chunks` |
| `node_web_search_mcp` | `search_web_documents` | `web_search_docs` |
| `node_rrf` | `fuse_retrieval_results` | `rrf_chunks` |
| `node_rerank` | `rerank_documents` | `reranked_docs` |
| `node_answer_output` | `produce_answer` | `answer/image_urls` 及落库结果 |

为降低一次性改名影响，可暂时保留旧入口名作为兼容别名，但主图、`app.rag.query.__init__` 和 service 实际定义最终必须使用同一组名称。

### 2.2 `query_filters` 结构

```text
query_filters:
  file_titles: list[str]
  region_names: list[str]
  document_types: list[str]
  topics: list[str]
  keywords: list[str]
  hard_fields: list[str]
  strict: bool
```

说明：

- `hard_fields` 只允许 `file_titles`、`region_names`、`document_types`。
- `topics`、`keywords` 在 V1 中只用于增强查询，不参与硬过滤。
- `file_titles` 默认作为软条件；只有用户明确表达“只查某份完整文件”时才进入 `hard_fields`。
- `strict=True` 只表示用户出现“仅、只、必须限定”等明确排他表达，不能由模型自行猜测。
- 空 `query_filters` 是合法状态，表示全库语义检索。

### 2.3 本地候选统一结构

```text
chunk_id、document_id、chunk_index、file_title、section_title、display_title、
content、context_type、region_names、document_type、topics、keywords、
score、source、retrieval_source、url
```

- `source`：本地统一为 `milvus`。
- `retrieval_source`：普通检索为 `embedding`，HyDE 为 `hyde`。
- `display_title`：`section_title` 有效且不同于 `file_title` 时为 `file_title / section_title`，否则为 `file_title`。
- `content` 始终保存原始完整 chunk，重排压缩不得覆盖它。

### 2.4 Web 候选统一结构

Web 候选也使用 `display_title/content/score/source/retrieval_source/url`，其中：

- `source`、`retrieval_source` 均为 `web`。
- 本地专属字段使用 `None` 或空列表。
- Web 结果以规范化 URL 去重；URL 为空时使用标题和摘要组合去重。

### 2.5 LangGraph 节点业务逻辑

节点层不承载检索细节，每个节点只执行进度登记、service 调用和状态增量返回。

#### `def node_item_name_confirm(state) -> dict`

核心功能：执行查询理解入口节点。

输入：至少包含 `session_id/original_query/is_stream` 的 state。

输出：`understand_query` 返回的状态增量。

步骤：

1. 登记节点开始。
2. 调用 `understand_query(state)`。
3. 校验返回值包含有效 `rewritten_query`，或包含非空澄清 `answer`。
4. 登记节点完成并原样返回结果。

说明：节点名可以暂时保留，前端任务名称应从“确认问题产品/主体”改为“理解查询范围”。

#### `def node_item_name_confirm_after_router(state) -> str | tuple[str, ...]`

核心功能：根据查询理解结果决定澄清或并行检索。

输入：查询理解完成后的 state。

输出：答案节点名称，或三个并行检索节点名称。

步骤：

1. `answer` 非空时路由到 `node_answer_output`。
2. `answer` 为空且 `rewritten_query` 有效时，同时路由到普通检索、HyDE 和 Web 节点。
3. 两者均无效属于状态契约错误，记录 ERROR 并抛出。
4. 不再根据 `item_names` 判断是否允许检索。

#### `def node_search_embedding(state) -> dict`

核心功能：调度普通本地检索。

输入：查询理解后的 state。

输出：严格为 `{"embedding_chunks": list}`。

步骤：登记开始，调用 `search_chunks`，校验输出列表类型，登记完成，原样返回；不得再包装成第二层 `embedding_chunks`。

#### `def node_search_embedding_hyde(state) -> dict`

核心功能：调度 HyDE 本地检索。

输入：查询理解后的 state。

输出：严格为 `{"hyde_embedding_chunks": list}`。

步骤：登记开始，调用 `search_chunks_with_hyde`，校验输出列表类型，登记完成，原样返回。

#### `def node_web_search_mcp(state) -> dict`

核心功能：调度网络搜索。

输入：查询理解后的 state。

输出：严格为 `{"web_search_docs": list}`。

步骤：登记开始，调用 `search_web_documents`，校验输出列表类型，登记完成，原样返回。

#### `def node_rrf(state) -> dict`

核心功能：在三个并行分支汇合后融合两路本地结果。

输入：包含普通、HyDE、Web 分支结果的 state。

输出：严格为 `{"rrf_chunks": list}`。

步骤：登记开始，调用 `fuse_retrieval_results`，登记完成，原样返回。Web 结果此时只完成并行汇合，不参与 RRF 公式。

#### `def node_rerank(state) -> dict`

核心功能：调度本地与 Web 候选统一精排。

输入：包含 `rewritten_query/rrf_chunks/web_search_docs` 的 state。

输出：严格为 `{"reranked_docs": list}`。

步骤：登记开始，调用 `rerank_documents`，校验列表类型，登记完成，原样返回。

#### `def node_answer_output(state) -> dict`

核心功能：调度统一答案出口。

输入：澄清分支的 state，或完成精排后的 state。

输出：至少包含 `answer/image_urls`。

步骤：登记开始，调用 `produce_answer`，完成流式/非流式输出和落库，登记完成，原样返回。

---

# 第一部分：`app\rag\query\item_name_confirm_service.py`

## 整体思路

文件名可暂时保留以减少改造范围，但业务含义从“主体名称确认”改为“查询理解与检索范围抽取”。推荐后续重命名为 `query_understanding_service.py`，入口函数使用 `understand_query`。

核心原理：当前问题是主要依据，近期历史仅用于指代消解；大模型负责结构化理解，代码负责类型、枚举、长度和硬过滤资格校验。没有文件标题或 metadata 条件时正常检索，不能要求用户补充主体。

核心原则：

- 不再访问 `item_name_collection`。
- 不再生成或确认 `item_names`。
- 文档类型只允许：`政策`、`标准`、`规划`、`技术文件`、`其他`。
- `topics/keywords` 永远先作为软条件。
- 模型输出不直接信任，必须规范化。
- 只有空问题、无法消解的关键指代或互相冲突的严格条件才生成澄清回答。
- 本节点完成后保存用户消息；历史写入失败应记录错误，但是否阻断主查询由项目一致性要求决定，V1 建议不阻断检索。

## 函数中文说明

### `def validate_query_input(state) -> tuple[str, str]`

核心功能：获取并校验查询入口参数。

输入：`state`，查询图节点状态。

输出：`session_id`、清洗后的 `original_query`。

步骤：

1. 获取 `session_id` 和 `original_query`。
2. 校验两者为非空字符串。
3. 去除问题首尾空白并统一连续空白。
4. 校验问题长度不超过入口允许上限；超长时拒绝或在 API 层提前限制，不能静默丢失问题尾部。
5. 返回规范化结果。

### `def load_recent_history(session_id) -> list[dict]`

核心功能：从 MongoDB 获取用于指代消解的近期对话。

输入：`session_id`。

输出：按时间正序排列的近期消息列表。

步骤：

1. 查询最近 `QUERY_HISTORY_MESSAGE_LIMIT` 条记录。
2. 不再按 `item_names` 非空过滤消息。
3. 保留用户问题、改写问题、回答摘要、旧 `item_names` 和新版 `query_filters`。
4. 将旧 `item_names` 仅作为旧版文件标题线索，不恢复旧的强约束语义。
5. 无历史时返回空列表并记录 INFO，不视为异常。

### `def build_history_context(messages) -> str`

核心功能：把历史消息转换为受长度控制的 Prompt 上下文。

输入：近期消息列表。

输出：`history_text`。

步骤：

1. 按对话顺序标记用户和助手角色。
2. 用户消息优先使用 `rewritten_query`，为空时使用原始 `text`。
3. 助手消息只保留摘要，不把历史答案当作事实证据。
4. 附加已有查询范围；旧 `item_names` 标注为“旧版文件标题线索”。
5. 从最近消息向前保留内容，总长度不超过 `QUERY_HISTORY_MAX_CHARS`。
6. 无历史时返回“无历史对话”。

### `def call_llm_query_understanding(original_query, history_text) -> dict`

核心功能：调用 JSON 模式大模型完成问题改写、范围抽取和澄清判断。

输入：当前原始问题、历史上下文文本。

输出：大模型原始字典结果。

步骤：

1. 加载 `query_understanding.prompt`。
2. 使用 `json_mode=True` 的聊天模型和 JSON 解析器。
3. 传入当前问题和历史上下文。
4. 获取结构化结果。
5. JSON 无法解析或调用失败时记录 ERROR；service 总入口回退为“原问题 + 空过滤”的全库检索，不能使用半结构化结果生成过滤条件。

### `def normalize_query_understanding(raw_result, original_query) -> dict`

核心功能：校验并规范化模型输出，生成可信的查询理解结果。

输入：模型原始结果、原始问题。

输出：规范化后的 `rewritten_query`、`query_filters`、澄清字段。

步骤：

1. 校验结果为字典；缺少 `rewritten_query` 时回退到原始问题。
2. 清洗改写问题，限制在 `REWRITTEN_QUERY_MAX_CHARS` 内；不得截断到语义不完整。
3. 将各过滤值转为去空、去重的字符串列表，并限制每个列表数量。
4. 删除非法 `document_types`。
5. 校验 `hard_fields` 白名单；`topics/keywords` 即使被模型标为 hard 也强制移除。
6. `file_titles` 只有在原问题明确出现完整标题且存在排他表达时才允许硬过滤，否则转为软条件。
7. `region_names/document_types` 只有当前问题明确表达，或通过清晰指代继承时才允许硬过滤。
8. 校验 `needs_clarification` 和 `clarification_question` 一致性。
9. 没有任何范围时保留空过滤结构，不能生成澄清。

### `def apply_query_understanding(state, result, history) -> dict`

核心功能：将查询理解结果转换为本节点状态增量。

输入：当前 state、规范化理解结果、已加载的历史消息。

输出：包含 `rewritten_query/query_filters/history/answer` 的状态增量。

步骤：

1. 写入 `rewritten_query` 和 `query_filters`。
2. 写入本轮已加载的精简历史，供答案节点复用。
3. 需要澄清时写入 `answer=clarification_question`。
4. 不需要澄清时写入空 `answer`，允许条件路由进入三路检索。
5. 不再写入 `item_names`。

### `def save_user_query_history(state, state_update) -> None`

核心功能：保存本轮用户问题及查询理解结果。

输入：原始查询 state、查询理解后的状态增量。

输出：无。

步骤：

1. 从原始 state 获取 `session_id/original_query`，保存 `session_id/role/text/rewritten_query/query_filters`。
2. `image_urls` 使用空列表。
3. 为旧数据兼容，可暂时保留空 `item_names`，但不再参与业务判断。
4. 写入失败记录 ERROR；V1 建议不影响本轮检索执行。

### `def understand_query(state) -> dict`

核心功能：编排查询理解 service 的完整流程。

输入：查询图 state。

输出：本节点状态增量。

步骤：

1. 校验入口参数。
2. 加载并格式化近期历史。
3. 调用大模型获取结构化理解结果。
4. 规范化改写问题、查询范围和澄清判断。
5. 生成状态增量。
6. 保存用户历史。
7. 记录改写长度、硬过滤字段和是否澄清，不记录完整 Prompt。

---

# 第二部分：`app\rag\query\search_embedding_service.py`

## 整体思路

该 service 是本地知识库召回基线。使用 BGE-M3 对检索文本生成稠密、稀疏向量，通过 Milvus WeightedRanker 执行混合检索。无 metadata 限制时执行全库检索。

V1 选择稠密/稀疏权重 `0.6/0.4`：自然语言问答更依赖语义相似，政策名称、术语和数字又需要稀疏检索补充。该权重先保持现有倾向，后续必须用评测集调整。

## 函数中文说明

### `def normalize_query_filters(value) -> dict`

核心功能：为普通检索、HyDE、Web 和答案服务提供同一份查询过滤规范化能力。

输入：任意来源的 `query_filters`。

输出：字段完整、列表去重、枚举合法的过滤结构。

步骤：补齐默认字段，清洗字符串列表，删除非法文档类型和空 hard field，并规范化 strict。该函数只在 `search_embedding_service.py` 定义，其他 service 直接复用，避免重复规则。

### `def validate_retrieval_state(state) -> tuple[str, dict]`

核心功能：校验普通检索需要的改写问题和查询范围。

输入：查询图 state。

输出：`rewritten_query`、规范化 `query_filters`。

步骤：

1. 获取并校验非空 `rewritten_query`。
2. 获取 `query_filters`，为空时补默认结构。
3. 再次校验过滤字段类型和枚举，防止绕过入口节点调用 service。
4. 返回结果；不再校验 `item_names`。

### `def build_retrieval_query(rewritten_query, query_filters) -> str`

核心功能：将软条件转换为适合向量化的检索文本。

输入：改写问题、查询范围。

输出：`retrieval_query`。

步骤：

1. 以 `rewritten_query` 为主体。
2. 追加软文件标题、地域、主题和关键词，使用清晰字段标签。
3. 已在问题中出现的词不重复追加。
4. 控制总长度，优先保留原问题、文件标题、主题，再保留关键词。
5. 不追加空字段和内部控制字段。

### `def build_milvus_filter_expr(query_filters) -> str | None`

核心功能：把可信硬条件转换为安全的 Milvus 标量过滤表达式。

输入：规范化 `query_filters`。

输出：Milvus `expr` 或 `None`。

步骤：

1. 只处理 `hard_fields` 中允许的字段。
2. `file_titles` 使用受控字符串列表进行等值/IN 过滤。
3. `document_types` 使用中文枚举 IN 过滤。
4. 地域按产品语义处理：明确“仅本地”时只包含指定地域；询问“在某地适用”时可包含指定地域与“全国”。
5. 不把“不限”自动当作“全国”；技术文件或文种未限定时，地域优先作为软条件。
6. 同字段多值使用 OR，不同字段使用 AND。
7. 使用 JSON 序列化或统一转义工具构造字面量，严禁拼接原始用户字符串。
8. 无硬条件时返回 `None`。

### `def embed_retrieval_query(retrieval_query) -> tuple[list[float], dict[int, float]]`

核心功能：生成 BGE-M3 稠密和稀疏查询向量。

输入：检索文本。

输出：单条稠密向量、单条稀疏向量。

步骤：

1. 批量接口传入单元素列表。
2. 校验 dense 和 sparse 均存在且数量为 1。
3. 校验稠密向量维度与 collection schema 一致。
4. 返回两类向量；异常记录 ERROR 并抛出。

### `def search_chunks_by_milvus(dense_vector, sparse_vector, filter_expr) -> list`

核心功能：访问当前生效 chunks collection 执行混合召回。

输入：两类向量、可选过滤表达式。

输出：Milvus 原始命中列表。

步骤：

1. 使用 `SEARCH_ANN_LIMIT` 创建稠密和稀疏请求。
2. 使用统一的 `milvus_gateway.chunks_collection`，该配置必须与 import 实际写入集合一致。
3. 采用 `0.6/0.4` 权重并开启分数归一化。
4. 最终取 `SEARCH_TOP_K`。
5. 读取新版 schema 的全部候选字段。
6. 将 Milvus 单查询外层结果拆成命中列表；无命中返回空列表。

### `def normalize_local_candidates(milvus_hits, retrieval_source) -> list[dict]`

核心功能：把 Milvus 原始结果映射为统一候选结构。

输入：原始命中、召回来源 `embedding` 或 `hyde`。

输出：本地候选列表。

步骤：

1. 提取新版 schema 字段和归一化分数。
2. `chunk_id/content/file_title` 缺失的记录视为非法并跳过，同时记录 WARNING。
3. 生成 `display_title`。
4. 补充 `source=milvus`、`retrieval_source` 和空 `url`。
5. 保持 Milvus 返回顺序。

### `def build_display_title(file_title, section_title) -> str`

核心功能：统一生成查询结果展示标题。

输入：文件标题、章节标题。

输出：`file_title / section_title` 或仅 `file_title`。

步骤：清洗两个标题；章节为空或等于文件标题时不重复展示，否则使用斜杠组合。

### `def search_chunks(state) -> dict`

核心功能：完成普通本地混合检索并返回节点状态增量。

输入：查询图 state。

输出：`{"embedding_chunks": list[dict]}`。

步骤：

1. 校验查询状态。
2. 构建向量检索文本和 Milvus 过滤表达式。
3. 生成稠密、稀疏向量。
4. 执行混合检索。
5. 规范化候选。
6. 记录 collection、是否过滤、命中数量和耗时。
7. 无命中返回空列表；Milvus/向量服务异常记录 ERROR 后返回空列表，以允许其他并行分支继续。

---

# 第三部分：`app\rag\query\search_embedding_hyde_service.py`

## 整体思路

HyDE 是增强召回而不是事实生成。大模型生成一段可能出现在相关文档中的专业表述，随后仅用该文本增强查询向量。HyDE 内容不得进入答案上下文。

HyDE 必须复用普通检索的过滤构造、Milvus 入口和候选规范化能力，避免两套 schema 逻辑漂移。

## 函数中文说明

### 复用 `validate_retrieval_state(state) -> tuple[str, dict]`

核心功能：校验 HyDE 所需查询数据。实际实现直接复用普通检索函数，不再定义重复的 `validate_hyde_state`。

输入：查询图 state。

输出：`rewritten_query`、规范化 `query_filters`。

步骤：与普通检索校验一致；不要求 `item_names`。

### `def build_query_scope_text(query_filters) -> str`

核心功能：把用户明确范围转换为 HyDE Prompt 的简短说明。

输入：查询范围。

输出：范围文本。

步骤：

1. 只选择明确文件、地域、文档类型和主要主题。
2. 去重并限制数量。
3. 无范围时返回“无额外范围限制”。

### `def generate_hyde_text(rewritten_query, scope_text) -> str`

核心功能：调用大模型生成仅用于召回的假设性文档表述。

输入：改写问题、范围文本。

输出：`hyde_text`。

步骤：

1. 加载 `hyde_prompt.prompt`。
2. 调用普通非 JSON 聊天模型。
3. 清洗结果并限制到 `HYDE_MAX_CHARS`。
4. 空结果或调用失败时记录 WARNING，返回空字符串。

### `def build_hyde_retrieval_query(rewritten_query, hyde_text, query_filters) -> str`

核心功能：构造 HyDE 分支的最终向量化文本。

输入：改写问题、HyDE 文本、查询范围。

输出：检索文本。

步骤：

1. 保留原始改写问题，避免 HyDE 偏题后完全替代用户意图。
2. 追加 HyDE 文本。
3. 追加与普通检索相同的软条件。
4. 控制总长度并去除重复片段。

### `def search_chunks_with_hyde(state) -> dict`

核心功能：完成 HyDE 生成、向量化和本地混合检索。

输入：查询图 state。

输出：`{"hyde_embedding_chunks": list[dict]}`。

步骤：

1. 校验状态并生成范围文本。
2. 调用大模型生成 HyDE 文本。
3. HyDE 为空时返回空列表，不回退为普通检索，避免与普通分支产生完全重复结果。
4. 构造增强检索文本和与普通分支相同的硬过滤表达式。
5. 复用向量化、Milvus 检索和本地候选规范化能力。
6. 设置 `retrieval_source=hyde`。
7. 记录耗时和命中数量，不记录完整 HyDE 内容。
8. 任一外部步骤失败时返回空列表，允许其他分支继续。

---

# 第四部分：`app\rag\query\web_search_service.py`

## 整体思路

继续使用 DashScope MCP WebSearch。网络搜索负责补充知识库外、时效性或来源链接信息，但不改变本地 metadata，也不作为 RRF 的本地排序分支。

V1 默认返回 5 条而不是 10 条：Web 摘要噪声通常高于本地 chunk，且最终 Reranker 上限为 6；减少 Web 候选可控制延迟并避免挤占本地证据。

## 函数中文说明

### `def validate_web_search_inputs(state) -> tuple[str, dict]`

核心功能：校验 Web 搜索输入。

输入：查询图 state。

输出：`rewritten_query`、查询范围。

步骤：校验问题非空；过滤结构为空时补默认值；不要求任何硬条件。

### `def build_web_search_query(rewritten_query, query_filters) -> str`

核心功能：生成适合搜索引擎的简短查询。

输入：改写问题、查询范围。

输出：Web 查询文本。

步骤：

1. 以改写问题为主体。
2. 只追加明确文件标题、地域和文档类型。
3. 不追加内部字段名、hard/soft 标记和大量关键词。
4. 限制长度，避免自然语言问题被改造成关键词堆砌。

### `async def call_web_search_mcp(query, count) -> object`

核心功能：异步连接 MCP 并调用 `bailian_web_search`。

输入：Web 查询文本、返回数量。

输出：MCP 原始响应。

步骤：

1. 校验 MCP URL 和 API Key 已配置，但日志中不得输出 Key。
2. 建立连接并使用明确的连接、读取超时。
3. 调用 WebSearch 工具。
4. 无论成功失败都清理连接。
5. 超时、连接和远端错误向上抛出，由同步入口统一降级。

### `def parse_web_search_response(mcp_result) -> list[dict]`

核心功能：安全解析 MCP 返回并规范化网页候选。

输入：MCP 原始响应。

输出：Web 候选列表。

步骤：

1. 校验 `content` 存在并找到文本块。
2. 解析 JSON，获取 `pages`。
3. 校验每项标题、摘要和 URL 类型。
4. 丢弃标题与摘要均为空的记录。
5. 生成统一 Web 候选结构。
6. 按规范化 URL 去重；无 URL 时按标题加摘要去重。
7. 保持搜索引擎原始顺序并限制数量。

### `def search_web_documents(state, count=WEB_SEARCH_TOP_K) -> dict`

核心功能：执行 Web 搜索并返回节点状态增量。

输入：查询图 state、可选返回数量。

输出：`{"web_search_docs": list[dict]}`。

步骤：

1. 校验输入并构建 Web 查询。
2. 调用异步 MCP 服务。
3. 解析和规范化结果。
4. 记录查询长度、结果数和耗时。
5. 外部异常记录 WARNING/ERROR 后返回空列表，不阻断本地检索链路。

---

# 第五部分：`app\rag\query\rrf_service.py`

## 整体思路

RRF 只融合普通检索和 HyDE 两路本地候选。它只依赖排名，不依赖两路分数是否在同一尺度。普通检索更忠于用户原问题，因此权重设为 `1.0`；HyDE 存在生成偏移风险，初始权重设为 `0.8`。

`RRF_K=60` 延续经典平滑取值，避免前几名权重差过大；`RRF_TOP_K=12` 为后续 Reranker 保留足够候选。

## 函数中文说明

### `def validate_rrf_inputs(state) -> tuple[list[dict], list[dict]]`

核心功能：读取并校验两路本地候选。

输入：查询图 state。

输出：普通候选列表、HyDE 候选列表。

步骤：

1. 缺失字段按空列表处理。
2. 非列表类型属于状态契约错误，记录 ERROR 并抛出。
3. 允许任一路或两路为空。

### `def reciprocal_rank_fusion(ranked_sources, k, limit) -> list[dict]`

核心功能：按 `chunk_id` 对多路有序候选去重并计算加权 RRF 分数。

输入：`[(weight, candidates)]`、平滑常量、输出上限。

输出：按 RRF 分数降序排列的本地候选。

步骤：

1. 遍历每个来源及其候选排名。
2. 缺少 `chunk_id` 的候选跳过并记录 WARNING。
3. 按 `weight / (k + rank)` 累加同一 chunk 分数。
4. 首次出现时复制完整候选，禁止原地修改并行分支的列表。
5. 记录命中的 retrieval sources，便于解释同一 chunk 是否被两路同时召回。
6. 用 RRF 分数替换当前阶段 `score`，原始分数可放入内部 `retrieval_scores`。
7. 按 RRF 分数降序排列，稳定并列顺序并截取 `limit`。

### `def fuse_retrieval_results(state) -> dict`

核心功能：组织两路本地候选融合并返回节点状态增量。

输入：查询图 state。

输出：`{"rrf_chunks": list[dict]}`。

步骤：

1. 校验输入。
2. 组装普通 `1.0`、HyDE `0.8` 两路来源。
3. 调用 RRF 融合。
4. 两路均为空时返回空列表并记录 WARNING。
5. 记录两路输入数、去重后数量和最终数量。

---

# 第六部分：`app\rag\query\rerank_service.py`

## 整体思路

Reranker 统一处理 RRF 本地候选与 Web 候选。只有用于打分的文本可以压缩，原始 `content` 和 metadata 必须原样保留。输入允许“仅本地、仅 Web、两者都有、两者都空”四种状态。

V1 延续最大输入 512 tokens、最终 2～6 条和断崖动态截断。全空时不抛出业务异常，返回空列表交给答案节点固定兜底。

## 函数中文说明

### `def validate_rerank_inputs(state) -> tuple[str, list[dict], list[dict]]`

核心功能：校验改写问题和候选列表类型。

输入：查询图 state。

输出：改写问题、本地候选、Web 候选。

步骤：

1. `rewritten_query` 必须非空。
2. 两类候选缺失时补空列表。
3. 非列表类型抛出状态契约错误。
4. 不要求两类候选同时非空。

### `def merge_rerank_candidates(rrf_chunks, web_search_docs) -> list[dict]`

核心功能：将本地与 Web 候选转换为统一精排结构。

输入：RRF 本地候选、Web 候选。

输出：统一候选列表。

步骤：

1. 保留本地候选的全部 metadata 和原始 content。
2. 保留 Web 标题、摘要、URL 和来源。
3. 本地按 `chunk_id`、Web 按 URL 去重。
4. 生成唯一候选标识，避免 `chunk_id=None` 的 Web 结果互相覆盖。
5. 初始化 `rerank_score`，不覆盖 RRF 原始分数。

### `def build_rerank_text(candidate) -> str`

核心功能：构造供 Reranker 判断相关性的候选文本。

输入：统一候选。

输出：包含标题和必要 metadata 的评分文本。

步骤：

1. 首先加入 `display_title`。
2. 本地候选追加文档类型、地域、主题和关键词的简短标签。
3. 追加原始 content。
4. Web 候选只使用网页标题和摘要。
5. 不把分数、URL 和内部 ID 作为语义正文。

### `def fit_rerank_text(question, candidate, tokenizer) -> str`

核心功能：把评分文本控制在 Reranker token 上限内。

输入：问题、候选、Reranker tokenizer。

输出：只用于评分的文本。

步骤：

1. 计算问题和候选总 token 数。
2. 未超限时原样返回评分文本。
3. 普通文本超限时调用 `rerank_text_refine.prompt` 精简。
4. 表格和代码超限时不让 LLM 改写事实结构，采用确定性 token 截取，并优先保留标题、表头或代码开头。
5. 再次计算 token，仍超限则执行最终确定性截取。
6. 任何处理都不得覆盖候选的原始 `content`。
7. 精简模型失败时记录 WARNING，并回退为确定性 token 截取。

### `def create_rerank_pairs(rewritten_query, candidates) -> list[list[str]]`

核心功能：生成 BGE Reranker 的问题—候选文本对。

输入：改写问题、统一候选列表。

输出：与候选顺序严格一致的二维字符串列表。

步骤：逐条构建并控制评分文本；空候选返回空列表。

### `def score_and_sort_candidates(pairs, candidates) -> list[dict]`

核心功能：批量计算归一化相关性分数并排序。

输入：评分对、候选列表。

输出：包含 `rerank_score` 的降序候选。

步骤：

1. 校验 pairs 与 candidates 数量一致。
2. 使用现有 BGE Reranker 批量计算归一化分数。
3. 校验返回分数数量和数值合法性。
4. 写入 `rerank_score`，同时将当前统一 `score` 更新为精排分数。
5. 稳定降序排列。

### `def select_dynamic_top_k(candidates) -> list[dict]`

核心功能：在最小、最大范围内根据相关性断崖选择最终候选数。

输入：已按精排分数降序排列的候选。

输出：最终 Top-K。

步骤：

1. 空列表返回空列表；不足最小数量时全部返回。
2. 在第 `RERANK_MIN_TOP_K` 条之后寻找相邻分数断崖。
3. 同时判断绝对差和相对差。
4. 前一分数小于等于 0 时不计算除法比例，避免除零。
5. 找到首个断崖即截断；没有断崖则取最大数量。
6. 对未限定具体文件的查询，可按 `document_id` 做结果多样性控制；V1 每篇最多 2 条。严格指定单一文件时关闭该限制。

### `def rerank_documents(state) -> dict`

核心功能：完成候选合并、评分、排序和动态截断。

输入：查询图 state。

输出：`{"reranked_docs": list[dict]}`。

步骤：

1. 校验输入并合并候选。
2. 无候选时返回空列表。
3. 构造评分对。
4. 调用 Reranker 评分和排序。
5. 执行动态 Top-K 和文档多样性控制。
6. Reranker 模型失败时记录 ERROR，按 RRF 本地结果在前、Web 结果在后的上游顺序截取最多 6 条，使答案链路可以降级继续。
7. 记录本地/Web 输入数、最终数量和来源分布，不记录全文。

---

# 第七部分：`app\rag\query\answer_output_service.py`

## 整体思路

该 service 是统一出口，处理三类情况：入口节点已经生成澄清回答、所有检索无结果、存在有效证据需要调用大模型回答。事实只能来自 `reranked_docs`；历史仅用于语言上下文，HyDE 文本永不进入回答。

答案不再使用 `[来源1]` 这种需要用户二次查找的编号。本地候选（包括普通检索和 HyDE）统一引用为 `[本地知识库/file_title/section_title]`；Web 候选统一引用为 `[网络搜索/url]`。排序分数不再称为“置信度”，也不需要暴露给模型。

## 函数中文说明

### `def handle_prebuilt_answer(state) -> tuple[bool, str]`

核心功能：识别并处理入口节点生成的澄清或固定回答。

输入：查询图 state。

输出：是否已经有答案、答案文本。

步骤：

1. 读取非空 `answer`。
2. 流式模式下将完整固定回答推送一次。
3. 返回已处理标记，阻止再次调用大模型。

### `def validate_answer_inputs(state) -> tuple[str, list[dict]]`

核心功能：校验答案生成输入。

输入：查询图 state。

输出：改写问题、精排证据列表。

步骤：校验问题非空；`reranked_docs` 缺失时按空列表处理；非列表抛出契约错误。

### `def build_evidence_context(reranked_docs) -> str`

核心功能：将最终候选组织成带可读来源标签的证据文本。

输入：精排候选列表。

输出：`context`。

步骤：

1. Milvus 本地证据不区分普通检索或 HyDE，统一生成 `[本地知识库/file_title/section_title]`。
2. Web 证据统一生成 `[网络搜索/url]`。
3. 本地证据输出展示标题、文档类型、地域、内容类型和原文。
4. Web 证据输出网页标题、URL 和摘要。
5. 不输出内部 ID、向量分数、“置信度”或数字来源编号。
6. 总长度超过 `ANSWER_MAX_CONTEXT_CHARS` 时按排名截取，不能截断 Markdown 表格的单行结构。

### `def build_source_label(document) -> str`

核心功能：根据候选来源生成唯一的用户可读来源标签。

输入：本地或 Web 精排候选。

输出：本地标签或 Web 标签。

步骤：Web 使用 URL；Milvus 使用 `file_title/section_title`，章节为空时回退到文件标题。HyDE 只属于检索方式，不改变其本地知识库来源类型。

### `def replace_legacy_source_labels(answer, reranked_docs) -> str`

核心功能：兜底替换模型偶尔生成的旧 `[来源N]` 标记。

输入：模型答案、与证据顺序一致的精排候选。

输出：已将合法数字编号替换为可读来源标签的答案。

步骤：解析 N 的一基索引，查找对应候选并调用 `build_source_label`；索引越界时保留原文本，避免错误绑定来源。

### `def build_answer_history_context(state) -> str`

核心功能：生成仅用于对话衔接的历史文本。

输入：查询图 state。

输出：历史上下文。

步骤：

1. 优先复用查询理解节点已加载的 `history`。
2. 必要时从仓储补查近期消息。
3. 不再按 `item_names` 过滤。
4. 只保留问题和短回答，总长度受限。
5. 明确标注历史不能作为事实来源。

### `def load_answer_prompt(state, evidence_context, history_text) -> str`

核心功能：渲染答案 Prompt。

输入：state、证据上下文、历史上下文。

输出：最终 Prompt 文本。

步骤：

1. 获取改写问题和查询范围摘要。
2. 加载 `answer_out.prompt`。
3. 渲染 `question/query_scope/context/history`。
4. 不再传入 `item_names`。

### `def generate_answer_by_llm(state, prompt_text) -> str`

核心功能：按流式或非流式模式调用大模型生成答案。

输入：state、渲染后的 Prompt。

输出：完整答案字符串。

步骤：

1. 获取聊天模型。
2. 流式模式逐块推送非空文本并累计完整答案。
3. 非流式模式单次调用并提取文本。
4. 空答案视为模型调用异常。
5. 返回完整答案，不在函数内保存历史。

### `def extract_image_urls(reranked_docs) -> list[str]`

核心功能：从最终证据提取可展示图片 URL。

输入：精排候选列表。

输出：去重后的图片 URL 列表。

步骤：

1. 从 content 中提取 Markdown 图片链接。
2. 对 Web URL 去除 query/fragment 后按扩展名判断图片类型。
3. 只接受允许的 HTTP(S) 或项目认可的本地地址。
4. 按首次出现顺序去重。

### `def save_answer_history(state, answer, image_urls) -> None`

核心功能：保存助手回答。

输入：state、答案、图片列表。

输出：无。

步骤：保存 `session_id/role/text/rewritten_query/query_filters/image_urls`；旧 `item_names` 可暂存空列表用于兼容。

### `def produce_answer(state) -> dict`

核心功能：统一编排澄清、无结果和证据回答三类输出。

输入：查询图 state。

输出：至少包含 `answer`、`image_urls` 的状态增量。

步骤：

1. 如果已有澄清回答，直接处理并保存历史。
2. 校验答案输入。
3. `reranked_docs` 为空时生成固定文本“未检索到足以回答该问题的参考内容”，不调用大模型。
4. 有证据时构造证据和历史上下文。
5. 渲染 Prompt 并调用大模型。
6. 提取图片 URL。
7. 保存助手历史。
8. 记录答案长度、证据数量和来源分布。

---

# 第八部分：Prompt 设计

## 1. `query_understanding.prompt`

用于替换 `rewritten_query_and_itemnames.prompt`。由于 `load_prompt` 使用 `str.format`，JSON 示例中的字面量花括号应使用双花括号。

```text
# 角色
你是再生水知识库的查询理解助手。你的任务是理解问题和提取检索范围，不负责回答问题。

# 规则
1. 当前用户问题是主要依据，历史对话仅用于消解“这个、该文件、上述政策”等指代。
2. 将当前问题改写为可独立理解的中文检索问题，不改变用户意图，不补充用户未表达的事实。
3. 即使用户没有指定文件名称、地域或文档类型，也必须正常生成 rewritten_query。
4. file_titles 只提取明确出现或能由清晰历史指代确定的完整文件标题。
5. region_names 只提取主体适用或研究地域，不提取偶然出现的地名。
6. document_types 只能是：政策、标准、规划、技术文件、其他。
7. topics 为上位主题，keywords 为具体检索词；二者都不能放入 hard_fields。
8. hard_fields 只允许 file_titles、region_names、document_types，并且只有用户明确限定时才能加入。
9. strict 只有在用户表达“只、仅、限定、不要其他”等排他要求时才为 true。
10. 只有问题为空、关键指代无法消解或严格条件互相冲突时，needs_clarification 才为 true。
11. 不要输出解释，只返回 JSON。

# 输出格式
{{
  "rewritten_query": "独立完整的问题",
  "file_titles": [],
  "region_names": [],
  "document_types": [],
  "topics": [],
  "keywords": [],
  "hard_fields": [],
  "strict": false,
  "needs_clarification": false,
  "clarification_question": ""
}}

# 当前用户问题
{query}

# 历史对话
{history_text}
```

## 2. `hyde_prompt.prompt`

```text
# 角色
你是再生水领域的检索表达生成助手。下面内容只用于向量检索，不是最终答案。

# 任务
根据用户问题，生成一段可能出现在相关政策、标准、规划或技术文件中的专业表述。

# 要求
1. 保持与问题和明确查询范围一致。
2. 覆盖可能出现的专业术语、同义表达和关键概念。
3. 不虚构文件名称、编号、日期、机构、数据或引用。
4. 不出现“假设性回答”“根据资料”等说明。
5. 使用中文，不超过 {max_chars} 字，只输出正文。

用户问题：{rewritten_query}
查询范围：{query_scope}
```

## 3. `rerank_text_refine.prompt`

该 Prompt 只用于超长普通文本的评分副本，不处理 table/code，不替换原文。

```text
你是检索重排文本精简助手。请围绕问题压缩候选文本，输出仅用于相关性打分的文本。

问题：{question}
候选文本：{answer}

要求：
1. 保留与问题直接相关的事实、条件、数值、术语和否定关系。
2. 不新增、不推测、不改写事实含义。
3. 删除重复、背景性和与问题无关内容。
4. 不输出说明、标题或评价。
5. 不超过 {limit} 字。
```

## 4. `answer_out.prompt`

```text
# 角色
你是严格基于检索证据回答问题的再生水专业助手。

# 核心规则
1. 所有事实只能来自【参考证据】，不得使用自身知识补充。
2. 【历史对话】只用于理解指代和表达习惯，不能作为事实依据。
3. 直接回答用户问题，不扩展无关内容。
4. 每个关键事实或结论后原样使用证据中的来源标识。
5. 本地来源固定为 [本地知识库/file_title/section_title]。
6. 网络来源固定为 [网络搜索/url]。
7. 不得使用 [来源1]、[来源2] 等数字编号，也不得编造来源内容。
8. 本地表格、代码和原文中的数值、条件、例外不得改变。
9. 本地知识库与网络搜索冲突时，明确说明来源差异，不自行判断哪一方必然正确。
10. 证据不足时明确回答“参考内容中未提及该问题的相关信息”。
11. 不把检索相关性分数描述为事实置信度。

# 用户问题
{question}

# 查询范围
{query_scope}

# 参考证据
{context}

# 历史对话，仅用于上下文理解
{history}

# 输出要求
使用中文，结构清晰，优先给出直接答案；保留必要来源标注，不输出分析过程。
```

---

# 第九部分：核心常量与选择理由

| 常量 | V1 建议值 | 选择理由 |
| --- | ---: | --- |
| `QUERY_HISTORY_MESSAGE_LIMIT` | 6 | 足够支持近距离指代，减少旧主题污染 |
| `QUERY_HISTORY_MAX_CHARS` | 4000 | 控制查询理解 Prompt 成本，优先保留最近上下文 |
| `ORIGINAL_QUERY_MAX_CHARS` | 2000 | 防止异常超长输入，同时容纳复杂业务问题 |
| `REWRITTEN_QUERY_MAX_CHARS` | 200 | 比旧 100 字更能保留地域、文种和复合问题 |
| `QUERY_FILTER_MAX_VALUES` | 10 | 防止模型输出异常大列表和过滤表达式膨胀 |
| `RETRIEVAL_QUERY_MAX_CHARS` | 500 | 保留问题与软条件，避免关键词堆积稀释语义 |
| `SEARCH_ANN_LIMIT` | 20 | 给稠密、稀疏两路融合提供较宽候选池 |
| `SEARCH_TOP_K` | 10 | 每个本地分支保留足够结果供 RRF 去重 |
| `DENSE_WEIGHT` | 0.6 | 自然语言语义为主 |
| `SPARSE_WEIGHT` | 0.4 | 保留文件名、术语、数字和专有词精确命中 |
| `HYDE_MAX_CHARS` | 300 | 足够覆盖专业表述，又降低生成偏移和向量噪声 |
| `WEB_SEARCH_TOP_K` | 5 | 控制网络噪声、延迟及其对本地证据的挤占 |
| `WEB_CONNECT_TIMEOUT_SECONDS` | 30 | 连接超时后及时退化到本地检索 |
| `WEB_READ_TIMEOUT_SECONDS` | 60 | 兼顾 MCP 搜索耗时与整体问答响应时间 |
| `RRF_K` | 60 | 平滑不同排名位置差异，沿用成熟常用取值 |
| `RRF_EMBEDDING_WEIGHT` | 1.0 | 普通检索最忠于原问题 |
| `RRF_HYDE_WEIGHT` | 0.8 | 保留 HyDE 增益，同时降低生成偏移影响 |
| `RRF_TOP_K` | 12 | 给本地与 Web 统一精排提供足够候选 |
| `RERANK_MAX_INPUT_TOKENS` | 512 | 与当前 Reranker 能力和性能折中保持一致 |
| `RERANK_MIN_TOP_K` | 2 | 避免单一证据偶然命中 |
| `RERANK_MAX_TOP_K` | 6 | 控制最终上下文长度和生成噪声 |
| `RERANK_GAP_ABS` | 0.2 | 识别明显绝对分差，先沿用现值 |
| `RERANK_GAP_RATIO` | 0.2 | 兼顾不同整体分数区间，先沿用现值 |
| `RERANK_MAX_PER_DOCUMENT` | 2 | 非指定文档问题中提高来源多样性 |
| `ANSWER_MAX_CONTEXT_CHARS` | 20000 | 覆盖最多 6 条 chunk/Web 证据并限制 Prompt 体积 |

上述值均为 V1 初始值。其中召回数量、稠密/稀疏权重、HyDE 权重、断崖阈值和单文档上限必须通过离线问题集评测后调整，不能把经验值当成长期固定结论。

---

# 第十部分：关键决策与实施顺序

## 1. collection 决策

import 和 query 必须共享一个有效 `CHUNKS_COLLECTION` 配置或 Milvus alias。query 不自行推测 `_v2/_v3`，否则可能查到旧 schema。当前项目配置已统一为 `kb_chunks_v2`；如部署环境使用其他名称，必须在同一环境变量中同步修改，不能只修改一侧。

## 2. 地域过滤决策

- “仅北京地方政策”：硬过滤北京市，不包含全国。
- “在北京适用的政策”：硬过滤北京市或全国。
- 技术问题只提到北京但未限定文种：地域作为软条件，不进行硬过滤。
- “不限”默认不加入地域硬过滤，由语义检索和 Reranker 判断。

## 3. 文件标题决策

V1 不建设新的标题集合。完整标题和严格限定同时出现时才做 `file_title` 硬过滤，其余均作为向量检索软条件。这样避免重新引入 import 双写和标题目录同步问题。

## 4. 推荐实施顺序

1. 先统一 state、节点返回层级、service 公共入口和 `__init__` 导出。
2. 同步确认 import/query 的实际 chunks collection。
3. 改造查询理解和四个 Prompt。
4. 改造普通检索与 HyDE 的新版字段、过滤和统一候选结构。
5. 改造 RRF、Web 规范化与 Reranker。
6. 最后改造答案引用、历史字段和无结果兜底。
7. 使用 `query.md` 中的验收场景做链路测试，再基于评测集调整常量。

该顺序先消除接口和 schema 断点，再调整检索效果，可以避免多个问题叠加后难以定位。
