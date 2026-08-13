# rewater-agent 架构审查报告

## 1. 审查目标与范围

本次审查目标是评估当前 rewater-agent 是否具备一个面向 AI Agent 应用工程岗位展示的高质量项目基础，并明确从当前商品识别 Agent 代码迁移到再生水领域知识库 Agent 的下一阶段路线。

本次审查只分析现状，不修改业务代码，不新增功能。

审查依据：

- `docs/ARCHITECTURE.md`
- `docs/PROJECT_CONTEXT.md`
- `docs/RAG_DESIGN.md`
- 当前 `app/`、`tests/`、项目配置和入口代码

项目核心目标是展示：

1. Agent Workflow 设计；
2. RAG 架构能力；
3. Hybrid Retrieval 能力；
4. Query Understanding 能力；
5. 行业知识库建设能力；
6. 必要的工程化能力。

用户认证、RBAC、多租户、完整文档版本管理、人工审核发布、长期 Memory 和企业级监控不属于当前核心审查目标。

## 2. 总体结论

当前项目已经具备较完整的 RAG/Agent 技术骨架：

- 两条 LangGraph 工作流；
- PDF/Markdown 导入；
- BGE-M3 Dense + Sparse Embedding；
- Milvus Hybrid Search；
- HyDE、RRF、Reranker；
- MCP 联网搜索；
- LLM 答案生成；
- SSE 流式输出；
- MongoDB 历史记录；
- RAG Eval 基础模块。

但项目现在还不能被视为“完整、可运行、可展示的 Agent Demo”。主要原因是：

1. 查询链存在确定性的导入和状态契约错误，完整依赖环境下也很可能无法启动或正确流转；
2. 当前业务仍围绕商品 `item_name`，与目标文档中的再生水行业 Query Understanding 和 metadata 检索存在明显差距；
3. 测试、README、启动入口和失败降级不足，无法稳定支撑架构迁移和面试演示。

建议下一阶段不要立即进行大规模行业重构。应先把现有技术链整理成可启动、可测试、可解释的稳定基线，再逐步替换商品语义。

## 3. 与目标架构的一致性检查

| 目标能力 | 当前状态 | 一致性 | 说明 |
|---|---|---:|---|
| FastAPI / SSE | 已存在 | 部分一致 | 导入、查询分为两个 FastAPI 服务；SSE 和任务状态使用进程内字典 |
| LangGraph Agent Workflow | 已存在 | 部分一致 | 两条图结构完整，但查询图存在导入及状态契约错误 |
| Query Understanding | 未实现目标形态 | 不一致 | 当前只提取 `item_names` 和 `rewritten_query` |
| 结构化 Query Rewrite | 部分存在 | 不一致 | 有 LLM 改写，但没有地域、文种、主题、时效等结构化检索计划 |
| Dense Retrieval | 已存在 | 部分一致 | 使用 BGE-M3 和 Milvus，但节点返回契约错误 |
| Sparse Retrieval | 已存在 | 部分一致 | BGE-M3 Sparse 向量已接入，但索引与检索 metric 不一致 |
| Metadata Filter | 未实现 | 不一致 | 当前只有 `item_name` 字符串过滤 |
| Web Search MCP | 已存在 | 基本一致 | 每次调用重新连接 MCP，失败时无法优雅降级 |
| RRF | 已存在 | 部分一致 | 实际只融合普通检索和 HyDE，没有融合 Web |
| Rerank | 已存在 | 部分一致 | BGE Reranker 已接入，但节点错误地把完整 state 写入 `reranked_docs` |
| 证据组织与引用 | 很弱 | 不一致 | 当前主要拼接标题、文本和分数，没有正式引用对象 |
| LLM 答案生成 | 已存在 | 部分一致 | 支持流式输出，但仍依赖商品主体和旧 Prompt |
| PDF/MD 解析 | 已存在 | 基本一致 | MinerU、图片摘要和 MinIO 已接入 |
| 行业文档分类 | 未实现 | 不一致 | 当前是商品主体识别 |
| 结构感知 Chunk | 初步存在 | 部分一致 | 按 Markdown 标题和字符数切分，未支持法规条款、页码和表格结构 |
| BGE-M3 Embedding | 已存在 | 基本一致 | Dense + Sparse 已实现 |
| Milvus | 已存在 | 部分一致 | Schema 固定为商品字段，尚无行业 metadata |
| RAG Eval | 已有骨架 | 部分一致 | 当前评测数据仍为 HAK180 商品场景，且受节点契约错误影响 |

结论：技术组件覆盖度较高，但目标架构的关键价值——行业 Query Understanding、metadata retrieval、证据引用——尚未形成。当前更接近“商品 RAG 原型”，还不是“再生水领域 Agent Demo”。

## 4. 当前项目问题

### A. 架构问题

#### A1. 查询工作流存在 P0 级断裂

以下节点导入了不存在的函数：

- `node_answer_output.py` 导入 `produce_answer`，实际实现为 `generate_answer`；
- `node_rrf.py` 导入 `fuse_retrieval_results`，实际实现为 `fuse_by_rrf`；
- `app/rag/query/__init__.py` 导出了多个不存在的名称：
  - `produce_answer`
  - `fuse_retrieval_results`
  - `search_chunks`
  - `search_chunks_with_hyde`
  - `validate_retrieval_state`

HyDE 还使用了不存在的 `milvus_gateway.chunk_collection_name`，实际网关属性是 `chunks_collection`。

这些是当前最先需要修复的问题。

#### A2. 节点和 Service 没有统一返回协议

普通检索中：

- Service 返回 `{"embedding_chunks": chunks}`；
- Node 又包装成 `{"embedding_chunks": service_result}`。

实际会形成嵌套结构：

```python
{
    "embedding_chunks": {
        "embedding_chunks": [...]
    }
}
```

HyDE 存在相同问题。

Rerank 更严重：

- `rerank_documents()` 返回完整 state；
- Node 又把这个 state 写入 `state["reranked_docs"]`。

最终 `reranked_docs` 会变成完整状态字典，而不是文档列表。

#### A3. 当前 Workflow 是固定流水线，Agent 路由能力较弱

当前查询图只有一个简单条件：

- 商品识别成功：并行执行三路检索；
- 商品识别失败：提前回答。

尚未体现：

- 查询意图分类；
- 是否需要联网搜索的动态判断；
- 是否需要 HyDE 的动态判断；
- 地域或文种不明确时的澄清；
- 检索为空时的降级路线；
- 多文档对比等任务路由。

因此 LangGraph 当前主要作为 DAG 编排器，还没有充分体现 Agent Workflow 设计能力。

#### A4. Web Search 成为本地 RAG 的硬依赖

Rerank 要求以下三项全部非空：

- `rewritten_query`
- `rrf_chunks`
- `web_search_docs`

MCP 搜索失败或返回空结果时，即使 Milvus 已经召回高质量资料，整个查询仍会失败。这与“Web Search 是可选增强”的目标定位不一致。

#### A5. 导入流程缺少一致性边界

当前流程会：

1. 先识别并写入商品主体集合；
2. 再做 Chunk Embedding；
3. 最后删除旧 Chunk 并插入新 Chunk。

如果后续失败，可能出现：

- 主体存在、正文不存在；
- 部分 Embedding 批次缺失；
- 已删除旧数据但新数据未完整写入。

对于当前 Demo 不需要建设完整事务系统，但至少应保证失败被明确报告，不把半成品标记为成功。

### B. 代码组织问题

#### B1. 生产代码混入大量手工测试和教学代码

静态统计结果：

- 109 个 Python 文件；
- 93 处 `print()`；
- 大约 26 个生产模块包含顶层手工运行代码；
- 节点和 Service 文件中存在大量 HAK180、手机和烫金机样例。

这会降低项目的专业观感，使阅读者难以快速区分正式实现、调试代码、教学注释和废弃实现。

建议后续把有价值的样例迁入 `examples/` 或真正的测试文件，但不必现在一次性清理全部文件。

#### B2. `shared` 与 `infra` 职责重叠

例如 Milvus：

```text
RAG Service
  → infra/vector_store/milvus_gateway.py
      → shared/clients/milvus_utils.py
          → pymilvus
```

MinIO、LLM 也存在类似双层包装。双层本身不是错误，但目前两层都很薄，业务代码有时直接依赖 `shared`，有时依赖 `infra`，边界不稳定。

建议保留 `infra` 作为正式出口，`shared/clients` 作为内部实现，不进行目录级大迁移。

#### B3. 配置管理有多个出口

配置同时分布在：

- `app/shared/config/*`
- `app/infra/config/providers.py`
- `app/infra/config/__init__.py`
- 部分模块直接读取 `os.getenv`
- 多处重复调用 `load_dotenv()`

此外：

- `settings_config.py` 使用 `settings = AppSettings`，保存的是类而不是实例；
- `McpConfig` 在同一个文件中定义了两次。

这会让配置来源和初始化时机难以解释。

#### B4. 项目入口不清晰

- 根 `main.py` 只输出旧项目名 `zhishiku`；
- 真正入口是两个独立 FastAPI 模块；
- README 为空；
- `pyproject.toml` 描述仍为 `Add your description here`。

对于岗位展示项目，这是明显的完成度缺口。

#### B5. 依赖清单偏重且存在漂移

项目同时维护：

- `pyproject.toml`
- `requirements.txt`
- `uv.lock`

三者并非完全一致。`neo4j` 当前在依赖中存在，但代码没有形成实际知识图谱能力，容易给人“堆技术栈但未落地”的印象。

### C. 模块职责问题

#### C1. `item_name_confirm_service` 职责过多

该文件同时负责：

- 请求参数校验；
- MongoDB 历史读取；
- Prompt 构建；
- LLM 结构化输出；
- Embedding；
- Milvus 主体检索；
- 阈值决策；
- 用户澄清答案；
- 历史记录写入。

它实际承担了 Query Understanding、Retrieval、Decision 和 Persistence 多种职责。

迁移时不建议直接拆成大量微模块，但至少应将未来 Query Understanding 的输出定义成稳定结构，并把历史写入留给流程边界或答案层。

#### C2. 导入主体 Service 同时负责领域抽取和数据库建表

`item_name_service.py` 同时包含：

- LLM 商品识别；
- Chunk 内容修改；
- Embedding；
- Milvus Schema 创建；
- 删除与插入。

未来行业 metadata 抽取不应同时负责创建和写入 Milvus 集合。

#### C3. API 层承载较多任务编排

`import_server.py` 同时负责上传、本地目录管理、文件保存、任务状态、LangGraph 后台执行和 HTTP 接口。

`query_server.py` 同样承担查询执行、SSE、任务状态和历史接口。

对小型 Demo 可以接受，但建议把“运行一次图”的用例入口保持为独立函数，使 API 测试和 CLI 演示都可以复用。

#### C4. 基础设施层吞掉异常

例如 Milvus 客户端或检索失败后返回 `None`，上层往往在更远的位置发生属性错误。

高质量 Demo 更适合：

- 基础设施错误抛出明确异常；
- Workflow 在节点边界决定降级或失败；
- 状态中记录 `errors` 或 `warnings`。

#### C5. RRF 与 Rerank 的来源模型不统一

候选数据使用了多种字段：

- `content` / `text` / `snippet`
- `source` / `type`
- Milvus score / RRF score / Rerank score 共用 `score`

这会让各阶段难以解释和调试。对于 Hybrid Retrieval 展示，应该能清晰看到召回来源、原始召回分、RRF 分、Rerank 分和最终排名。

### D. 命名和接口问题

#### D1. 公共函数名称与真实实现不一致

主要包括：

- `produce_answer` 与 `generate_answer`
- `fuse_retrieval_results` 与 `fuse_by_rrf`
- `search_chunks` 与 `search_by_embedding`
- `search_chunks_with_hyde` 与 `search_by_hyde`

这说明代码发生过重命名，但调用方和包出口没有同步。

#### D2. 返回类型标注与实际值不一致

示例：

- `search_by_embedding()` 标注返回 `QueryGraphState`，实际返回 state 增量字典；
- `rerank_documents()` 名称暗示返回文档列表，实际返回完整 state；
- `ImportGraphState.chunks` 标注为 `list[str]`，实际为 `list[dict]`；
- `QueryGraphState.answer` 标注为 `str`，部分逻辑会赋值为 `None`。

#### D3. 函数命名模糊且重复

多个模块使用：

- `get_data_and_validates`
- `deal_milvus_list`
- `require_chunks`

建议后续改为能表达具体对象和动作的名称，例如：

- `validate_retrieval_input`
- `format_chunk_hits`
- `validate_embedding_chunks`

#### D4. 拼写和历史命名残留

- `mivlus_result` 拼写错误；
- 根入口仍输出 `zhishiku`；
- 测试、日志和注释中大量出现手机、商品和烫金机；
- 任务名称中还存在未实现的知识图谱节点；
- `resource.md` 与 `resourse.md` 拼写不统一。

#### D5. Milvus 过滤接口不安全、不稳定

查询直接拼接：

```python
expr=f"item_name in {item_names}"
```

删除直接拼接：

```python
filter=f"item_name=='{item_name}'"
```

存在字符串转义、特殊字符、表达式兼容性和未来 metadata filter 难以复用等问题。

### E. 后续扩展风险

#### E1. Milvus Schema 被商品模型锁死

当前核心字段是：

- `item_name`
- `file_title`
- `title`
- `parent_title`
- `part`

缺少目标中的：

- `document_id`
- `document_type`
- `region_codes`
- `topics`
- `validity_status`
- `section_path`
- `clause_number`
- `page_start/page_end`

如果继续向现有 Schema 叠加功能，后续迁移成本会更高。

#### E2. Dense/Sparse Metric 不一致

索引创建使用 IP，查询请求默认使用 COSINE。这会影响检索正确性，Sparse 向量尤其需要明确统一 metric。

#### E3. 检索分支缺少降级

当前：

- 普通检索或 HyDE 任一路为空，RRF 失败；
- Web 为空，Rerank 失败；
- Milvus Gateway 出错返回 `None`，上层没有统一处理。

增加更多工具或检索方式后，这种“所有分支必须成功”的结构会越来越脆弱。

#### E4. Embedding 失败会静默丢数据

`embedding_service.py` 在某批失败后直接 `continue`。任务可能最终显示成功，但部分 Chunk 没有入库，这会让检索和评测结果不可解释。

#### E5. Chunk 与目标设计差距较大

当前：

- 按字符而不是 Token；
- overlap 实际为 0；
- 配置了 `CHUNK_MIN=300`，实际调用却传 `CHUNK_SIZE=600`；
- 没有真正的标题层级路径；
- 没有条款号和页码；
- 表格没有独立结构。

继续直接调参不会自然演变成行业结构化切分，需要先明确最小 metadata 契约。

#### E6. 测试体系不能支撑迁移

静态检查结果：

- 109 个 Python 文件语法有效；
- pytest 收集到 0 个测试；
- 当前 `tests/test_rag_eval_tester.py` 是手工调用示例，不是断言测试。

另外，工作区中原有多批测试文件处于删除状态。这些属于用户已有改动，本次未修改，但意味着当前测试基线较弱。

#### E7. 运行与部署可复现性不足

- README 为空；
- 根入口无效；
- 没有明确的一键启动方式；
- 外部依赖服务较多，但缺少启动前检查；
- 配置缺失往往到运行中才暴露。

## 5. 修改建议分级

### 5.1 必须修改：影响项目质量

这些事项应在行业功能开发之前完成：

1. 修复查询包所有缺失导入符号；
2. 统一 Node/Service 返回契约；
3. 修复 HyDE 的 Milvus 集合属性；
4. 让普通检索、HyDE、Web Search 支持独立失败和降级；
5. 修复 Dense/Sparse 索引与查询 metric；
6. 让 Embedding 批次失败明确导致导入失败，或实施有限重试；
7. 建立最小自动测试；
8. 建立有效入口和 README；
9. 在迁移前定义最小行业 state 和 metadata；
10. 修复上传文件名和 ZIP 解压的路径安全问题。

最小自动测试应至少覆盖：

- 查询图可构建；
- 导入图可构建；
- 节点 state 增量契约；
- RRF 单路/双路；
- Rerank 无 Web 降级；
- Query Rewrite 输出校验。

### 5.2 建议修改：提升工程能力展示

1. 将生产模块中的手工测试逐步迁到 `tests/` 或 `examples/`；
2. 为 Workflow 增加统一候选文档模型；
3. 分开记录 Retrieval、RRF、Rerank 分数；
4. 增加本地知识库、Web Search 和 HyDE 的动态路由；
5. 把 Query Rewrite 改成经过 Pydantic 校验的结构化输出；
6. 增加行业小型评测集；
7. 为节点统一记录耗时、输入数量、输出数量和降级原因；
8. 收敛配置出口并提供启动时配置检查；
9. 清理未落地依赖和历史名称；
10. 提供可离线或 Mock 运行的 Demo 模式，降低面试演示对外部服务的依赖。

### 5.3 可以暂时不做：避免过度设计

- 用户认证和 RBAC；
- 多租户；
- 完整文档版本系统；
- 人工审核工作台；
- 长期 Memory；
- 企业级监控平台；
- Redis/消息队列/复杂任务调度；
- Neo4j 和知识图谱；
- 微服务拆分；
- Kubernetes；
- Embedding 模型微调；
- 自动法规更新；
- 高并发优化；
- 完整前端重写。

## 6. 下一阶段开发路线

### P0：保证项目成为完整 Agent Demo

#### P0-1：恢复查询链路可运行性

目标：

- 所有包可以导入；
- 查询图可以构建；
- 每个节点返回正确 state 增量；
- 非流式查询可以贯通。

主要范围：

- `app/rag/query/__init__.py`
- 查询节点
- 查询 Service
- `QueryGraphState`

验收：

- 查询图 Import 成功；
- Mock 外部依赖后端到端通过；
- State 每个字段类型正确。

#### P0-2：建立最小测试安全网

至少增加：

- 图编译测试；
- Query Rewrite 输出测试；
- 普通检索节点契约测试；
- HyDE 节点契约测试；
- RRF 融合测试；
- Rerank 空 Web 降级测试；
- Answer Context 构建测试；
- Chunk 切分边界测试。

验收：

- pytest 可以收集并运行真实断言测试；
- 不依赖真实 LLM、Milvus 和 MongoDB 的单元测试可以快速运行。

#### P0-3：统一候选文档和状态契约

建议定义统一字段：

```text
document_id
chunk_id
content
title
source
source_url
retrieval_method
retrieval_score
rrf_score
rerank_score
metadata
```

验收：

- 普通检索、HyDE、Web 使用同一结果结构；
- RRF 和 Rerank 不再反复转换临时字段。

#### P0-4：实现可靠降级

最低要求：

- HyDE 失败时继续普通检索；
- Web 失败时继续本地检索；
- 单路召回可以进入 Rerank；
- 无召回时生成明确的证据不足回答；
- 节点失败原因进入日志或 state。

#### P0-5：建立可展示入口

需要：

- 有效 README；
- 正确项目描述；
- 清晰的启动命令；
- 环境依赖清单；
- 一条导入 Demo；
- 一条查询 Demo；
- 一张与实际代码一致的 Workflow 图。

#### P0-6：定义再生水最小 Metadata

第一阶段只实现：

- `document_id`
- `title`
- `document_type`
- `region_codes`
- `topics`
- `source`
- `publish_date`
- `validity_status`
- `section_path`
- `content`

不一次建设全部规划字段。

### P1：体现高级能力，提高面试竞争力

#### P1-1：结构化 Query Understanding

输出：

- 独立问题；
- 地域；
- 文种；
- 专业主题；
- 时效；
- 是否需要澄清；
- 是否需要 Web/HyDE。

展示点：

- Pydantic 结构化输出；
- 失败 fallback；
- LangGraph 条件路由。

#### P1-2：真正的 Hybrid Retrieval

展示：

- Dense 与 Sparse 独立召回结果；
- Metadata Filter；
- RRF 融合；
- Rerank 前后排名变化；
- 单路降级。

这是最能体现项目技术含量的部分。

#### P1-3：行业结构感知 Chunk

优先支持两种最有代表性的文档：

1. 法规/标准：章、节、条、款；
2. 论文/报告：标题层级、摘要、结论、表格。

不必一次覆盖所有文种。

#### P1-4：证据引用模型

最终回答应包含：

- 文档标题；
- 章节或条款；
- 页码（解析可用时）；
- 来源；
- 效力状态；
- 本地知识库或 Web 标记。

#### P1-5：行业 RAG 评估

构建小而高质量的评测集，展示：

- Recall@K；
- MRR；
- 必须命中率；
- Rerank 前后变化；
- Query Understanding 准确率；
- 引用正确性。

#### P1-6：Workflow 可观测性

每个节点记录：

- 耗时；
- 输入/输出数量；
- 调用模型；
- 是否降级；
- 召回来源；
- 最终分数。

不需要企业监控平台，日志和评估报告即可。

### P2：研究性质功能

- HyDE 是否对再生水语料有真实增益的 A/B 评测；
- Multi Query Expansion；
- Parent-Child Retrieval；
- 多文档政策/标准对比 Agent；
- 表格专用检索；
- 法规效力冲突检测；
- GraphRAG/Neo4j；
- Embedding/Reranker 模型对比；
- Agent 工具：单位换算、指标核查、标准编号查找；
- 自动检索策略选择；
- LLM-as-a-Judge 回答评估。

## 7. 推荐实际执行顺序

建议把下一阶段拆成六个小变更，而不是一次大重构：

1. 修复查询导入名称和节点返回契约；
2. 补查询图与核心 Service 契约测试；
3. 统一检索结果模型并实现失败降级；
4. 完善入口、README 和可运行 Demo；
5. 定义最小行业 metadata 与 Query Understanding state；
6. 再替换 `item_name` 商品流程，形成第一版再生水 Agent。

在第 1～4 步完成之前，不建议直接重写整个商品识别业务。否则无法区分迁移产生的问题与原有链路问题。

## 8. 审查验证说明

本次静态检查结果：

- 109 个 Python 文件语法可以解析；
- pytest 当前收集到 0 个测试；
- 静态符号审计确认查询包存在缺失导入；
- 当前系统 Python 环境缺少 FastAPI，因此未完成真实服务导入和端到端运行验证；
- 工作区已有未提交修改和测试文件删除，本次未触碰这些内容。

