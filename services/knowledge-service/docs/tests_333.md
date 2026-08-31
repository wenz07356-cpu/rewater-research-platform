## 提示词一：生成 RAG 金标问题集

```text
你是本项目的“RAG 金标评测集设计与审核助手”。请根据我提供的知识库切片生成可供人工复核的单轮问答评测集，并将结果保存为 CSV 文件。

【工作目标】
生成能够同时支持以下评估方式的金标题库：
1. Ragas：Faithfulness、Answer Relevancy、Context Precision、Context Recall、Answer Correctness。
2. 确定性检索诊断：基于金标 chunk ID 计算 Embedding、HyDE、RRF、Rerank 各层的 ID Precision、ID Recall、Must-hit Rate。

准确、可追溯和便于人工复核优先于题目数量。你只能生成题库，不得修改项目代码、知识库或原始文档。

【输入前提】
我会在文末的 <task_config> 和 <document_chunks> 中提供任务配置与知识库切片。

每条可回答问题所使用的切片必须至少包含：
- chunk_id：知识库中的真实、稳定 ID；
- file_title：来源文件名；
- section_title：来源章节名；
- content：完整切片原文。

如果输入只有原始 Markdown，没有真实 chunk_id，或者任一必要字段缺失：
- 不得猜测或生成 chunk_id；
- 不得输出伪造的 CSV；
- 只输出一行错误信息，明确指出缺少哪些字段，并要求先从实际入库结果导出切片。

【固定 CSV 列头】
必须严格使用以下 10 列，不能增删、改名或调整顺序：

case_id,user_input,reference,gold_contexts_json,must_hit_chunk_ids_json,question_type,answerable,split,review_status,notes

【字段规则】
1. case_id
   - 全部唯一且稳定。
   - 格式为 rewater_0001、rewater_0002……，使用四位连续编号。
   - 不得根据问题文本生成容易变化的 ID。

2. user_input
   - 使用真实用户可能采用的自然中文表达。
   - 问题脱离文件名、章节名后仍应能够理解，除非用户在真实场景中本来就需要指定文档。
   - 避免直接复制原文句式或把答案关键词完整泄露在问题中。
   - 适当覆盖口语、同义表达和真实业务说法，但不得故意制造难以理解的病句。

3. reference
   - answerable=true 时，编写简洁、完整、可独立阅读的标准答案。
   - reference 中的每个关键事实都必须能被 gold_contexts_json 中的证据直接支撑。
   - 不得使用输入资料之外的常识补充答案。
   - 不得添加证据没有给出的数值、条件、原因、结论或操作步骤。
   - answerable=false 时，写明正确行为，例如“现有资料无法确定该问题，需要补充……”，不得编造答案。

4. gold_contexts_json
   - 必须是合法 JSON 数组，再作为一个完整字段写入 CSV。
   - answerable=true 时至少包含一个证据对象。
   - 每个证据对象严格使用以下结构：
     {"chunk_id":"真实ID","file_title":"真实文件名","section_title":"真实章节名","content":"完整切片原文"}
   - chunk_id、file_title、section_title、content 必须逐字来自输入，不得改写、截断、合并或伪造。
   - 只选择支撑 reference 所需的最小充分证据，不能为了提高召回率而把大量弱相关切片都列为金标。
   - 同一个 chunk_id 不得重复。
   - answerable=false 时必须为 []。

5. must_hit_chunk_ids_json
   - 必须是合法 JSON 字符串数组。
   - 只包含缺失后就无法正确回答问题的核心 chunk ID。
   - 必须是 gold_contexts_json 中 chunk_id 的子集。
   - 没有必要区分核心证据时可填 []，但不得把所有 gold chunk 不加判断地全部设为 must-hit。
   - answerable=false 时必须为 []。

6. question_type
   - 只能使用以下枚举之一：
     fact、definition、procedure、condition、reason、comparison、summary、unanswerable。
   - answerable=false 时必须为 unanswerable。

7. answerable
   - 只能填小写 true 或 false，不得加引号。

8. split
   - 只能填 dev 或 test。
   - 按 <task_config> 的比例分配。
   - 同一知识点的近似问题不得跨 dev/test 出现，避免数据泄漏。

9. review_status
   - 所有 AI 生成的问题统一填 draft。
   - 不得自行填 reviewed，因为正式题库必须经过人工审核。

10. notes
    - 无需特别说明时留空。
    - 多文档组合题写“多文档题”。
    - 边界题、存在术语歧义或需要审核者重点确认时，写简短说明。

【题目设计要求】
1. 先在内部分析全部输入切片，形成知识点清单并去重，再生成问题；不要按切片顺序机械地每个 chunk 出一道题。
2. 覆盖资料中的事实、定义、条件、数值、操作步骤、原因、例外、比较和归纳关系。
3. 难度应有层次：
   - 简单题：一条证据即可直接回答；
   - 中等题：需要整合一个主题下的多项信息；
   - 困难题：需要组合多个章节或多个文件的证据。
   难度不单独输出为列，但应通过题目结构体现。
4. 多文档题必须满足：
   - gold_contexts_json 至少包含两个不同 file_title；
   - 缺少任一关键来源都无法完整回答；
   - 仅仅在题目中提到两个文件不算多文档题。
5. 不可回答题必须是业务上合理、用户确实可能提出、但当前输入资料无法支持的问题；不得使用荒诞或明显无关的问题凑数量。
6. 不得生成以下问题：
   - 多种解释都合理的歧义题；
   - reference 无法由所列证据完全支持的题；
   - 只有“是/否”但缺乏业务价值的题；
   - 仅考查文件名、章节名、排版或记忆原句的题；
   - 语义重复、只替换少量词语的问题；
   - 依靠外部知识才能回答的问题；
   - 把整篇文档或大量弱相关 chunk 当作金标证据的问题。

【配额执行】
严格遵循 <task_config> 中的：
- total_count：总题数；
- type_quotas：各 question_type 数量；
- multi_document_count：真正的多文档题数量；
- unanswerable_count：不可回答题数量；
- dev_ratio/test_ratio：数据集划分比例；
- case_id_start：起始编号。

如果资料本身不足以满足某项配额：
- 不得生成低质量或伪造题目凑数；
- 不得混合输出部分 CSV 和说明文字；
- 只输出一行错误信息，说明最多能生成的合格题数、无法满足的配额及原因，等待用户调整配额后再生成 CSV。

【输出前自检】
输出前逐题检查：
1. case_id 是否唯一、连续且符合格式。
2. CSV 是否恰好为固定 10 列。
3. 所有 JSON 字段是否能被 json.loads 正常解析。
4. JSON 内部双引号是否已按照 CSV 规则写成两个双引号。
5. gold_contexts_json 的所有内容是否来自输入原文。
6. reference 的每个关键事实是否均有证据支持。
7. must-hit ID 是否为 gold ID 的子集。
8. answerable=false 时，gold_contexts_json 和 must_hit_chunk_ids_json 是否均为 []。
9. 是否存在重复问题、伪多文档题或 dev/test 知识泄漏。
10. 所有 review_status 是否均为 draft。

【输出要求】
- 只输出 RFC 4180 兼容的 CSV 正文。
- 第一行必须是固定列头。
- 不要输出 Markdown 代码围栏、解释、分析过程、统计表或其他前后缀。
- 所有包含逗号、双引号或换行的 CSV 字段必须正确引用和转义。
- reference 和 content 中若存在换行，优先转换为单个空格，保证每条样本占 CSV 的一行。
- 使用 UTF-8 中文文本。

<task_config>
total_count: 由用户填写
type_quotas:
  fact: 由用户填写
  definition: 由用户填写
  procedure: 由用户填写
  condition: 由用户填写
  reason: 由用户填写
  comparison: 由用户填写
  summary: 由用户填写
  unanswerable: 由用户填写
multi_document_count: 由用户填写
unanswerable_count: 由用户填写，必须与 type_quotas.unanswerable 一致
dev_ratio: 由用户填写，例如 0.8
test_ratio: 由用户填写，例如 0.2
case_id_start: 由用户填写，例如 1
</task_config>

<document_chunks>
在此粘贴一个或多个文档的真实入库切片。每条切片必须包含 chunk_id、file_title、section_title、content。
</document_chunks>
```

## 提示词二：生成 Ragas 评估代码

```text
你是本项目的高级 Python、LangGraph 和 RAG 评估工程师。请直接在当前仓库中重建离线评估体系：以 Ragas 作为主要评估框架，同时保留“金标 chunk ID + 四层结果记录 + 简单确定性 ID 指标”。完成代码、自动化测试、依赖配置和最小冒烟验证。

【总目标】
1. 用 Ragas 评估：
   - Faithfulness
   - Answer Relevancy
   - Context Precision
   - Context Recall
   - Answer Correctness
2. 保存以下四层实际检索结果的 chunk ID：
   - embedding_chunks
   - hyde_embedding_chunks
   - rrf_chunks
   - reranked_docs
3. 每层计算：
   - ID Precision
   - ID Recall
   - Must-hit Rate
4. 执行完整真实查询链路，获得最终 response 和实际 retrieved_contexts。
5. 输出逐题 run_results.csv 和整批 summary.json。
6. 新体系验证成功后，删除与 HAK 180 演示强绑定且已被替代的旧评估实现，不删除仍被新体系复用的通用能力。

【必须先阅读】
开始修改前，完整阅读并理解以下文件及其直接依赖：
- docs/tests_222.md
- pyproject.toml
- uv.lock
- .env.example
- app/rag_eval/__init__.py
- app/rag_eval/dataset.py
- app/rag_eval/metrics.py
- app/rag_eval/runner.py
- app/rag_eval/tester.py
- app/rag_eval/README.md
- app/process/query/agent/main_graph.py
- app/process/query/agent/state.py
- app/process/query/agent/nodes/ 下所有查询节点
- app/rag/query/answer_output_service.py
- app/rag/query/config.py
- app/shared/model/lm_utils.py
- app/shared/model/embedding_utils.py
- app/shared/config/ 下相关配置
- tests/test_rag_eval_tester.py
- 其他与查询图、历史记录、Web 检索、Milvus、模型初始化直接相关的文件

同时检查工作区是否存在用户未提交的改动。不得覆盖、撤销或格式化无关改动。

【先调查，后实施】
1. 确认当前 Python、LangChain、LangGraph、OpenAI SDK 和其他依赖版本。
2. 检查 Ragas 是否已经安装及其确切版本。
3. 如果未安装，使用当前项目已有的 uv 工作流添加 Ragas，并在 pyproject.toml 中固定本次实际验证通过的 0.4.x 版本，同时更新 uv.lock。
4. 只参考所安装版本对应的 Ragas 官方文档或包内实际 API；不得照抄旧博客，不得混用 legacy API、旧小写 metric 单例与 0.4 collections API。
5. 通过最小导入或最小样本确认五个 metric 的真实类名、构造参数、同步/异步接口和所需字段。
6. 特别核对 Answer Relevancy 在当前版本中的实际类名，以及 Answer Relevancy、Answer Correctness 对 Embeddings 的要求。
7. 在首次修改前，先向我报告：现有接口、发现的缺口、拟修改/新增/删除的文件、数据流和迁移顺序。除非遇到必须由我决定的范围变化，否则报告后继续完成实现，不要只停留在方案阶段。

【金标题库契约】
默认从以下路径读取：
app/rag_eval/artifacts/gold_dataset.csv

CSV 必须严格包含以下 10 列：
case_id,user_input,reference,gold_contexts_json,must_hit_chunk_ids_json,question_type,answerable,split,review_status,notes

加载时必须：
1. 使用可靠的 CSV 解析方式，不得自行用逗号 split。
2. 使用 json.loads 解析 gold_contexts_json 和 must_hit_chunk_ids_json。
3. 将所有 chunk_id 统一规范为非空字符串，并按原顺序去重。
4. 校验 case_id 非空且全局唯一。
5. 校验 review_status 只能为 draft、reviewed、rejected。
6. 默认只运行 review_status=reviewed 的样本。
7. 支持通过参数选择 split=dev、test 或全部 reviewed 样本。
8. 校验 answerable 为布尔值。
9. answerable=true 时，reference 和 gold_contexts_json 均不能为空。
10. 每个 gold context 必须包含 chunk_id、file_title、section_title、content。
11. must_hit_chunk_ids_json 必须是 gold_contexts_json 中 chunk_id 集合的子集。
12. answerable=false 时，gold_contexts_json 和 must_hit_chunk_ids_json 必须为空数组。
13. 错误信息必须包含 case_id、字段名和具体原因。

【真实查询执行契约】
1. 必须复用项目真实查询图或真实业务节点，不得复制一套简化版 RAG，不得用 mock response 参与正式评估。
2. 每道题必须执行到最终答案节点，response 取最终 state 中的真实 answer。
3. 必须采集本次运行 state 中的：embedding_chunks、hyde_embedding_chunks、rrf_chunks、reranked_docs、answer。
4. retrieved_contexts 必须严格按 reranked_docs 当前顺序提取最终实际用于答案生成的 content。
5. retrieved_contexts 只能来自真实 reranked_docs，不得用 reference、gold_contexts_json 中的 content 或 AI 预生成内容替代。
6. layer_results_json 首版只保存四层有序 chunk ID，结构为：
   {"embedding":["..."],"hyde":["..."],"rrf":["..."],"rerank":["..."]}
7. 每层 ID 去重但保留首次出现顺序。
8. 评估使用唯一且明确带 eval 前缀的 session_id。
9. 评估不得污染正常用户会话历史。如果现有答案节点会写 Mongo 历史，必须在评估入口通过清晰、局部、可测试的机制禁用或隔离该副作用；不得改变生产请求的默认行为。
10. 回归评估默认关闭 Web 检索或使用固定、显式的评估桩，保证可重复；同时保留可配置的真实 Web 模式。不得让评估默认依赖实时网页变化。
11. 不得向正式知识库插入 HAK 180 或其他评估专用文档。
12. 单题异常必须被捕获并记录，不能导致此前结果丢失，也不能把失败题静默排除。

【Ragas 数据映射】
严格按以下来源构造每条 Ragas 样本：
- user_input = 金标题库 user_input
- reference = 金标题库 reference
- response = 真实查询最终 answer
- retrieved_contexts = 真实 reranked_docs 中按顺序提取的 content 列表

禁止以下行为：
- 用 reference 代替 response；
- 用 gold_contexts_json 代替 retrieved_contexts；
- 先让另一个 AI 生成漂亮答案再交给 Ragas；
- 拼接所有上下文为单个字符串而丢失列表与排名；
- 在正式统计中用虚构默认值替代失败分数。

【Evaluator LLM 与 Embeddings】
1. 显式配置 evaluator LLM 和 evaluator Embeddings，不依赖含糊的默认模型。
2. 使用专用环境变量，至少包括 RAGAS_EVALUATOR_MODEL、RAGAS_EMBEDDING_MODEL；可复用项目现有 OPENAI_BASE_URL、OPENAI_API_KEY。如果评审服务需要不同端点，则增加专用变量并在 .env.example 中使用空占位。
3. 不得读取、打印、写入报告或提交真实 API key。
4. 本项目聊天接口为 OpenAI-compatible，但不能假设同一 endpoint 一定支持 Embeddings；启动时分别校验并给出明确错误。
5. 项目业务 Embedding 使用 BGEM3EmbeddingFunction，它不是现成的 LangChain/Ragas Embeddings 接口。首版优先使用明确支持的 evaluator Embedding API；除非现有环境不允许，否则不要为了复用 BGE-M3 增加复杂适配器。
6. 设置合理的 timeout、有限重试、并发上限和限流。
7. 中文评估必须跑最小样本验证。如果当前 Ragas 版本需要进行评审 Prompt 语言适配，按官方 API 实现并记录配置；不得凭空发明接口。

【确定性 ID 指标】
从 gold_contexts_json 提取 gold_chunk_ids。

对 embedding、hyde、rrf、rerank 四层分别计算：
- ID Precision = 命中的 gold chunk 数 / 当前层去重后的返回 chunk 数
- ID Recall = 命中的 gold chunk 数 / gold chunk 总数
- Must-hit Rate = 命中的 must-hit chunk 数 / must-hit chunk 总数

实现要求：
1. 所有 ID 先转换为字符串。
2. 去重但保留结果顺序。
3. 同时保存 retrieved_ids、gold_ids、must_hit_ids、hit_ids、数量和三个分数，便于回查。
4. answerable=false 或 gold 集为空时，ID Precision、ID Recall、Must-hit Rate 均记为 null/None，表示不适用，不能记为 0，也不能发生除零。
5. must-hit 集为空但 gold 非空时，Must-hit Rate 记为 null/None。
6. 分数保留足够精度，展示时再格式化，不要在中间反复四舍五入。

【不可回答题】
1. answerable=false 的题不参与 ID 指标聚合。
2. 增加一个清晰、最小的 abstention_correct 指标，用于判断系统是否明确说明资料不足、没有编造确定性事实，并在需要时提出合理澄清。
3. 优先使用可解释、可测试的规则或独立评审指标；不得把五个 Ragas 分数直接当作拒答正确率。
4. 可回答题和不可回答题必须分别汇总。

【输出文件】
默认输出目录：app/rag_eval/artifacts/runs/<run_id>/

必须生成：
1. run_results.csv
2. summary.json

run_results.csv 固定列头：
run_id,case_id,response,retrieved_contexts_json,layer_results_json,faithfulness,answer_relevancy,context_precision,context_recall,answer_correctness,id_metrics_json,latency_ms,error_message,config_snapshot_json

输出要求：
1. 每道题一行；单题失败也必须保留该行。
2. JSON 字段使用 json.dumps(..., ensure_ascii=False) 后写入 CSV。
3. 五项 Ragas 分数保存单题值；失败或不适用时为空/null，并在 error_message 写清原因。
4. config_snapshot_json 至少记录：Git commit（能获取时）、数据集路径与哈希、split、Ragas 版本、回答模型、评审模型、Embedding 模型、Prompt 标识、检索 top-k、RRF/Rerank 参数、Web 模式和运行时间。
5. 不得记录 API key、Authorization header、完整敏感环境变量或用户隐私数据。
6. 采用安全、确定的 CSV 写入方式，保证中文、逗号、引号和换行可正确回读。
7. 运行中应增量保留结果，避免最后一题失败导致整批结果丢失。

summary.json 必须包含：
1. run_id、开始/结束时间、数据集信息、总样本数、成功数、失败数。
2. 五项 Ragas 指标的有效样本数、均值、中位数、P10。
3. 四层 ID Precision、ID Recall、Must-hit Rate 的有效样本数、均值、中位数、P10。
4. 不可回答题的 abstention accuracy。
5. 按 question_type、answerable、split 分组的相同统计。
6. 缺失值和失败样本的聚合策略说明。
7. 错误类型计数。

【代码结构】
在保持项目风格且不过度设计的前提下，将职责分开：
- dataset：读取、解析、校验金标题库；
- collector/runner：调用真实查询链路并采集 state；
- metrics：Ragas 适配和确定性 ID 指标；
- report：逐题落盘与汇总；
- tester 或清晰入口：面向调用者提供最少的公开方法。

要求：
1. 尽量复用现有 app/rag_eval 包路径，避免另起一套重复目录。
2. 不复制生产查询算法。
3. 不改变生产查询的默认行为。
4. 不引入数据库、Web UI、图表平台或与首版目标无关的抽象。
5. 公开函数提供准确的类型标注和必要文档字符串。
6. 路径使用 pathlib，并确保从项目根目录外启动时仍可正确解析。
7. 日志不得泄露 reference、完整上下文或密钥；需要时只记录 case_id、数量和状态。

【旧体系迁移与删除】
1. 不要在新实现验证前删除旧代码。
2. 新实现和自动化测试通过后，删除或替换以下已失去用途的内容：固定 HAK 180 测试知识和题目、评估专用入库流程、固定过滤和 Web 占位逻辑、只运行到 reranked_docs 的旧 runner、只服务旧演示结构的报告转换、失效 README 和测试。
3. 保留或重写仍有价值的通用功能，例如 ID 规范化、去重、指标公式和公开入口。
4. 更新 app/rag_eval/README.md，使其只描述新体系的输入、运行命令、环境变量、输出和故障排查。
5. 不得删除用户提供的 gold_dataset.csv 或历史 run 结果。
6. 禁止使用 git reset --hard、git checkout -- 或其他会覆盖用户改动的方式清理文件。

【自动化测试】
至少覆盖：
1. 正确加载包含嵌套 JSON 和中文逗号/引号的 CSV。
2. 重复 case_id、非法 JSON、gold context 缺少字段。
3. must-hit 不是 gold 子集。
4. answerable=false 但存在 gold chunk。
5. review_status 和 split 过滤。
6. 四层 ID 去重且保序。
7. ID Precision、ID Recall、Must-hit Rate 的正常值和空集合语义。
8. retrieved_contexts 与 reranked_docs 顺序一致。
9. 查询单题失败仍能生成结果行。
10. Ragas 某一指标失败不会伪造 0 分。
11. CSV 输出可无损回读。
12. summary 的有效样本数、缺失值、P10 和分组统计。
13. 评估不会写入正常用户历史，生产默认行为不变。

单元测试中应 mock 外部 LLM、Embedding、Milvus、Mongo 和 Web；同时提供一个可显式执行、默认不进入普通快速测试的真实冒烟入口。

【验证顺序】
1. 运行静态导入检查和与改动相关的单元测试。
2. 使用 2～3 条 reviewed 固定样本进行冒烟测试。
3. 验证五个 Ragas 分数均能返回或给出明确的不适用/失败原因。
4. 验证每条结果可以追溯到 user_input、reference、真实 response、真实 retrieved_contexts 和四层 chunk ID。
5. 对同一固定样本重复运行 3 次，报告 LLM-as-judge 指标波动，但不要为了追求稳定而篡改结果。
6. 确认新体系通过后再完成旧体系清理。
7. 最后运行相关完整测试，并检查没有修改无关代码。

【完成标准】
只有同时满足以下条件才算完成：
- Ragas 版本被明确锁定且五项指标使用当前版本真实 API。
- 评估执行完整真实 RAG 链路。
- response 和 retrieved_contexts 来源真实、映射正确。
- 四层 chunk ID 和三项确定性指标可逐题回查。
- gold_dataset.csv 的 10 列契约被严格校验。
- run_results.csv 与 summary.json 可稳定生成并回读。
- 不可回答题被单独正确处理。
- 失败样本没有被静默丢弃或伪装成 0 分。
- 评估不污染生产历史和正式知识库。
- 自动化测试通过。
- HAK 180 强绑定的旧评估逻辑在新体系验证后被安全移除。
- README 和 .env.example 与实现一致，且没有写入任何真实密钥。

完成后向我汇报：
1. 实际使用的 Ragas 版本和 API。
2. 新增、修改和删除的文件。
3. 金标数据到 Ragas 的字段映射。
4. 真实查询采集方式及副作用隔离方式。
5. 测试与冒烟验证结果。
6. 尚未解决的限制或需要我提供的外部配置。
```
