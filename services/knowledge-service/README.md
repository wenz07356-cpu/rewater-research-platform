# Knowledge Service

`knowledge-service` 是再生水知识与深度研究平台的知识底座，负责市政水务资料入库、证据问答和内部知识检索。服务使用 LangGraph 编排处理流程，以 Milvus 保存知识切片和向量，以 MongoDB 保存问答历史，以 MinIO 保存文档图片，并通过两个 FastAPI 进程分别提供入库与查询能力。

该目录可以单独开发和测试；如需体验完整平台，建议回到仓库根目录使用 `compose.yaml` 启动，统一入口为 <http://localhost:8080>。

## 核心能力

- 文档入库：接收 PDF 或 Markdown 文件，完成解析、图片处理、元数据抽取、标题感知切分、BGE-M3 向量化和 Milvus 写入。
- 知识问答：支持 Dense/Sparse 混合检索、HyDE、RRF 融合、BGE Reranker、可选联网搜索和 SSE 流式输出。
- 检索模式：内置均衡、精确回答、全面检索、自定义四种请求级模式。
- 来源追溯：本地证据标识文件与章节，网络证据保留 URL。
- 内部检索：通过稳定的 `/retrieval` HTTP 契约向 `research-service` 返回精排证据，不暴露 Milvus 实现细节。
- RAG 评估：提供问题集、RAGAS 评估流程和结果报告模块。

## 处理流程

### 文档入库

```text
上传 PDF / Markdown
  -> 识别文件类型
  -> PDF 转 Markdown（Markdown 文件跳过此步）
  -> Markdown 图片处理
  -> 文档元数据抽取
  -> 按标题切分并处理表格、代码块及长短片段
  -> BGE-M3 向量化
  -> 写入 Milvus
```

### 证据问答

```text
用户问题
  -> 查询理解与改写
  -> 普通向量检索 + HyDE 检索 + 可选 Web 检索
  -> RRF 融合
  -> BGE Reranker 精排
  -> 基于证据生成回答
  -> 普通 JSON 或 SSE 输出
```

## 目录结构

```text
knowledge-service/
|-- app/
|   |-- api/                 # FastAPI 路由和 Pydantic 接口模型
|   |-- infra/               # LLM、向量库、对象存储、文档解析和持久化适配
|   |-- process/
|   |   |-- import_/         # 入库 LangGraph、节点和演示页面
|   |   `-- query/           # 查询 LangGraph、节点和聊天页面
|   |-- rag/
|   |   |-- import_/         # 解析、切分、元数据、向量化与索引业务服务
|   |   `-- query/           # 检索、HyDE、RRF、精排和答案业务服务
|   |-- rag_eval/            # RAGAS 数据、指标、执行器和报告
|   |-- resources/prompts/   # LLM 提示词
|   `-- shared/              # 配置、客户端、模型加载、日志和通用工具
|-- tests/                   # 单元测试、接口测试和检索模式测试
|-- .env.example             # 独立运行时的配置模板
|-- Dockerfile
|-- pyproject.toml
`-- uv.lock
```

## 运行要求

- Python 3.12。
- 推荐使用 [uv](https://docs.astral.sh/uv/) 管理依赖。
- Milvus、MongoDB、MinIO；导入 PDF 时还需要可访问的 MinerU 服务。
- OpenAI 兼容的文本/视觉模型接口。
- BGE-M3 与 BGE Reranker v2 M3 模型文件。模型也可通过配置指向其他有效路径。
- 联网搜索使用 DashScope WebSearch MCP；不需要联网时可在查询请求中关闭。

## 配置

在当前目录创建本地配置：

```powershell
Copy-Item .env.example .env
```

至少需要核对以下配置：

| 配置组 | 主要变量 | 用途 |
| --- | --- | --- |
| 应用 | `APP_HOST`、`IMPORT_APP_PORT`、`QUERY_APP_PORT` | 两个 HTTP 进程的监听地址和端口 |
| LLM | `OPENAI_BASE_URL`、`OPENAI_API_KEY`、`LLM_DEFAULT_MODEL`、`VL_MODEL` | 查询理解、回答、元数据及图片理解 |
| Embedding | `BGE_M3_PATH`、`BGE_DEVICE`、`BGE_FP16` | 文档与问题向量化 |
| Reranker | `BGE_RERANKER_LARGE`、`BGE_RERANKER_DEVICE` | 候选证据精排 |
| Milvus | `MILVUS_URL`、`CHUNKS_COLLECTION` | 知识切片、稠密向量和稀疏向量 |
| MongoDB | `MONGO_URL`、`MONGO_DB_NAME` | 会话历史 |
| MinIO | `MINIO_ENDPOINT`、`MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY`、`MINIO_BUCKET_NAME` | 文档图片存储 |
| MinerU | `MINERU_BASE_URL`、`MINERU_API_TOKEN` | PDF 解析 |

不要提交包含真实密钥的 `.env`。`MINIO_ENDPOINT` 不应包含 `http://` 或 `https://`；协议由 `MINIO_SECURE` 控制。

## 本地启动

安装锁定依赖：

```powershell
uv sync --frozen
```

分别启动入库服务和查询服务（需要两个终端）：

```powershell
uv run uvicorn app.api.http.import_server:app --host 0.0.0.0 --port 8000
```

```powershell
uv run uvicorn app.api.http.query_server:app --host 0.0.0.0 --port 8001
```

启动后可访问：

| 功能 | 地址 |
| --- | --- |
| 入库页面 | <http://localhost:8000/html> |
| 入库接口文档 | <http://localhost:8000/docs> |
| 查询页面 | <http://localhost:8001/html> |
| 查询接口文档 | <http://localhost:8001/docs> |
| 入库健康检查 | <http://localhost:8000/health> |
| 查询健康检查 | <http://localhost:8001/health> |

也可以从仓库根目录启动整个平台：

```powershell
Copy-Item .env.example .env
.\scripts\start.ps1
```

根级启动方式、可选本地基础设施和健康检查说明见仓库根 [README](../../README.md)。

## HTTP 接口

### 上传文档

`POST /upload` 使用 `multipart/form-data`，字段名为 `files`，支持一次提交多个文件：

```powershell
curl.exe -X POST http://localhost:8000/upload `
  -F "files=@C:\docs\再生水政策.pdf" `
  -F "files=@C:\docs\地方标准.md"
```

响应中的每个 `task_id` 对应一个文件。入库在 FastAPI 后台任务中执行，可轮询状态：

```powershell
curl.exe http://localhost:8000/status/<task_id>
```

当前任务状态保存在进程内存中，重启入库进程后不会保留；已写入外部存储的知识数据不受影响。

### 非流式问答

`POST /query`：

```powershell
$body = @{
  query = "深圳市再生水利用现状如何？"
  is_stream = $false
  retrieval_mode = "balanced"
  web_enabled = $true
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri http://localhost:8001/query `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

`retrieval_mode` 可取：

- `balanced`：在准确性、召回范围和耗时之间保持均衡。
- `precision`：缩小候选范围，优先返回少量高相关证据。
- `recall`：扩大候选与最终参考范围，适合综述性问题。
- `custom`：必须同时提供 `retrieval_options`，用于调整候选数、参考数、关键词/语义偏好和 HyDE 影响。

`web_enabled` 独立控制本次请求是否使用联网搜索。省略时使用所选模式的默认值。

### 流式问答

先向 `POST /query` 提交 `is_stream: true`，获得 `session_id`，随后连接：

```text
GET /stream/{session_id}
```

该接口使用 `text/event-stream` 返回阶段进度、答案片段、最终结果或错误事件。浏览器演示页面已包含完整调用方式。

### 内部证据检索

`POST /retrieval` 面向 `research-service`，只检索证据，不生成最终回答：

```json
{
  "query": "再生水用于工业冷却的水质要求",
  "top_k": 6
}
```

响应状态为 `ok`、`empty` 或 `needs_clarification`；`top_k` 当前允许 1～6。

### 会话历史

```text
GET    /history/{session_id}?limit=10
DELETE /history/{session_id}
```

## 测试

在当前目录执行完整测试：

```powershell
uv run --with pytest pytest -q
```

按模块执行：

```powershell
uv run --with pytest pytest tests/test_import_document_services.py -q
uv run --with pytest pytest tests/test_query_services.py -q
uv run --with pytest pytest tests/test_retrieval_modes.py -q
uv run --with pytest pytest tests/test_retrieval_api.py -q
```

部分集成路径会加载本地模型或访问外部基础设施；运行前应确认 `.env`、模型目录和服务地址有效。

## 数据与日志

- 非容器运行时，默认数据目录为当前服务目录同级的 `rewater-agent-data-base/`。
- 上传文件与中间产物位于 `rewater-agent-data-base/output/YYYYMMDD/<task_id>/`。
- 日志位于 `rewater-agent-data-base/logs/`，默认按天轮转并保留 7 天。
- 根级 Compose 使用 `knowledge-data` 命名卷持久化上述运行数据。

## 与 Research Service 的边界

`knowledge-service` 负责知识的导入、索引、检索和证据问答；`research-service` 负责任务编排、章节研究与报告生成。研究服务通过查询进程的 `/retrieval` 接口读取证据，不直接连接 Milvus。修改该接口的请求或响应模型时，应同步运行 `tests/test_retrieval_api.py` 以及 research-service 中的知识库工具契约测试。
