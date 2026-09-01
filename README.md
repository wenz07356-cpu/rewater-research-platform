# 再生水知识与深度研究平台

面向市政水务资料的知识入库、证据问答与深度研究一体化平台：将分散文档转化为可检索证据，并通过可确认大纲、异步研究任务和确定性渲染生成来源可追溯的报告。

## 平台界面

统一入口为 <http://localhost:8080>，可进入知识库导入、知识问答和深度研究三个工作区。

## 核心能力

- **知识入库**：上传水务资料，完成文档解析、切分、BGE-M3 向量化并写入 Milvus。
- **证据问答**：支持本地知识检索、HyDE、RRF 融合、BGE Reranker、可选联网搜索和 SSE 流式回答。
- **深度研究**：创建研究主题，生成并确认大纲，由 DeepAgents 协调检索与章节研究，Celery 在后台执行长任务。
- **来源追溯**：问答返回文件或网页来源；研究结论通过 `source_id` 关联章节证据和参考来源。
- **统一入口**：Nginx 提供单一页面地址和三组公开 API 前缀，浏览器无需直接访问各服务端口。

## 系统架构

```text
用户浏览器
    |
    v
Nginx Gateway :8080
    |-- /knowledge/import ------> knowledge-import :8000
    |                                 |-- MinerU
    |                                 |-- MongoDB
    |                                 `-- Milvus / MinIO
    |
    |-- /knowledge/chat -------> knowledge-query :8001
    |                                 |-- Milvus / MinIO
    |                                 `-- LLM / 联网搜索
    |
    `-- /research -------------> research-api :8010
                                      |-- MongoDB
                                      `-- Redis --> research-worker
                                                       |-- knowledge-query /retrieval
                                                       `-- LLM / 外部搜索
```

仓库保留两个领域服务：`knowledge-service` 管理资料和证据检索，`research-service` 管理研究项目、异步任务与报告。研究服务只通过内部 `/retrieval` 契约获取知识证据，不直接读取 Milvus，避免将向量库实现细节扩散到研究领域。

> 根 `compose.yaml` 编排网关和五个应用容器。默认连接已有的 MongoDB、Redis、Milvus、MinIO；没有这些服务时，可以叠加 `compose.local-infra.yaml` 在本机启动一套独立的演示基础设施。

## 三条业务流程

### 1. 知识入库

```text
上传 PDF / Markdown
  -> MinerU 文档解析
  -> 内容切分与元数据整理
  -> BGE-M3 向量化
  -> Milvus 索引 + MongoDB 元数据 + MinIO 图片
```

### 2. 证据问答

```text
用户问题
  -> 查询改写与可选 HyDE
  -> Milvus 混合检索 + 可选联网搜索
  -> RRF 融合与 BGE Reranker
  -> LLM 基于证据回答
  -> SSE 输出答案、文件章节或网页来源
```

### 3. 深度研究

```text
创建研究项目
  -> 生成研究简报与大纲
  -> 用户确认或修改大纲
  -> Celery 异步执行章节研究
  -> 内部知识检索 + 公开资料检索
  -> 结构化章节与来源校验
  -> 确定性 HTML 报告渲染
```


## 启动

### 准备条件

- Windows PowerShell 5.1 或更高版本。
- Docker Desktop，并支持 `docker compose`。
- Python 服务镜像和依赖构建所需的网络环境。
- 本地模型目录 `models/bge-m3`、`models/bge-reranker-v2-m3`；也可在 `.env` 中配置其他宿主机路径。
- MongoDB、Redis、Milvus 和 MinIO：可以使用应用容器可访问的已有实例，也可以使用仓库提供的可选本地基础设施编排。
- 执行业务所需的 OpenAI 兼容模型配置；文档解析还需 MinerU，联网研究可选 Tavily。

### 配置并启动

以下两种方式任选一种。已有基础设施适合当前开发环境；本地基础设施适合第一次体验项目的用户。

#### 方式一：连接已有基础设施

在仓库根目录执行：

```powershell
Copy-Item .env.example .env
# 编辑 .env：至少核对外部基础设施地址、本地模型路径和业务所需的 API Key
.\scripts\start.ps1
```

脚本会校验 `.env` 和两个模型目录，构建并启动应用，等待核心服务健康后打印平台地址。PowerShell 禁止执行本地脚本时可使用：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

该方式读取根 `.env` 中的 `MONGO_URL`、`MONGODB_URI`、`REDIS_URL`、`CELERY_BROKER_URL`、`MILVUS_URL` 和 `MINIO_*` 配置。

#### 方式二：启动可选的本地基础设施

本地方式仍需准备 `.env`、BGE 模型和业务所需的 API Key，但不需要预先安装数据库：

```powershell
Copy-Item .env.example .env
# 编辑 .env：填写本地模型路径和业务所需的 API Key；基础设施地址会被叠加文件覆盖
docker compose -f compose.yaml -f compose.local-infra.yaml up -d --build
docker compose -f compose.yaml -f compose.local-infra.yaml ps
```

该命令会额外启动 MongoDB、Redis、MinIO、etcd 和 Milvus。它们只在 Compose 内部网络提供服务，不占用宿主机的数据库端口；本地账号仅用于开发演示，不适合生产环境。

启动后访问：

| 功能 | 地址 |
| --- | --- |
| 平台首页 | <http://localhost:8080/> |
| 知识库导入 | <http://localhost:8080/knowledge/import> |
| 知识问答 | <http://localhost:8080/knowledge/chat> |
| 深度研究 | <http://localhost:8080/research> |

如果修改了 `PLATFORM_PORT`，请将地址中的 `8080` 替换为配置端口。其他系统可直接运行：

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps
```

健康检查和停止命令：

```powershell
.\scripts\check.ps1
.\scripts\stop.ps1
```

`stop.ps1` 只执行 `docker compose down`，不会删除命名卷，也不会影响外部基础设施中的数据。

使用本地基础设施时，检查和停止需要带上相同的两个 Compose 文件：

```powershell
.\scripts\check.ps1
docker compose -f compose.yaml -f compose.local-infra.yaml down
```

普通 `down` 会保留 MongoDB、Redis、MinIO、etcd 和 Milvus 的命名卷。只有确认不再需要本地演示数据时，才执行不可恢复的数据清理：

```powershell
docker compose -f compose.yaml -f compose.local-infra.yaml down -v
```

## 测试与检查

根级运行状态检查：

```powershell
.\scripts\check.ps1
docker compose ps
```

`check.ps1` 会检查首页、三个业务页面、网关 API、三个后端健康状态、Celery Worker，以及应用容器到外部 MongoDB、Redis、Milvus、MinIO 的网络连通性；失败时输出相关服务的最近日志。

knowledge-service 测试：

```powershell
Push-Location .\services\knowledge-service
uv run --with pytest pytest -q
Pop-Location
```

research-service 静态检查和测试：

```powershell
Push-Location .\services\research-service
uv sync --frozen --extra dev
uv run ruff check app tests
uv run pytest -q
uv run python -m compileall -q app tests
Pop-Location
```

## 已知限制与后续计划

### 已知限制

- 当前定位是本机或可信内网演示，没有用户、角色和 OIDC 鉴权。
- `knowledge-import` 的任务状态保存在进程内，服务重启后不会保留处理中任务。
- 知识库管理目前以上传和进度展示为主，尚无完整的文档列表、删除和重建索引功能。
- MongoDB、Redis、Milvus 和 MinIO 可以连接已有实例，也可由 `compose.local-infra.yaml` 在本机启动；完整本地模式占用资源较多，建议为 Docker Desktop 分配至少 8 GB 内存。
- BGE 模型需要提前准备；首次构建镜像和 CPU 推理可能耗时较长。
- 外部 LLM、MinerU 和联网搜索依赖各自服务的可用性、额度和密钥。
- 当前不包含生产级高可用、监控告警、链路追踪、自动扩缩容和 Secret 管理。
- 平台页面已经统一入口和 API 前缀，但视觉名称与顶部导航仍有少量历史文案待统一。

### 后续计划

- 统一三个工作区的导航、视觉名称、错误提示和水务示例文案。
- 补充固定演示资料、可重复演示脚本和明确标注的预生成报告。
- 将导入任务持久化，并补充知识库文档生命周期管理。
- 在生产化阶段加入 OIDC、角色权限、可观测性和更严格的就绪检查。

## 仓库结构

```text
.
|-- compose.yaml                  # 根级应用编排
|-- compose.local-infra.yaml      # 可选的本地数据库和向量存储
|-- deploy/gateway/               # Nginx 配置和平台首页
|-- scripts/                      # 启动、停止和健康检查
|-- services/knowledge-service/   # 知识导入、问答与证据检索
`-- services/research-service/    # 研究 API、Worker 与报告渲染
```
