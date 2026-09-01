# Research Service

`research-service` 是再生水知识与深度研究平台的研究报告服务，面向市政水务领域完成研究任务书生成、大纲确认、多来源证据研究、章节组织和 HTML 报告输出。

服务使用 FastAPI 提供研究项目接口，使用 Celery 执行耗时任务，使用 MongoDB 保存项目、任务、章节、来源及报告版本。DeepAgents 负责研究规划和工具调用；内部资料优先通过 `knowledge-service` 的 HTTP 检索契约获取，公开资料可通过 Tavily 搜索并读取网页正文。

该目录可以单独开发和测试；如需体验完整平台，建议回到仓库根目录使用 `compose.yaml` 启动，统一入口为 <http://localhost:8080/research>。

## 核心能力

- 研究项目：根据主题、研究目标、受众、地域范围和时间范围创建研究任务。
- 可确认大纲：自动生成研究任务书和多级大纲，支持用户确认或通过自然语言提出修改要求。
- 异步研究：API 进程只负责创建任务，Celery Worker 在后台执行大纲生成、修改、章节研究和报告渲染。
- 多来源检索：研究子智能体可使用自研内部知识库、Tavily 搜索和网页正文读取工具。
- 市政研究约束：提示词要求区分政策、标准、规划、工程与运营资料，关注适用地域、时间效力、指标口径和来源可信度。
- 结构化证据：章节保存关键发现、来源编号、置信度、风险、不确定性、表格和图表描述。
- 确定性报告：研究完成后由代码将结构化章节渲染成 HTML，避免再次依赖模型自由生成版式。
- 来源追溯：报告正文中的 `source_id` 可跳转到末尾参考来源；内部知识库证据和公开网页使用统一来源结构。
- 报告版本：每次生成或重新渲染都会保存独立版本，并可按项目或全局获取最新报告。

## 业务流程

```text
创建研究项目
  -> Celery 生成研究任务书和大纲
  -> 用户查看大纲
  -> 确认大纲，或提交修改要求后再次确认
  -> 提交报告生成任务
  -> 主研究 Agent 按章节委派检索子智能体
       |-- knowledge-service /retrieval（内部知识证据）
       |-- Tavily Search（公开资料）
       `-- Web Reader（网页正文）
  -> 章节、来源和风险信息写入 MongoDB
  -> 确定性 HTML 渲染
  -> 保存报告版本并返回最新报告
```

大纲确认是明确的人工检查点。项目状态不是 `outline_confirmed` 时，报告生成接口会返回 `409`，防止未经确认直接开始长时间研究。

## 服务架构

```text
浏览器 / Gateway
       |
       v
FastAPI :8010
  |-- MongoDB：项目、任务、章节、来源、报告元数据
  `-- Redis：Celery broker
              |
              v
         Celery Worker
           |-- LLM / DeepAgents
           |-- knowledge-service :8001
           |-- Tavily / 公开网页
           `-- reports/：HTML 报告文件
```

API 和 Worker 必须连接同一套 MongoDB、Redis 和报告存储目录。根级 Compose 已通过共享环境变量和 `research-reports` 命名卷保证这一点。

## 目录结构

```text
research-service/
|-- app/
|   |-- agents/                 # DeepAgents 封装与市政研究提示词
|   |-- background/             # Celery 任务入口和异步业务流程
|   |-- config/                 # 类型化环境配置
|   |-- repository/             # MongoDB Repository 与报告文件存储
|   |-- routers/                # 研究项目、任务和报告接口
|   |-- schemas/                # 请求、响应和研究结果模型
|   |-- tools/                  # 内部知识库、外部搜索、网页读取、章节和报告工具
|   |-- celery_app.py           # Celery 应用配置
|   `-- main.py                 # FastAPI 应用入口
|-- static/index.html           # 深度研究工作台页面
|-- reports/                    # 独立运行时生成的 HTML 报告
|-- tests/                      # 工具契约、注册、模型、报告和网页读取测试
|-- .env.example               # 独立运行时配置模板
|-- Dockerfile
|-- pyproject.toml
`-- uv.lock
```

`app/tools/ragflow_search.py` 仅作为历史兼容文件保留，当前研究智能体不会注册或调用它；实际内部知识检索统一由 `knowledge_base_search.py` 完成。

## 运行要求

- Python 3.12。
- 推荐使用 [uv](https://docs.astral.sh/uv/) 管理依赖。
- MongoDB，用于持久化研究项目、任务状态、章节、来源和报告版本。
- Redis，用作 Celery broker。
- OpenAI 或 DeepSeek 模型接口。
- 正常生成报告时需同时运行 FastAPI 和 Celery Worker。
- 推荐运行 `knowledge-service` 查询进程；使用内部知识库时应确保其 `/retrieval` 接口可访问。
- Tavily API Key 为可选配置；未配置时公开搜索工具会返回 `skipped`，不会伪造搜索结果。

## 配置

在当前目录创建本地配置：

```powershell
Copy-Item .env.example .env
```

主要配置如下：

| 配置组 | 变量 | 用途 |
| --- | --- | --- |
| 应用 | `APP_NAME`、`APP_VERSION`、`API_PREFIX`、`LOG_LEVEL` | 服务名称、版本、API 前缀和日志级别 |
| MongoDB | `MONGODB_URI`、`MONGODB_DATABASE` | 项目、任务和报告数据持久化 |
| Celery | `REDIS_URL`、`CELERY_BROKER_URL` | Redis 连接和任务队列；后者为空时回退到前者 |
| LLM | `LLM_PROVIDER`、`LLM_MODEL_NAME`、`LLM_TEMPERATURE` | 研究智能体所用模型 |
| OpenAI | `OPENAI_API_BASE`、`OPENAI_API_KEY` | OpenAI 或兼容接口 |
| DeepSeek | `DEEPSEEK_API_BASE`、`DEEPSEEK_API_KEY` | DeepSeek 接口 |
| 研究范围 | `REPORT_MAX_SECTIONS` | 单次报告最多完整研究的章节数量，范围 1～50 |
| 内部知识库 | `ENABLE_KNOWLEDGE_SERVICE`、`KNOWLEDGE_SERVICE_BASE_URL`、`KNOWLEDGE_SERVICE_TOP_K` | 是否启用自研知识库、查询服务地址和返回证据数 |
| 外部搜索 | `TAVILY_API_KEY` | 启用 Tavily 公开搜索 |
| 报告文件 | `REPORT_STORAGE_BACKEND`、`REPORT_STORAGE_LOCAL_DIR` | HTML 报告存储方式和本地目录 |

注意事项：

- `KNOWLEDGE_SERVICE_BASE_URL` 应指向查询服务端口 `8001`，不是入库服务端口 `8000`。
- `KNOWLEDGE_SERVICE_TOP_K` 当前允许 1～6，与 knowledge-service 的公开契约一致。
- `REPORT_STORAGE_BACKEND` 当前应保持 `local`。代码中已预留 `minio` 类型，但 MinIO 报告存储尚未实现。
- 不要提交包含真实密钥的 `.env`。

## 本地启动

### 1. 安装依赖

```powershell
uv sync --frozen --extra dev
```

### 2. 准备基础设施

确保 `.env` 中的 MongoDB 和 Redis 地址可从当前主机访问。如果使用内部知识库，还需先启动 knowledge-service 查询进程：

```powershell
Push-Location ..\knowledge-service
uv run uvicorn app.api.http.query_server:app --host 127.0.0.1 --port 8001
Pop-Location
```

### 3. 启动 FastAPI

```powershell
uv run uvicorn app.main:app --host 127.0.0.1 --port 8010
```

### 4. 启动 Celery Worker

另开一个终端，在当前目录执行：

```powershell
uv run celery -A app.celery_app:celery_app worker --loglevel=INFO --pool=solo
```

Windows 本地开发建议使用 `--pool=solo`；Linux 或容器内可使用默认 worker pool。启动后可访问：

| 功能 | 地址 |
| --- | --- |
| 深度研究页面 | <http://127.0.0.1:8010/> |
| API 文档 | <http://127.0.0.1:8010/api/v1/docs> |
| OpenAPI | <http://127.0.0.1:8010/api/v1/openapi.json> |
| 健康检查 | <http://127.0.0.1:8010/health> |

### 使用根级 Compose

完整平台推荐从仓库根目录启动：

```powershell
Copy-Item .env.example .env
.\scripts\start.ps1
```

根级启动会同时运行网关、knowledge-service 入库与查询进程、research-service API 和 Worker。启动方式、可选本地基础设施与健康检查说明见仓库根 [README](../../README.md)。

## HTTP 接口

除 `/health` 和静态页面外，接口默认位于 `/api/v1` 下。

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `POST` | `/research-projects` | 创建项目，并异步生成任务书和大纲 |
| `GET` | `/research-projects/{project_id}/outline` | 获取当前大纲和项目状态 |
| `PUT` | `/research-projects/{project_id}/outline` | 确认大纲或提交修改要求 |
| `POST` | `/research-projects/{project_id}/report-tasks` | 基于已确认大纲生成研究报告 |
| `POST` | `/research-projects/{project_id}/report-render-tasks` | 用已有章节重新渲染报告，不重新研究 |
| `GET` | `/tasks/{task_id}` | 查询 Celery 业务任务状态 |
| `GET` | `/research-projects/{project_id}/reports/latest` | 获取指定项目的最新报告 |
| `GET` | `/reports/latest` | 获取所有项目中最近生成的报告 |

### 1. 创建研究项目

```powershell
$body = @{
  topic = "深圳市再生水利用现状与提升路径"
  research_goal = "梳理政策、设施、利用规模与主要制约并提出建议"
  target_audience = "市政水务管理人员"
  region_scope = "china"
  time_scope = @{
    type = "recent_years"
    years = 5
  }
} | ConvertTo-Json -Depth 4

$project = Invoke-RestMethod `
  -Uri http://127.0.0.1:8010/api/v1/research-projects `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

创建响应包含 `project_id` 和 `initial_task_id`。前端应轮询任务接口，直到状态变为 `succeeded` 或 `failed`：

```powershell
Invoke-RestMethod "http://127.0.0.1:8010/api/v1/tasks/$($project.initial_task_id)"
```

地域范围可取 `china`、`overseas`、`global`；时间范围类型可取 `recent_years` 或 `unlimited`。使用 `recent_years` 时必须提供 1～20 的 `years`。

### 2. 查看、修改或确认大纲

查看大纲：

```powershell
Invoke-RestMethod "http://127.0.0.1:8010/api/v1/research-projects/$($project.project_id)/outline"
```

提交修改要求会创建新的异步任务：

```json
{
  "action": "revise",
  "revision_instruction": "增加再生水工业利用和风险控制章节"
}
```

确认当前大纲：

```powershell
$confirm = @{ action = "confirm" } | ConvertTo-Json
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8010/api/v1/research-projects/$($project.project_id)/outline" `
  -Method Put `
  -ContentType "application/json" `
  -Body $confirm
```

### 3. 生成报告

```powershell
$request = @{
  user_instruction = "突出政策依据、建设现状和可执行建议"
} | ConvertTo-Json

$reportTask = Invoke-RestMethod `
  -Uri "http://127.0.0.1:8010/api/v1/research-projects/$($project.project_id)/report-tasks" `
  -Method Post `
  -ContentType "application/json" `
  -Body $request
```

轮询 `$reportTask.task_id`，成功后获取报告：

```powershell
Invoke-RestMethod "http://127.0.0.1:8010/api/v1/research-projects/$($project.project_id)/reports/latest"
```

最新报告响应包含完整 `html`、版本号和来源列表。`report-render-tasks` 只适用于项目已经保存章节的情况，可在不重复检索和研究的前提下生成新报告版本。

## 后台任务状态

业务任务状态持久化在 MongoDB 中，与 Celery 自身内部状态分离：

```text
queued -> running -> succeeded
                  `-> failed
```

Worker 对未处理异常最多自动重试 3 次，并使用指数退避和随机抖动。API 返回的 `task_id` 应通过 `/api/v1/tasks/{task_id}` 查询，而不是直接访问 Celery backend。

## 检索与来源策略

当 `ENABLE_KNOWLEDGE_SERVICE=true` 时，检索子智能体按现有工具顺序注册：

1. `external_search`：使用 Tavily 查找公开资料。
2. `read_web_page`：读取选定网页的正文和基础元数据。
3. `knowledge_base_search`：调用自研知识库 `/retrieval` 获取内部精排证据。

提示词要求市政研究优先检查内部知识库，并使用公开资料补充时效性、统计数据或内部资料未覆盖的内容。工具返回 `skipped`、`empty`、`needs_clarification` 或 `error` 时，Agent 应显式降级，不得把缺失结果当作真实来源。

## 报告存储

- 项目、任务、章节、来源和报告元数据保存在 MongoDB。
- HTML 正文默认写入 `REPORT_STORAGE_LOCAL_DIR`，默认值为 `reports/`。
- MongoDB 中保存报告文件 URI，读取最新报告时再从文件存储加载 HTML。
- 根级 Compose 将报告目录映射到 `research-reports` 命名卷，以便 API 和 Worker 共享文件并在容器重建后保留报告。
- `REPORT_STORAGE_BACKEND=minio` 尚不可用，选择后会抛出 `NotImplementedError`。

## 测试与检查

在当前目录执行：

```powershell
uv run ruff check app tests
uv run pytest -q
uv run python -m compileall -q app tests
```

测试覆盖重点包括：

- `test_knowledge_base_search.py`：内部知识库 HTTP 契约和异常归一化。
- `test_search_tool_registration.py`：检索子智能体的工具注册与开关行为。
- `test_simplified_research_model.py`：研究结果模型、来源和报告生成流程。
- `test_latest_report.py`：项目级及全局最新报告接口。
- `test_web_reader.py`：网页正文解析、代理回退和错误处理。

多数测试通过替身隔离外部服务；真实端到端研究仍需要可用的 MongoDB、Redis、Worker、LLM，以及按需启用的 knowledge-service 和 Tavily。

## 已知限制

- 当前没有用户鉴权和多租户隔离，只适合本地演示或可信内网环境。
- 报告文件仅实现本地文件系统存储，MinIO/S3 适配仍是占位实现。
- `REPORT_MAX_SECTIONS` 会限制完整研究章节数量，适合控制比赛演示时长和模型成本，但过小会降低报告覆盖面。
- 网页读取器采用轻量 HTML 解析，不执行 JavaScript；动态渲染页面、登录页面或反爬严格的网站可能无法读取。
- Tavily 和内部知识库均可独立降级，但缺少检索来源时报告的证据完整性会下降。
