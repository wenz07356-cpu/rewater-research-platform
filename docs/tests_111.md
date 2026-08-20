# 本项目 RAG 评估方案：题库、Ragas 与执行流程

> 目标：只梳理评估思路、数据格式、提示词、安装和执行步骤，不修改项目代码。  
> 分析基线：当前仓库 `app/rag_eval/`、查询链路和依赖配置。  
> Ragas 文档核对日期：2026-08-19。

## 1. 先给结论

原来的三步方向是对的，但建议拆成下面五步，否则“生成题库”和“跑指标”之间缺少数据采集与质量控制：

1. 冻结评估对象：确定知识库版本、切分参数、检索参数、模型和 Prompt 版本。
2. 建设金标题库：由 AI 起草问题、参考答案和证据，人审后才能成为基线。
3. 运行真实 RAG：逐题获得真实 `response`、`retrieved_contexts` 和各层 `chunk_id`。
4. 双层评估：保留项目现有的确定性检索指标，同时用 Ragas 评估语义检索质量和最终答案质量。
5. 汇总与诊断：按问题类型、难度、来源文件和链路阶段分组，不只看五个总平均分。

当前项目的 `app/rag_eval` 已经能评估：

- `embedding_chunks`：普通检索；
- `hyde_embedding_chunks`：HyDE 检索；
- `rrf_chunks`：RRF 融合；
- `reranked_docs`：最终重排；
- 指标为主体命中率、基于 `chunk_id` 的 precision、recall 和 must-hit rate。

但现有 runner 在 `reranked_docs` 处结束，没有调用最终答案节点，因此没有生成用于 Ragas 的 `response`，也无法计算 Faithfulness、Answer Relevancy 和 Answer Correctness。后续生成评估代码时，首要工作不是直接调用 Ragas，而是补齐“执行完整查询链路并采集答案与上下文”这一层。

推荐保留两类指标：

| 层次 | 指标 | 价值 |
| --- | --- | --- |
| 确定性检索指标 | 当前项目的 chunk ID precision、recall、must-hit rate | 无评审模型随机性，能准确定位普通检索、HyDE、RRF、rerank 哪层退化 |
| Ragas 语义指标 | Faithfulness、Answer Relevancy、Context Precision、Context Recall、Answer Correctness | 判断上下文是否真正有用，以及最终答案是否忠实、切题、正确 |

二者名称虽然相似，但不能互相替代。例如，项目当前的 precision 是“命中的金标 chunk 数 / 返回 chunk 数”；Ragas Context Precision 还关注相关上下文在排序中的位置，并可通过评审模型按语义判定相关性。

## 2. 评估前先固定实验基线

每次评估应保存一个 `run_id`，并记录以下快照：

- Git commit 或代码版本；
- 知识库版本、源文件清单及文件哈希；
- chunk 切分大小、重叠长度和 metadata 规则；
- 普通召回、HyDE、RRF、rerank 的 top-k 与阈值；
- Embedding、Reranker、回答模型、评审模型的名称与版本；
- 查询 Prompt、HyDE Prompt、答案 Prompt 的版本；
- temperature、随机种子（若模型支持）、运行时间；
- 是否启用 Web 检索，以及 Web 结果是否固定。

否则两次分数变化时，无法判断是参数优化、知识库变化、模型升级还是外部 Web 内容变化造成的。

建议第一阶段只评估单轮、本地知识库问答，并关闭或固定 Web 检索。等基线稳定后，再单独建立“联网问答”和“多轮对话”题库。五个目标指标都可以很好地用于单轮 RAG；多轮场景需要额外保存历史消息，并增加多轮或会话级指标。

## 3. 问题集应该怎样组织

### 3.1 不建议把所有字段都塞进一个 CSV

最清晰的方式是分成两个文件，通过 `case_id` 关联：

1. `gold_dataset.csv`：版本化保存人工审核后的题目和金标，不随某次运行改变。
2. `run_results.csv`：每次执行产生的答案、检索上下文、分数、耗时和错误。

如果现阶段只想维护一个 CSV，也可以把运行字段留空；但必须明确：`response`、`retrieved_contexts_json` 和 `retrieved_context_ids_json` 只能由真实 RAG 运行填写，不能由题库生成 AI 预先填写。

### 3.2 `gold_dataset.csv` 推荐列头

CSV 不原生支持数组，所有列表字段统一保存为合法 JSON 字符串，例如 `["chunk-1","chunk-2"]`，不能使用 Python 列表写法或用逗号自行拼接。

| 列名 | 必填 | 含义 | 用途 |
| --- | --- | --- | --- |
| `case_id` | 是 | 稳定且唯一的题号，如 `rewater_single_001` | 关联运行结果、人工复核和回归对比 |
| `user_input` | 是 | 用户真实会提出的问题 | Ragas `user_input`；对应当前项目的 question/original_query |
| `reference` | 是 | 经人工审核的标准答案 | Context Precision、Context Recall、Answer Correctness |
| `reference_contexts_json` | 是 | 支撑标准答案的最小、完整原文片段列表 | 证据审查与内容级检索对比 |
| `reference_context_ids_json` | 是 | 上述证据对应的稳定 chunk ID 列表 | 对接项目现有 precision/recall；避免只依赖 LLM 判分 |
| `must_hit_chunk_ids_json` | 建议 | 答对此题不可缺少的关键 chunk ID | 对接当前 `must_hit_rate` |
| `expected_item_names_json` | 过渡期建议 | 预期主体列表 | 兼容当前项目的主体命中率；未来领域化后可换成预期过滤条件 |
| `source_files_json` | 是 | 证据来源文件列表 | 可追溯、多文档问题检查、分文件统计 |
| `source_sections_json` | 建议 | 证据所在章节列表 | 人工回查和定位切分问题 |
| `question_type` | 是 | 如 fact、procedure、comparison、reason、summary、unanswerable | 分类型分析，不让简单事实题掩盖复杂题退化 |
| `difficulty` | 是 | easy、medium、hard | 分难度分析 |
| `scope` | 是 | single_doc、multi_doc | 检查单文档与跨文档能力 |
| `answerable` | 是 | true 或 false | 区分可回答题与拒答题 |
| `expected_behavior` | 建议 | answer、clarify、abstain | 对模糊题和知识库外问题定义正确行为 |
| `tags_json` | 建议 | 业务主题、地区、文档类型等标签 | 分组统计和抽样 |
| `split` | 是 | dev 或 test | dev 用于调参，test 只做最终验收，避免过拟合 |
| `generation_method` | 是 | human、ai_single_doc、ai_multi_doc、log_mining 等 | 追踪题目来源 |
| `review_status` | 是 | draft、reviewed、rejected | 只有 reviewed 进入正式评估 |
| `reviewer` | 建议 | 审核人或审核批次 | 质量追责 |
| `notes` | 否 | 歧义、边界或评分注意事项 | 辅助人工诊断 |

一个概念示例：

```csv
case_id,user_input,reference,reference_contexts_json,reference_context_ids_json,must_hit_chunk_ids_json,expected_item_names_json,source_files_json,source_sections_json,question_type,difficulty,scope,answerable,expected_behavior,tags_json,split,generation_method,review_status,reviewer,notes
rewater_single_001,某项再生水要求是什么？,依据文档应满足A并完成B。,"[""原文证据A"",""原文证据B""]","[""chunk-101"",""chunk-108""]","[""chunk-101""]","[]","[""文件甲.md""]","[""第三章"""]",procedure,medium,single_doc,true,answer,"[""规范"",""操作"""]",dev,ai_single_doc,reviewed,reviewer_1,
```

### 3.3 `run_results.csv` 推荐列头

| 列名 | 来源 | 含义 |
| --- | --- | --- |
| `run_id` | 评估程序 | 一次完整实验的唯一 ID |
| `case_id` | 金标题库 | 与 `gold_dataset.csv` 关联 |
| `response` | 真实 RAG | 最终答案；对应 Ragas `response` |
| `retrieved_contexts_json` | 真实 RAG | 按最终传给答案模型的顺序保存 `reranked_docs[*].content` |
| `retrieved_context_ids_json` | 真实 RAG | 与上述文本严格一一对应的 chunk ID |
| `embedding_ids_json` | 真实 RAG | 普通检索层 ID |
| `hyde_ids_json` | 真实 RAG | HyDE 层 ID |
| `rrf_ids_json` | 真实 RAG | RRF 层 ID |
| `reranked_ids_json` | 真实 RAG | 最终重排层 ID |
| `faithfulness` 等五个分数 | Ragas | 单题分数，不只保存均值 |
| `latency_ms` | 评估程序 | 端到端耗时 |
| `token_usage_json` | 评估程序 | 可获得时记录回答模型与评审模型用量 |
| `error_type`、`error_message` | 评估程序 | 失败时保留，不静默丢题 |
| `config_snapshot_json` | 评估程序 | 本次实验配置快照 |

关键映射只有四个：

```text
user_input          <- 金标题库中的问题
reference           <- 金标题库中的标准答案
response            <- 本项目真实生成的最终答案
retrieved_contexts  <- 本项目最终传给答案模型的证据文本列表
```

`reference_context_ids` 和 `retrieved_context_ids` 则用于现有的确定性指标，文本字段用于 Ragas 的语义指标。

## 4. 问题集不仅可以从一个 Markdown 生成

### 4.1 可用的六种来源

1. 单文档生成：适合事实、定义、参数、操作步骤和注意事项题。
2. 多文档联合生成：适合比较、汇总、跨文档条件组合、冲突识别题。
3. 按 chunk/章节分层生成：先为章节分配题量，再生成，能避免长文档或开头章节垄断题目。
4. 真实日志挖掘：对历史用户问题脱敏、聚类后抽样，最贴近真实分布。
5. 专家手写和故障复盘：覆盖业务高风险、少见但重要的边界场景。
6. 反向与扰动生成：生成知识库外、条件缺失、术语别名、口语、错别字、否定问法和对抗性问题。

推荐混合，而不是只用 AI 从文档顺序出题。首版可采用如下分布，再根据真实流量调整：

| 类型 | 建议占比 |
| --- | ---: |
| 单文档直接事实/定义 | 25% |
| 操作步骤、条件和因果 | 20% |
| 多文档比较/归纳 | 15% |
| 真实用户日志改写 | 20% |
| 不可回答、应澄清问题 | 10% |
| 别名、口语、错别字、边界条件 | 10% |

### 4.2 多个 Markdown 生成一个问题集的方法

可以，而且这是更接近真实知识库的做法。推荐流程：

1. 为每个文件建立 `document_id/file_title/section_title/chunk_id/content` 清单。
2. 先让 AI 输出“候选知识点”，不立即出题。
3. 对知识点去重并标注所属文件、章节、主题和是否可跨文档组合。
4. 按题型和难度配额抽样，再生成问题、参考答案和证据。
5. 对 `multi_doc` 题强制至少引用两个文件，且答案确实必须组合两处证据；只是在问题里提到两个文件不算跨文档题。
6. 自动检查所有 reference context 必须能在输入原文中定位。
7. 人工审核后写入正式 CSV。

若全部文档过长，不要一次性塞给模型。应按“文件或章节生成候选题 -> 全局去重与配额平衡 -> 对候选题回查原文 -> 人审”的方式分批处理。

### 4.3 正式题库的最低质量门槛

- 问题无需看到文件名或章节名也能被真实用户理解，除非业务本来就会这样问。
- `reference` 只包含证据能支持的事实，不能由常识补全。
- `reference_contexts_json` 是最小充分证据，不把整篇文档当上下文。
- 每个证据片段都能定位到真实文件、章节和 chunk ID。
- 避免题干直接复述原文造成关键词泄漏；至少保留一批口语化或同义改写题。
- 多文档题确实需要组合多处证据。
- 不可回答题的 `reference` 应明确说明资料不足，`expected_behavior=abstain`；不要为它编造答案。
- 去除语义重复题，防止某一知识点被重复计权。
- AI 生成后必须人工抽查；正式 test 集建议全部审核。

## 5. 生成问题集的 AI 提示词

下面的提示词既可以处理一个 Markdown，也可以处理多个 Markdown。调用时把已经带有文件、章节和 chunk ID 的原文放到 `<documents>` 中。

```text
你是“再生水领域 RAG 评测集设计员”。你的任务是基于给定资料起草可人工审核的单轮问答金标集，而不是回答资料以外的问题。

【项目背景】
- 系统包含普通 Embedding 检索、HyDE 检索、RRF 融合、Reranker 和最终答案生成。
- 后续既要用 chunk ID 计算确定性 precision/recall/must-hit rate，也要用 Ragas 计算 Faithfulness、Answer Relevancy、Context Precision、Context Recall、Answer Correctness。
- 题库用于离线回归评估，准确性和可追溯性高于题目数量。

【输入】
1. documents：一个或多个 Markdown 文档。每个片段均提供 document_id、file_title、section_title、chunk_id、content。
2. quotas：题型、难度、single_doc/multi_doc、answerable/unanswerable 的数量要求。
3. split：dev 或 test。

【任务步骤】
1. 先识别资料中的独立知识点、操作步骤、条件、数值、因果、例外和跨文档关联。
2. 按 quotas 生成候选题，不要按文档顺序机械地每段出一道题。
3. 为每题编写只由资料支撑的 reference。
4. 选取能完整支撑 reference 的最小证据片段，输出原文和 chunk ID。
5. 对 multi_doc 题，证据必须来自至少两个不同 source_files，且缺少任一来源就无法完整回答。
6. 对 unanswerable 题，不得虚构 reference；reference 写明“现有资料无法确定”，expected_behavior 设为 abstain。
7. 自检歧义、重复、证据不足、题干泄漏答案、伪跨文档题；不合格题直接删除。

【输出格式】
- 只输出 RFC 4180 兼容的 CSV，不要输出 Markdown 代码围栏和解释文字。
- 第一行严格使用以下列名：
case_id,user_input,reference,reference_contexts_json,reference_context_ids_json,must_hit_chunk_ids_json,expected_item_names_json,source_files_json,source_sections_json,question_type,difficulty,scope,answerable,expected_behavior,tags_json,split,generation_method,review_status,reviewer,notes
- 所有 *_json 字段必须是合法 JSON 数组，并按 CSV 规则转义双引号。
- review_status 一律填 draft，reviewer 留空。
- case_id 使用前缀 rewater_，不得重复。
- question_type 只能取 fact、definition、procedure、condition、reason、comparison、summary、unanswerable。
- difficulty 只能取 easy、medium、hard；scope 只能取 single_doc、multi_doc。
- generation_method 根据本批任务填 ai_single_doc 或 ai_multi_doc。

【硬性约束】
- 不使用 documents 外部知识。
- 不伪造 chunk_id、文件名、章节或原文。
- reference_contexts_json 与 reference_context_ids_json 数量及顺序严格一致。
- must_hit_chunk_ids_json 必须是 reference_context_ids_json 的子集。
- 每个 answerable=true 的 reference 中，每项关键事实都必须能被所列证据支持。
- 不得生成仅靠问题措辞就能猜出答案的题。

<quotas>
在此填写数量，例如：总计 40 题；easy/medium/hard=12/20/8；single_doc/multi_doc=30/10；unanswerable=4。
</quotas>

<documents>
在此粘贴带 document_id、file_title、section_title、chunk_id、content 的资料。
</documents>
```

生成后不要直接进入正式 test 集。先做结构校验、原文回查、去重，再由人工把 `review_status` 改为 `reviewed`。

## 6. 五个 Ragas 指标怎样理解

Ragas 当前文档在界面上将 Answer Relevancy 所属页面称为 Response Relevancy，但 collections API 类名为 `AnswerRelevancy`。生成代码时必须以实际安装版本的导入测试为准，不要混用旧博客里的小写单例、旧字段名和新 API。

| 指标 | 需要的核心字段 | 回答的问题 | 不能说明什么 |
| --- | --- | --- | --- |
| Faithfulness | `response`、`retrieved_contexts` | 回答中的陈述是否能由实际检索上下文支撑 | 不保证回答完整，也不保证参考答案本身正确 |
| Answer Relevancy | `user_input`、`response`，并需 Embeddings | 回答是否切题、直接、不过度冗余 | 不核实事实正确性 |
| Context Precision | `user_input`、`reference`、`retrieved_contexts` | 相关上下文是否排在无关上下文之前 | 不等于项目基于 chunk ID 的简单 precision |
| Context Recall | `reference`、`retrieved_contexts` | 标准答案中的关键信息是否被检索上下文覆盖 | 不判断最终回答是否使用了这些信息 |
| Answer Correctness | `user_input`、`response`、`reference`，并需 Embeddings | 最终回答与标准答案在事实和语义上是否一致 | 不能单独解释错误来自检索还是生成 |

诊断组合：

- Context Recall 低：优先查切分、metadata filter、Embedding、HyDE 和召回 top-k。
- Recall 高但 Context Precision 低：候选噪声多或排序差，优先查 RRF、rerank 和 top-k。
- Context 指标高但 Faithfulness 低：证据足够，回答模型仍加入了无依据内容，查答案 Prompt 和模型。
- Faithfulness 高但 Answer Correctness 低：回答可能忠于错误/不充分上下文，或漏掉标准答案关键点。
- Correctness 高但 Relevancy 低：答案可能包含正确内容但冗长、绕题或没有直接回应。

对不可回答题，以上五项并不足以完整评价“是否正确拒答”。建议额外加入 `abstention_accuracy` 或人工规则：当 `expected_behavior=abstain` 时，检查答案是否明确说明资料不足且未编造事实。这可以先作为项目自定义指标，不必强行套进五项均值。

## 7. Ragas 安装与验证

### 7.1 当前项目状态

仓库的 `pyproject.toml`、`requirements.txt` 和 `uv.lock` 中没有发现 Ragas。因此当前并未把 Ragas 安装为项目依赖。项目使用 Python 3.12 和 uv，优先沿用 uv，不建议同时用系统 pip 修改环境。

Ragas 官方安装命令是 `pip install ragas`，官方 quickstart 也支持 uv。PyPI 在本次核对时展示的稳定版为 0.4.3。由于 Ragas 0.4 的 collections API 与旧教程差异较大，实际实施时建议先在分支中显式固定验证过的版本，而不是长期使用无上限的最新版。

建议实施命令（本次不执行）：

```powershell
uv add "ragas==0.4.3"
uv sync
uv run python -c "import ragas; print(ragas.__version__)"
```

如果决定跟随当时最新版，则先执行 `uv add ragas`，跑通一个最小样本并锁定 `uv.lock`，再开始写正式评估代码。不要直接照抄 0.1/0.2 时代的教程。

### 7.2 评审 LLM 与 Embeddings

本项目已经通过 `ChatOpenAI` 使用 OpenAI-compatible 地址，因此评审 LLM 可以沿用相同 `OPENAI_BASE_URL`、`OPENAI_API_KEY` 和模型配置，前提是该服务与所选模型能稳定完成结构化评审。

Answer Relevancy 和 Answer Correctness 需要 Embeddings。项目当前业务检索使用的是 `BGEM3EmbeddingFunction`，它不是现成的 LangChain Embeddings 接口。实施时有两种选择：

1. 推荐先使用评审服务提供的 OpenAI-compatible Embedding API，并在评估配置中单独设置 evaluator embedding model。
2. 若必须复用本地 BGE-M3，为它编写符合 Ragas/所用框架协议的适配器，并用固定样本验证维度、归一化、同步/异步接口和中文相似度。

不要默认聊天模型的 base URL 一定支持 embeddings；需要先用一个最小调用验证。评审模型最好与被评系统的回答模型分离，至少在关键 test 集上如此，以降低同模型自评偏差。

### 7.3 最小冒烟验证

正式跑全量前，只选 2～3 条 reviewed 样本，依次验证：

1. 能导入实际安装版本中的五个 metric 类。
2. 中文问题、答案和上下文能得到非空分数。
3. `retrieved_contexts` 是 `list[str]`，不是拼成一个大字符串。
4. Answer Relevancy 与 Answer Correctness 确实拿到了 Embeddings。
5. 无 API key、限流、超时、空答案时能够留下错误记录。
6. 同一样本重复 3 次，观察 LLM-as-judge 指标波动。

官方参考：

- [Ragas Installation](https://docs.ragas.io/en/stable/getstarted/install/)
- [Ragas Quick Start](https://docs.ragas.io/en/stable/getstarted/quickstart/)
- [EvaluationDataset schema](https://docs.ragas.io/en/stable/references/evaluation_schema/)
- [Faithfulness](https://docs.ragas.io/en/v0.3.9/concepts/metrics/available_metrics/faithfulness/)
- [Answer/Response Relevancy](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/answer_relevance/)
- [Context Precision](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_precision/)
- [Context Recall](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_recall/)
- [Answer Correctness](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/answer_correctness/)
- [Ragas 0.3 -> 0.4 migration](https://docs.ragas.io/en/latest/howtos/migrations/migrate_from_v03_to_v04/)

## 8. 生成评估代码的 AI 提示词

这段提示词应在真正准备实施代码时使用。它要求 AI 先读仓库、列设计，再改代码；本次文档任务不执行它。

```text
你是本项目的 RAG 离线评估工程师。请基于当前仓库实现评估代码，不得凭空假设接口。先阅读并理解：
- pyproject.toml、uv.lock
- app/rag_eval/dataset.py
- app/rag_eval/metrics.py
- app/rag_eval/runner.py
- app/rag_eval/tester.py
- app/process/query/agent/main_graph.py
- app/process/query/agent/state.py
- app/rag/query/answer_output_service.py
- app/shared/model/lm_utils.py
- app/shared/model/embedding_utils.py
- 相关测试文件

【目标】
在保留现有分层 chunk ID 指标的基础上，增加 Ragas 0.4.x 的最终答案评估，计算：
1. Faithfulness
2. Answer Relevancy（注意核对当前安装版本的 collections API 名称）
3. Context Precision
4. Context Recall
5. Answer Correctness

【输入数据契约】
金标题库 CSV 至少包含：case_id、user_input、reference、reference_contexts_json、reference_context_ids_json、must_hit_chunk_ids_json、expected_item_names_json、review_status。
所有 *_json 字段读入后必须用 json.loads 解析并校验类型；只执行 review_status=reviewed 的样本。

【真实运行数据】
- user_input：来自金标题库。
- response：必须调用本项目真实完整查询链路得到，禁止用 reference 或 AI 预生成答案代替。
- retrieved_contexts：必须取本次运行中最终实际传给答案模型的 reranked_docs，按原顺序抽取 content。
- retrieved_context_ids：与 retrieved_contexts 一一对应抽取 chunk_id。
- 同时保存 embedding_chunks、hyde_embedding_chunks、rrf_chunks、reranked_docs 四层 ID，继续调用现有确定性指标。
- Web 检索必须可配置为关闭、固定桩或真实模式；默认回归评估使用关闭或固定桩，保证可重复。

【Ragas 与模型要求】
- 先检查 pyproject.toml/uv.lock 中实际安装的 Ragas 版本，再以该版本官方 API 编写；不要混用 legacy API 和 collections API。
- 显式创建 evaluator LLM 和 evaluator embeddings；从环境变量读取 endpoint/key/model，代码和日志中不得输出密钥。
- 本项目聊天模型使用 OpenAI-compatible API；不能假设同一 endpoint 支持 embeddings，启动时做配置校验并给出清晰错误。
- 支持中文；如对 Ragas 内置评审 Prompt 做语言适配，必须记录适配方式和版本。
- 设置 timeout、有限重试、并发上限和限流；单题失败记录 error_type/error_message，不得导致整批结果丢失。

【输出】
- 每次生成唯一 run_id。
- 保存单题结果，而不只保存平均值。
- 输出 run_results.csv 和 summary.json；包含五项 Ragas 分数、现有四层 chunk 指标、耗时、错误、模型名和配置快照。
- summary 按 question_type、difficulty、scope、answerable 分组，并报告有效样本数、失败数、均值、中位数、P10。
- 不把失败样本静默排除；聚合分母和缺失值策略必须写清楚。

【代码结构要求】
- dataset 模块只负责加载、解析和校验题库。
- collector/runner 负责调用真实 RAG 并采集 state。
- metrics 模块负责确定性指标与 Ragas 指标适配。
- report 模块负责落盘与汇总。
- 尽量复用现有 app/rag_eval，不复制业务查询逻辑。
- 不修改生产查询行为；评估逻辑不能污染线上历史会话或正式知识库。
- 为 CSV JSON 字段解析、字段映射、上下文顺序、空结果、单题失败、汇总统计编写自动化测试。

【实施顺序】
1. 先输出你从仓库确认到的真实接口、当前缺口、拟修改文件和数据流，不要立即写代码。
2. 给出最小实现方案并指出与旧 app/rag_eval 的兼容策略。
3. 经确认后再实现。
4. 先用 2～3 条固定样本做冒烟测试，再跑完整题库。

【验收条件】
- 对任一 case，可从报告追溯到问题、reference、response、最终上下文文本和每层 chunk ID。
- 五项指标所需字段均非伪造且来源明确。
- 相同固定配置重复运行可比较。
- Ragas 不可用时，现有确定性检索评估仍可独立运行，并清楚报告 Ragas 阶段失败。
```

## 9. 推荐的实际执行顺序

### 阶段 A：先把题库做对

1. 从真实知识库导出带稳定 chunk ID 的文档清单。
2. 先选 3～5 个有代表性的 Markdown，生成约 30～50 道候选题。
3. 同时覆盖单文档、多文档、步骤、条件、原因和不可回答问题。
4. 自动校验 CSV、JSON 列、ID 存在性和证据顺序。
5. 人工审核 reference 与证据，将合格样本标为 reviewed。
6. 划分 dev/test；后续调参只看 dev，test 不参与反复选择参数。

### 阶段 B：先跑现有检索评估

1. 先用现有四层 ID 指标建立 baseline。
2. 验证每层保存的 chunk ID 与文本一致。
3. 找出召回和 rerank 明显失败的题，先排除题库标注错误。

### 阶段 C：接入最终答案与 Ragas

1. 让评估 runner 走到 `node_answer_output`，采集真实 `answer`。
2. 保存最终实际用于回答的 `reranked_docs[*].content`，不要用金标 evidence 代替。
3. 用 2～3 条样本冒烟验证五个指标。
4. 小批量运行并检查费用、耗时、限流和分数稳定性。
5. 全量运行，保存逐题结果、汇总和配置快照。

### 阶段 D：再谈优化

优化时一次只改变一个主变量，例如 chunk size、召回 top-k、RRF 参数、rerank top-k 或答案 Prompt。每个候选配置至少比较：

- 五项 Ragas 指标；
- 当前项目四层确定性指标；
- 不可回答题准确率；
- P10 或低分题数量，而非只有均值；
- 延迟、调用成本和失败率。

只有 dev 集提升且冻结 test 集也通过门槛，才接受该参数。不要在每轮看过 test 明细后继续针对 test 调参，否则 test 会逐渐变成训练集。

## 10. 首版最小可行范围

为避免一开始做得过重，建议首版只完成：

1. 30～50 条 reviewed 单轮题，其中约 20% 为 multi_doc，10% 为 unanswerable。
2. 分离 `gold_dataset.csv` 与 `run_results.csv`。
3. 保留现有四层 chunk ID 指标。
4. 补齐最终 `response` 和实际 `retrieved_contexts` 的采集。
5. 接入五项 Ragas 指标并保存逐题结果。
6. 按 question_type、difficulty、scope 汇总。
7. 重复运行少量样本，记录评审模型波动。

做到这一步，已经可以回答三个关键问题：资料有没有被召回、召回结果是否真正有用、最终答案是否忠实且正确。之后再根据低分题的归因结果讨论具体参数优化。
