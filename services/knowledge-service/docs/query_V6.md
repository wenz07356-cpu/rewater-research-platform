# Query V6：交互式检索模式实现提示词

> 用途：将本文从“给 Codex 的任务”开始完整交给 Codex，用于后续编码。
> 本文是基于当前仓库实际代码和 `docs/query_V5.md` 整理的实现提示词，不是本轮代码改动。

## 给 Codex 的任务

你正在维护 `rewater-agent`。请直接修改代码，完成 Query 链路的请求级检索模式、查询范围交互、结果反馈和离线评估支持。实现依据是 `docs/query_V5.md`，但必须先重新检查当前代码，不能只按文档猜测。

### 一、目标

在保持现有默认查询效果和旧调用方兼容的前提下，提供四种请求级检索模式：

- `balanced`：均衡，必须与当前生产参数和 Web 行为一致；
- `precision`：精确回答，减少弱相关材料；
- `recall`：全面检索，扩大召回和最终上下文；
- `custom`：只开放受控、可理解的业务参数。

用户应能在 `app/process/query/page/chat.html` 中选择模式和资料范围，看到实际应用模式、候选数量、最终上下文数量及降级情况，并能用精确模式或全面模式重试上一问题。

### 二、开始编码前必须阅读的文件

至少完整阅读并理解以下文件，再决定具体改动位置：

- `docs/query_V5.md`
- `docs/PYTHON_CODE_STYLE_GUIDE.md`
- `app/rag/query/config.py`
- `app/api/schemas/query.py`
- `app/api/http/query_server.py`
- `app/process/query/agent/state.py`
- `app/process/query/agent/main_graph.py`
- `app/process/query/agent/nodes/*.py`
- `app/rag/query/search_embedding_service.py`
- `app/rag/query/search_embedding_hyde_service.py`
- `app/rag/query/web_search_service.py`
- `app/rag/query/rrf_service.py`
- `app/rag/query/rerank_service.py`
- `app/rag/query/answer_output_service.py`
- `app/infra/persistence/history_repository.py`
- `app/shared/clients/mongo_history_utils.py`
- `app/shared/utils/sse_utils.py`
- `app/shared/utils/task_utils.py`
- `app/process/query/page/chat.html`
- `app/rag_eval/ragas/collector.py`
- `app/rag_eval/ragas/runner.py`
- `app/rag_eval/ragas/__main__.py`
- `tests/test_query_services.py`
- `tests/test_ragas_eval.py`

编码前先用几句话总结你确认的调用链和计划；随后连续完成实现、测试和必要修正，不要只给方案。

### 三、当前代码事实

实现必须建立在下列现状上：

1. 当前流程是：查询理解后，普通混合检索、HyDE、Web 三个节点并行，汇入 RRF，再进入 Rerank 和答案节点。
2. `QueryRequest` 目前只有 `query`、`session_id`、`is_stream`；流式和非流式最终都调用 `invoke_query()` 创建 state。
3. `QueryGraphState` 目前没有请求级检索配置，检索、RRF、Rerank、Answer 均直接读取 `app/rag/query/config.py` 的模块常量。
4. `node_web_search_mcp` 只有评估开关 `eval_disable_web`；生产图固定调用 Web。HyDE 也固定调用。
5. RRF 只融合两路本地结果；Web 候选在 Rerank 阶段与本地候选统一打分，这是正确行为，应保留。
6. Rerank 的动态截断、同文档上限和异常回退都读取全局常量。
7. Answer 的上下文字符预算固定为 `ANSWER_MAX_CONTEXT_CHARS`。
8. Web、HyDE、Reranker 当前失败时会降级，但响应无法区分“主动关闭”“无结果”和“执行失败”。
9. 历史记录目前只保存问题、改写问题、查询过滤、答案和图片；没有模式、有效配置或检索摘要。
10. 前端目前只提交三个旧字段，也没有模式、范围或检索反馈组件。
11. 评估器目前保存部分全局配置快照，但不能按请求运行四种模式。
12. 当前 `chat.html` 存在轮询 `/status/{taskId}` 的旧代码，而 `query_server.py` 没有该路由；本任务不要扩大范围重写任务系统，除非改动是完成新交互所必需。

### 四、不可违反的工程边界

1. 严禁在请求处理中修改或 monkey-patch `app/rag/query/config.py` 的模块常量。不同并发请求不得串值。
2. 有效配置必须在请求入口解析一次，形成不可变的请求级对象，并经 `QueryGraphState` 传给所有节点。
3. 服务端是最终校验边界。不能相信前端范围、数量、权重、`hard_fields` 或隐藏字段。
4. 旧请求体不带任何新字段时，生产行为必须等价于当前 `balanced`：包括现有数值、HyDE 开启和 Web 开启。
5. `eval_disable_web` 是评估环境的强制覆盖：即使模式启用 Web，也不得真的调用 Web。
6. 禁用 HyDE 或 Web 时不能发起对应的 LLM、Embedding 或网络调用；应快速返回空分支结果和“主动关闭”状态。
7. 主动关闭不算降级；只有实际执行失败才进入 `degradations`。
8. 保持 Web 候选与本地候选统一进入 Rerank，不得把未经 Rerank 的 Web 内容直接交给答案模型。
9. SSE 与非流式入口必须复用同一个请求解析器和同一个元数据汇总器。
10. 不向普通用户返回 RRF 原始分数、完整底层参数、内部 Prompt、密钥或异常堆栈。
11. 不删除现有兼容别名和现有字段；旧 MongoDB 文档缺少新字段时必须可读取。
12. 不引入新的前端框架；在现有单文件页面中实现交互，并保持移动端可用。

### 五、请求和响应契约

#### 5.1 请求模型

在 `app/api/schemas/query.py` 中使用 Pydantic 明确定义枚举和嵌套模型，不要继续用无约束 `dict[str, Any]` 承载新接口。

建议的 JSON 请求如下：

```json
{
  "query": "北京市再生水利用有哪些管理要求？",
  "session_id": "sess-xxx",
  "is_stream": true,
  "retrieval_mode": "precision",
  "retrieval_options": null,
  "query_scope": {
    "document_ids": [],
    "region_names": ["北京市"],
    "document_types": ["政策"],
    "topics": [],
    "keywords": ["利用管理"],
    "strict": false
  },
  "remember_for_session": false
}
```

字段规则：

- `retrieval_mode` 应允许省略。省略时先读取本会话记住的偏好，没有偏好才使用 `balanced`。不要把 Pydantic 默认值直接写成 `balanced`，否则无法区分“省略”和“显式选择 balanced”。
- `retrieval_options` 只允许在 `custom` 下出现；`custom` 必须提供该对象。其他模式携带该对象时返回 422。
- `query_scope` 始终是本次请求属性，不随 `remember_for_session` 保存，避免旧范围静默限制后续问题。
- `remember_for_session` 只记住模式和已校验的自定义业务选项，默认 `false`。显式但不记忆的一次请求不能清除此前已记住的偏好。
- 所有列表需要去空白、稳定去重并限制最多 10 项；字符串设置合理长度上限。
- `document_types` 只接受当前 `DOCUMENT_TYPES`。
- 客户端不得提交 `hard_fields`。

`custom` 只暴露以下字段：

```json
{
  "candidate_top_k": 10,
  "max_reference_count": 6,
  "matching_preference": "balanced",
  "hyde_enabled": true,
  "hyde_influence": "medium",
  "web_enabled": true
}
```

校验范围：

- `candidate_top_k`: 5～25；
- `max_reference_count`: 1～12；
- `matching_preference`: `keyword | balanced | semantic`；
- `hyde_enabled`: 布尔值；
- `hyde_influence`: `low | medium | high`，HyDE 关闭时该值不生效；
- `web_enabled`: 布尔值。

不要开放 `RRF_K`、token 上限、超时、HyDE 字符上限、摘要比例、任意 Dense/Sparse 浮点数等工程参数。

#### 5.2 响应模型

为普通响应、SSE `final` 事件和助手历史记录增加同构的 `retrieval_metadata`：

```json
{
  "mode": "precision",
  "mode_label": "精确回答",
  "scope": {
    "documents": [{"document_id": "...", "file_title": "..."}],
    "region_names": ["北京市"],
    "document_types": ["政策"],
    "topics": [],
    "keywords": ["利用管理"],
    "strict": false
  },
  "summary": {
    "search_breadth": "较窄",
    "reference_range": "1～3",
    "matching_preference": "均衡",
    "hyde_enabled": true,
    "web_enabled": false
  },
  "counts": {
    "embedding": 6,
    "hyde": 6,
    "local_fused": 8,
    "web": 0,
    "final_context": 3
  },
  "degradations": []
}
```

要求：

- 上述对象只暴露可理解的摘要，不返回完整内部配置。
- `degradations` 使用稳定代码或安全中文文案，如 `hyde_failed`、`web_failed`、`reranker_failed`，不得返回异常文本。
- 流式请求的初始 `QueryResponse` 可以只返回已解析的模式摘要；最终 `final` 事件必须携带完整 `retrieval_metadata`。
- 非流式响应与同一 state 生成的 SSE 最终元数据应完全一致。
- 澄清回答也要返回模式和零计数元数据。

### 六、请求级有效配置

新增职责单一的模块，例如 `app/rag/query/retrieval_config.py`。建议使用 `@dataclass(frozen=True, slots=True)` 或等价不可变结构定义 `EffectiveRetrievalConfig`，字段至少包含：

- `mode`
- `ann_limit`
- `search_top_k`
- `dense_weight`、`sparse_weight`
- `hyde_enabled`
- `web_enabled`、`web_top_k`
- `rrf_k`、`rrf_embedding_weight`、`rrf_hyde_weight`、`rrf_top_k`
- `rerank_min_topk`、`rerank_max_topk`
- `rerank_gap_ratio`、`rerank_gap_abs`
- `rerank_max_per_document`
- `answer_max_context_chars`

保留 `config.py` 现有常量作为生产基线和工程硬上限来源，但节点运行参数必须来自 state 中的有效配置；只有兼容旧的直接 service 调用且 state 缺配置时，才构造 `balanced` 回退配置。

四个预设必须集中定义并由纯函数解析，不能把数值散落在 API、节点和页面：

| 参数 | `balanced` | `precision` | `recall` |
|---|---:|---:|---:|
| ANN 单路候选数 | 20 | 12 | 40 |
| 普通/HyDE 各路 Top-K | 10 | 6 | 20 |
| Dense/Sparse | 0.6/0.4 | 0.6/0.4 | 0.6/0.4 |
| HyDE | 开 | 开 | 开 |
| 普通/HyDE RRF 权重 | 1.0/0.8 | 1.0/0.4 | 1.0/1.0 |
| RRF K | 60 | 40 | 60 |
| RRF 输出数 | 12 | 8 | 24 |
| Rerank 最少/最多保留 | 2/6 | 1/3 | 6/12 |
| Rerank 相对/绝对断崖阈值 | 0.2/0.2 | 0.10/0.10 | 0.35/0.35 |
| 单文档最多上下文 | 2 | 2 | 3 |
| Web | 开 | 关 | 开 |
| Web Top-K | 5 | 3 | 8 |
| Answer 字符预算 | 20,000 | 12,000 | 30,000 |

`custom` 使用确定性映射，写成可单测的纯函数：

- `ann_limit = clamp(2 * candidate_top_k, 10, 50)`；
- `search_top_k = candidate_top_k`；
- `matching_preference` 映射为：`keyword => 0.35/0.65`、`balanced => 0.6/0.4`、`semantic => 0.8/0.2`；
- `hyde_influence` 映射 HyDE RRF 权重：`low => 0.4`、`medium => 0.8`、`high => 1.0`；关闭 HyDE 时分支不执行；
- 普通检索 RRF 权重固定 `1.0`，`rrf_k` 固定 `60`；
- `rrf_top_k = clamp(max(max_reference_count, ceil(1.2 * candidate_top_k)), 5, 30)`；
- `rerank_min_topk = min(2, max_reference_count)`；
- `rerank_max_topk = max_reference_count`；
- 两个断崖阈值固定 `0.2`，单文档上限固定 `2`；
- Web Top-K 固定 `5`；
- `answer_max_context_chars = clamp(max_reference_count * 2500, 5000, 30000)`。

解析后再次校验内部不变量：权重在 0～1 且和为 1、`search_top_k <= ann_limit`、Rerank 最小值不大于最大值、RRF 输出不小于 Rerank 最大值、所有值不超过服务端硬上限。

### 七、资料范围与查询理解的合并

不要直接把用户输入的文件标题作为权威硬过滤条件。Milvus chunk 已有稳定 `document_id`，应使用它完成文件选择：

1. 提供只读查询选项接口，例如 `GET /query/options`，返回有上限、稳定排序的文档 `{document_id, file_title}` 列表、地域列表和 `DOCUMENT_TYPES`。把 Milvus 读取封装进 gateway/service，不在 HTTP 路由中直接操作客户端。
2. 接口读取失败时记录日志并返回可用的空选项结构，不泄漏连接信息。
3. 前端文件选择器只提交服务端返回的 `document_ids`，不允许手输所谓精确文件 ID。
4. 服务端验证 ID 格式并解析为真实文档；未知 ID 返回 422，而不是静默变成空结果。
5. 将 `document_ids` 加入内部过滤结构和允许的硬过滤字段；Milvus 表达式使用 `document_id in [...]`。已解析标题可同时加入软检索文本和展示摘要。

显式 `query_scope` 与 LLM 查询理解结果按以下规则合并：

- 用户显式非空字段优先，LLM 只补充用户未指定的字段；不要让 LLM 覆盖用户选择。
- `topics`、`keywords` 始终只增强检索文本，不进入 Milvus 硬过滤。
- `strict=true` 时，用户显式选择且支持硬过滤的 `document_ids`、`region_names`、`document_types` 由后台生成 `hard_fields`。
- `strict=false` 时这些字段作为软条件；地域仍保留现有“非严格时兼容全国资料”的语义。
- LLM 识别到“仅在某文件/地区/类型内”等排他表达时，可保留当前严格推断能力，但 `hard_fields` 必须由规范化代码生成，不能原样相信模型输出。
- 对同名文件不要退回标题硬过滤；使用 `document_id` 消除歧义。
- 无结果时在元数据中保留实际范围，前端提供“放宽范围重试”：去掉 `strict` 和硬范围后重新提交，不能在后台偷偷放宽。

### 八、按文件落实改动

#### 8.1 API 和入口

- 在 `app/api/schemas/query.py` 增加枚举、Custom 选项、QueryScope、公开元数据等模型，并扩展 `QueryRequest`、`QueryResponse`、`HistoryItem`。
- 在 `app/api/http/query_server.py` 把完整的已校验请求传入 `invoke_query()`、`execute_query()`、`start_stream_query()` 和后台任务，不能在流式路径丢失字段。
- 在进入后台线程前解析有效配置和会话偏好，确保 SSE 与非流式使用同一结果。
- 在非流式响应和 SSE `final` 中调用同一元数据汇总函数。
- 为查询选项增加只读接口及响应模型。

#### 8.2 State 和图节点

- 为 `QueryGraphState` 和默认 state 增加：请求 scope、不可变有效配置、各分支执行状态，以及形成公开反馈所需的字段。
- 不要让三个并行节点同时覆盖同一个普通字典字段。可让各分支返回各自独立状态字段，最后统一汇总；若使用 LangGraph reducer，必须补并行合并测试。
- 为兼容直接调用 service 的旧测试，提供统一 `get_effective_retrieval_config(state)`，缺失时返回新的 balanced 对象。
- 可以保留现有三分支图拓扑：禁用的 HyDE/Web 节点快速返回空列表和 `disabled` 状态。这样可避免贸然破坏 LangGraph 的并行汇合语义。
- 不得因为关闭 Web 或 HyDE 导致 RRF 多次执行、提前执行或一直等待。

#### 8.3 各检索阶段

- `search_embedding_service.py`：把 ANN limit、Top-K、Dense/Sparse 权重显式传入检索函数，值来自请求配置。
- `search_embedding_hyde_service.py`：先检查 `hyde_enabled`；关闭时不得调用 HyDE LLM 或 Embedding；开启时复用请求级检索参数。
- `web_search_service.py`/Web 节点：先同时检查模式开关和 `eval_disable_web`，调用数量使用请求级 `web_top_k`。
- `rrf_service.py`：RRF K、两路权重和输出数量均来自请求配置。
- `rerank_service.py`：动态最少/最多条数、两个断崖阈值、单文档上限和异常回退数量均来自请求配置。不要只改正常路径而遗漏异常回退。
- `answer_output_service.py`：`build_evidence_context` 使用请求级字符预算，保留当前来源标签、历史上下文和图片提取行为。
- 每个外部阶段使用明确状态区分 `success`、`disabled`、`failed`；普通检索失败也应记录，但不在用户响应中泄漏异常。

#### 8.4 历史和会话记忆

- 扩展 Mongo 写入、Repository 和 History schema，保存安全的 `retrieval_preference` 或等价字段、公开 `retrieval_metadata`，并兼容旧文档缺字段。
- 用户消息保存本次模式、经过校验的自定义业务选项和 scope；助手消息保存最终检索元数据。
- 会话偏好只从 `remember_for_session=true` 的已校验用户记录恢复；新会话或找不到偏好时回到 balanced。
- 保存完整内部配置快照用于审计时，应是普通可序列化数据的副本，不能保存可变共享对象，也不能保存密钥或 Prompt。
- 历史读取失败不得阻断查询，应记录日志并回到 balanced。

#### 8.5 前端

在 `chat.html` 中完成以下交互：

- 输入框附近增加四模式选择器，默认显示“均衡”；
- 每个模式显示简短说明和代价提示；
- custom 才展开：候选范围、最多参考材料、匹配偏好、HyDE、HyDE 影响、联网搜索；
- 增加资料范围面板：文件多选、地域、文档类型、主题、关键词及“仅搜索所选范围”；
- 文件选择器的数据来自 `GET /query/options`，加载失败时禁用文件精确选择并显示安全提示；
- 增加“本会话记住选择”，默认不勾选；
- 请求 JSON 必须发送新字段，非 custom 时发送 `retrieval_options: null`；
- 回答区域显示模式、范围、各阶段数量和降级提示，但不显示底层 RRF 分数；
- 增加“精确模式重试”“全面模式重试”；无结果且使用严格范围时增加“放宽范围重试”；重试应复用原问题，模式或 scope 的变化必须在 UI 可见；
- SSE `final` 和非流式响应共用同一渲染函数；历史消息也能渲染已有 `retrieval_metadata`；
- 对按钮做防重复提交，保持现有流式 delta、图片、来源链接和进度展示行为。

### 九、离线评估

扩展 Ragas 评估链路，使同一金标题库能显式指定模式，并把实际有效配置写入每行和 summary 快照：

- `collect_query()` 接受 `retrieval_mode` 和可选 custom 选项，并放入初始 state；
- CLI 增加 `--retrieval-mode balanced|precision|recall|custom`；如支持 custom CLI，必须复用生产解析器，不要再实现一套校验；
- 保留现有“默认禁用 Web 以获得稳定评估”的兼容行为，`--web` 作为明确覆盖，并在快照中同时记录模式原始策略和评估 Web 覆盖；
- 快照保存完整有效配置的可序列化副本，而不再只保存少量全局常量；
- 报告仍保留四层 ID 指标、Ragas、延迟和失败行；增加最终上下文数量，便于比较模式成本。

不要在单元测试阶段自动运行真实 LLM、Milvus、MongoDB 或 Web。真实四模式评估是实现后的人工步骤，不是本任务测试必须访问的外部依赖。

### 十、必须补充的测试

优先扩展现有测试文件；如果职责明显独立，可以新增测试文件。至少覆盖：

1. 三个预设的每个值与表格完全一致，balanced 与当前常量一致。
2. custom 边界值、非法枚举、越界数字、非 custom 携带 options、custom 缺 options 均按预期处理。
3. custom 派生配置满足全部内部不变量。
4. 不带新字段的旧请求解析为 balanced，且 HyDE/Web/参数保持原行为。
5. 显式 scope 覆盖 LLM 同字段，LLM 只补空字段；客户端不能注入 `hard_fields`。
6. 未知 document ID 被拒绝，Milvus 过滤表达式正确转义并使用 `document_id`。
7. HyDE/Web 关闭时相关 mock 断言为“从未调用”；开启时读取正确 Top-K。
8. 普通检索、RRF、Rerank、Answer 分别读取 state 配置，而不是固定常量。
9. Rerank 正常动态截断和异常回退都使用请求级最大值；严格单文件行为仍正确。
10. 三并行分支在开启、部分关闭、全部外部分支失败时都只汇合一次并到达答案节点。
11. 主动关闭不进入 degradations，执行异常进入稳定降级代码。
12. 非流式响应与 SSE `final` 的 `retrieval_metadata` 一致。
13. 旧历史文档可读取；新历史字段可保存和返回；会话偏好只在要求记忆时生效。
14. 评估 collector 正确传递模式，快照包含有效配置和 Web 覆盖。
15. 并发隔离：用两个不同配置并发调用纯 service/图 mock，断言参数不串值，且模块常量前后未变化。

测试必须 mock 外部依赖，并运行：

```powershell
python -m pytest -q
```

如果仓库实际测试入口不同，可使用等价命令，但要在最终说明中列出命令和结果。

### 十一、验收标准

实现完成需同时满足：

- 旧请求无需修改即可工作，默认行为无意外变化；
- 四模式在同一进程的并发请求中相互隔离；
- precision 确实减少候选、关闭默认 Web 并更积极截断；
- recall 确实扩大 ANN、RRF、Rerank、Web 和答案预算；
- custom 只能影响白名单业务参数，无法绕过服务端上限；
- 用户显式范围不会被 LLM 覆盖，严格范围不会被后台静默放宽；
- HyDE、Web、Reranker 失败仍可降级完成，并向用户显示安全的降级状态；
- SSE、非流式和历史记录使用一致的模式及元数据语义；
- 前端能选择、提交、展示、重试，且不破坏现有流式答案和图片展示；
- 离线评估能按模式运行并保存可复现配置快照；
- 全部无外部依赖测试通过。

### 十二、最终交付说明

完成编码后，最终回复应简洁列出：

1. 实际修改的模块和主要行为；
2. API 请求/响应新增字段；
3. balanced 向后兼容和并发隔离如何保证；
4. 测试命令与结果；
5. 尚未执行的真实 Milvus/LLM/Web/Ragas 验证及原因；
6. 如实现细节与本文不同，说明差异、证据和影响。

不要只返回代码片段或待办清单；应在仓库内完成可测试实现。
