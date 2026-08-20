# Word 文档导入方案：LibreOffice 转 PDF 后复用 MinerU

## 1. 目标与范围

当前导入链路只支持 Markdown 和 PDF。本方案新增 `.docx`、`.doc` 两种输入格式，并统一采用以下处理路径：

```text
DOC/DOCX
  -> LibreOffice 无界面转换为 PDF
  -> 现有 MinerU PDF 解析
  -> Markdown 图片处理
  -> 文档 metadata 抽取
  -> Markdown 切分
  -> BGE-M3 Embedding
  -> Milvus 入库
```

本方案只新增 Word 输入标准化能力，不改变现有 Markdown、MinerU、切分、Embedding 和 Milvus 的业务规则。

采用该路线的原因：

1. `.doc` 是旧版二进制格式，不能直接复用普通 DOCX 解析库；LibreOffice 可以统一读取 DOC 和 DOCX。
2. 现有项目已经具备 PDF -> MinerU -> Markdown 的完整链路，Word 转 PDF 后可以最大限度复用已有能力。
3. PDF 能固定 Word 的分页和视觉布局，适合 MinerU 继续识别标题、表格、图片和页面结构。
4. 不需要维护 DOC、DOCX 两套正文、图片和表格解析逻辑。

本次方案不支持：

- `.docm`、`.dot`、`.dotx` 等宏或模板格式；
- 密码保护或加密的 Word 文档；
- 依赖外部链接才能完整显示内容的文档；
- 保证 Microsoft Word 与 LibreOffice 的排版结果完全一致。

---

## 2. 当前链路与目标链路

### 2.1 当前链路

```text
上传文件
  -> node_entry
      -> MD：node_md_img
      -> PDF：node_pdf_to_md
  -> node_document_metadata
  -> node_document_split
  -> node_bge_embedding
  -> node_import_milvus
```

当前限制点：

- `entry_service.py` 只识别 `.md`、`.pdf`；
- `main_graph.py` 只有 MD、PDF 两个路由；
- `ImportGraphState` 只有 MD、PDF 路径及开关；
- 上传页面的 `accept` 只包含 `.pdf,.md`；
- 上传接口没有在启动后台任务前拒绝不支持的文件；
- 不支持的类型可能只结束图，随后被后台任务标记为完成，存在“假成功”风险。

### 2.2 目标链路

```text
上传文件
  -> 上传层格式和安全校验
  -> node_entry
      -> MD：node_md_img
      -> PDF：node_pdf_to_md
      -> DOC/DOCX：node_word_to_pdf -> node_pdf_to_md
  -> node_document_metadata
  -> node_document_split
  -> node_bge_embedding
  -> node_import_milvus
```

核心约束：

- `node_word_to_pdf` 只负责把 Word 转成可用 PDF；
- Word 转换节点不调用 MinerU、不抽取 metadata、不切分、不入库；
- 转换成功后设置 `pdf_path` 指向生成的 PDF；
- `local_file_path` 始终保留原始 DOC/DOCX 路径，用于追溯和稳定 `document_id`；
- `file_title` 始终使用原 Word 文件名的 stem，不使用中间 PDF 文件重新推导；
- Word、原生 PDF 从 `node_pdf_to_md` 开始完全使用同一条链路。

---

## 3. LibreOffice 技术选择

### 3.1 使用方式

使用 LibreOffice Writer 的命令行转换能力，不通过桌面 GUI，也不使用 Microsoft Office COM。

标准命令形态：

```text
soffice
  --headless
  --nologo
  --nodefault
  --norestore
  -env:UserInstallation=file:///任务独立profile目录
  --convert-to pdf:writer_pdf_Export
  --outdir 任务独立输出目录
  输入文件路径
```

Linux 示例：

```bash
/usr/bin/soffice \
  --headless \
  --nologo \
  --nodefault \
  --norestore \
  -env:UserInstallation=file:///data/output/20260818/task-id/libreoffice-profile \
  --convert-to pdf:writer_pdf_Export \
  --outdir /data/output/20260818/task-id/converted \
  /data/output/20260818/task-id/source.docx
```

Windows PowerShell 示例：

```powershell
& "C:\Program Files\LibreOffice\program\soffice.com" `
  --headless `
  --nologo `
  --nodefault `
  --norestore `
  "-env:UserInstallation=file:///E:/project/rewater-agent/data/output/20260818/task-id/libreoffice-profile" `
  --convert-to "pdf:writer_pdf_Export" `
  --outdir "E:\project\rewater-agent\data\output\20260818\task-id\converted" `
  "E:\project\rewater-agent\data\output\20260818\task-id\source.docx"
```

实现时必须使用参数列表调用子进程，不能把用户文件名拼接成 shell 字符串执行。

### 3.2 关键参数说明

| 参数 | 作用 |
| --- | --- |
| `--headless` | 不启动图形界面，适合服务器和容器运行 |
| `--nologo` | 不显示启动画面 |
| `--nodefault` | 不打开默认起始窗口 |
| `--norestore` | 禁止崩溃恢复交互，避免后台任务等待 UI |
| `-env:UserInstallation=...` | 为当前任务指定独立且可写的 LibreOffice profile |
| `--convert-to pdf:writer_pdf_Export` | 明确使用 Writer PDF 导出过滤器 |
| `--outdir` | 将输出限定在当前任务目录 |

LibreOffice 官方说明 `--headless` 可在无界面环境运行，`--convert-to` 支持指定输出格式和输出目录；LibreOffice 同时要求其用户 profile 目录可写。

参考资料：

- [LibreOffice 官方启动参数](https://help.libreoffice.org/latest/en-US/text/shared/guide/start_parameters.html)
- [LibreOffice 官方文件转换过滤器](https://help.libreoffice.org/latest/en-US/text/shared/guide/convertfilters.html)

---

## 4. LibreOffice 部署方案

### 4.1 推荐部署位置

推荐把 LibreOffice 安装在“导入服务”所在主机或容器内，不安装到 MinerU 服务中。

原因：

- Word 转 PDF 属于导入服务的输入标准化职责；
- MinerU 继续只接收 PDF，不需要感知原文件是 Word；
- 任务目录、原文件和转换后 PDF 都在导入服务本地，便于校验和排错；
- 当前预期并发较低，同容器/同主机部署比单独建设转换微服务更简单。

未来只有在 Word 转换量明显增加、LibreOffice 资源占用影响 API 稳定性时，再拆为独立转换 worker。当前阶段不需要提前引入消息队列或独立微服务。

### 4.2 Windows 开发环境

安装步骤：

1. 从 LibreOffice 官方渠道安装稳定版本。
2. 默认安装目录通常为：

   ```text
   C:\Program Files\LibreOffice\program
   ```

3. 配置项目使用完整可执行文件路径：

   ```text
   C:\Program Files\LibreOffice\program\soffice.com
   ```

4. 启动应用前执行版本检查：

   ```powershell
   & "C:\Program Files\LibreOffice\program\soffice.com" --version
   ```

5. 使用一份中文 DOCX 和一份旧版 DOC 执行转换冒烟测试。
6. 检查输出 PDF 是否存在、非空、可打开且中文字体正常。

开发环境建议显式配置可执行文件路径，不依赖系统 `PATH`。这样可以避免开发机上存在多个 LibreOffice 版本时调用到错误版本。

### 4.3 Linux 云主机

以 Debian/Ubuntu 系统为例，需要安装 Writer、基础组件及中文字体：

```bash
apt-get update
apt-get install -y --no-install-recommends \
  libreoffice-writer \
  libreoffice-core \
  libreoffice-common \
  fonts-noto-cjk \
  fonts-liberation
rm -rf /var/lib/apt/lists/*
```

安装后检查：

```bash
command -v soffice
soffice --version
fc-list :lang=zh | head
```

注意事项：

- 具体包名以部署发行版的软件仓库为准；镜像和发行版确定后应固定版本，不在不同环境随意使用不同仓库。
- `fonts-noto-cjk` 用于常见中日韩字符；缺少中文字体时，PDF 可能出现乱码、方框、换行和分页变化。
- 如果业务文件依赖宋体、仿宋、黑体等特定字体，需要确认字体授权后，以只读方式挂载或安装相应字体。
- 字体变化会改变分页、表格宽度和 MinerU 的解析结果，因此字体集合属于部署基线的一部分。

### 4.4 Docker 部署

推荐以项目现有 Python 运行镜像为基础，在导入服务镜像中安装 LibreOffice Writer 和字体。示意方案：

```dockerfile
FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libreoffice-writer \
       libreoffice-core \
       libreoffice-common \
       fonts-noto-cjk \
       fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

ENV LIBREOFFICE_EXECUTABLE=/usr/bin/soffice
```

该片段只用于说明部署依赖，正式 Dockerfile 仍需合并项目自身的 Python 依赖安装、运行用户、数据卷和启动命令。

容器要求：

1. 使用非 root 用户运行导入服务和 LibreOffice。
2. 当前任务目录、输出目录和 profile 目录必须可写。
3. 应用代码、系统目录尽量只读。
4. 原始 Word、转换 PDF 和 MinerU 结果统一写到任务数据卷。
5. 不在容器内共享宿主机的 LibreOffice 默认 profile。
6. 容器启动时执行 LibreOffice 版本健康检查。
7. 生产镜像固定基础镜像 digest 或至少固定发行版，不使用浮动系统版本。

建议的数据目录结构：

```text
/data/output/YYYYMMDD/task_id/
├── source/
│   └── 原始文件.docx
├── converted/
│   └── 原始文件.pdf
├── libreoffice-profile/
├── mineru/
│   ├── result.zip
│   ├── extracted/
│   └── 原始文件.md
└── diagnostics/
    └── conversion.json
```

### 4.5 配置项

建议集中增加以下运行配置，名称可在实现时结合现有 `settings` 规范确定：

| 配置 | 建议初始值 | 说明 |
| --- | --- | --- |
| LibreOffice 可执行文件 | Windows/容器分别配置 | 禁止在业务代码散落硬编码路径 |
| 转换超时 | 120 秒 | 超时后终止当前进程树并标记任务失败 |
| 最大 Word 文件大小 | 待确认 | 应与上传接口限制保持一致 |
| 最大转换并发数 | 2 | 低并发初始值，后续通过压测调整 |
| 是否保留转换 PDF | `true` | 初期保留，便于核对 MinerU 输入 |
| 是否保留 LibreOffice profile | `false` | 成功或失败后清理临时 profile |
| PDF 导出过滤器 | `writer_pdf_Export` | 固定 Writer PDF 导出行为 |

不建议自动扫描整台主机寻找 `soffice`。启动时按配置路径校验，找不到就让导入服务健康检查失败，并输出明确部署错误。

---

## 5. Word 转 PDF 服务设计

### 5.1 服务职责

建议在 `app/rag/import_/` 下新增独立的 Word 转换 service，由 LangGraph 节点调用。

该 service 只负责：

1. 校验输入文件；
2. 创建任务级转换目录和 LibreOffice profile；
3. 调用 LibreOffice；
4. 校验输出 PDF；
5. 更新状态中的 PDF 路径；
6. 记录转换诊断信息。

它不负责：

- 上传文件；
- 调用 MinerU；
- 读取 PDF 正文；
- 文档 metadata 抽取；
- Markdown 切分；
- Embedding 或 Milvus 写入。

### 5.2 输入状态

转换前需要以下字段：

| 字段 | 说明 |
| --- | --- |
| `task_id` | 任务唯一标识 |
| `local_dir` | 当前任务独立目录 |
| `local_file_path` | 原始 DOC/DOCX 路径 |
| `file_title` | 原 Word 文件名 stem |
| `source_format` | `doc` 或 `docx` |

建议新增或明确以下状态字段：

| 字段 | 说明 |
| --- | --- |
| `source_format` | 原始文件格式：`md/pdf/doc/docx` |
| `source_file_path` | 原始上传文件路径；也可继续使用 `local_file_path` |
| `converted_pdf_path` | LibreOffice 生成的 PDF 路径 |
| `pdf_path` | 交给现有 MinerU 节点的实际 PDF 路径 |

不要将 `local_file_path` 改成中间 PDF 路径，否则会影响原文件追溯和基于源文件名生成稳定 `document_id` 的逻辑。

### 5.3 转换步骤

1. 从 state 取得 `local_file_path`、`local_dir`、`task_id`。
2. 校验原文件存在、是普通文件且后缀为 `.doc` 或 `.docx`。
3. 使用文件签名辅助校验，避免把任意文件仅改后缀后送入 LibreOffice。
4. 校验文件大小、空文件、密码保护等可提前识别的问题。
5. 在当前任务目录下创建独立的 `converted` 和 `libreoffice-profile` 目录。
6. 把 profile 目录转换成合法的 `file://` URI；Windows 不能直接把反斜杠路径拼入 URI。
7. 使用参数数组启动 LibreOffice 子进程，禁止 `shell=True`。
8. 捕获标准输出、标准错误、退出码和耗时，但不记录文件正文。
9. 超过配置时间后终止整个 LibreOffice 进程树，任务标记失败。
10. LibreOffice 退出后不能只检查退出码，还必须检查预期 PDF 是否真实生成。
11. 校验 PDF 非空、文件头以 `%PDF-` 开始，必要时读取页数确认至少一页。
12. 将生成路径写入 `converted_pdf_path` 和 `pdf_path`。
13. 保持 `local_file_path`、`file_title` 不变。
14. 返回 state 增量，交给现有 `node_pdf_to_md`。

### 5.4 输出文件定位

LibreOffice 通常使用输入文件 stem 生成 PDF，但业务逻辑不能只依赖标准输出中的提示文本。

建议规则：

1. 转换前保证 `converted` 目录为空或为本任务新建目录。
2. 预期路径为 `converted/<安全文件名stem>.pdf`。
3. 转换后枚举该目录中的普通 PDF 文件。
4. 必须恰好找到一个符合预期的输出文件。
5. 找不到或存在多个无法确定的 PDF 时明确失败，不能随便选择第一个。

原始中文标题保存在 `file_title`；如担心特殊字符影响 LibreOffice，可在任务目录内创建安全的临时输入文件名，但不得改变业务标题和原文件记录。

### 5.5 成功判断

以下条件必须同时满足才算转换成功：

- 子进程在超时前退出；
- 退出码为 0；
- 输出目录中存在唯一预期 PDF；
- PDF 文件大小大于最低阈值；
- 文件签名为 PDF；
- PDF 至少包含一页；
- 后续 MinerU 能正常接受该 PDF。

如果 LibreOffice 退出码为 0 但没有生成 PDF，仍然必须判定失败。

---

## 6. LangGraph 调整方案

### 6.1 入口识别

入口支持四种后缀，不区分大小写：

```text
.md
.pdf
.doc
.docx
```

推荐使用单一 `source_format` 路由，而不是继续累加多个布尔开关：

```text
md   -> node_md_img
pdf  -> node_pdf_to_md
doc  -> node_word_to_pdf
docx -> node_word_to_pdf
其他 -> 显式失败
```

如果为了控制本次改动范围暂时保留现有布尔开关，也应增加明确的 Word 路由标识，并计划后续收敛为枚举。任何格式都不应同时命中两条路由。

### 6.2 Word 节点

新增 `node_word_to_pdf`，其节点职责为：

1. 将任务状态登记为运行中；
2. 调用 Word 转 PDF service；
3. 成功后确认 `pdf_path` 非空；
4. 将节点登记为完成；
5. 返回状态增量。

图连接关系：

```text
node_entry
  -> node_word_to_pdf
  -> node_pdf_to_md
  -> node_md_img
```

Word 转换失败时直接抛出异常，由后台任务统一设置 `failed`，不得跳到 `END` 后被标记为完成。

### 6.3 与现有 MinerU 的衔接

转换节点完成后：

- `pdf_path` 指向 LibreOffice 生成的 PDF；
- `local_dir` 仍是当前任务目录；
- `file_title` 仍是原 Word 标题；
- `parse_pdf_to_markdown` 不需要区分原生 PDF 和 Word 转换 PDF；
- MinerU 输出 Markdown 后继续写入现有 `md_path/md_content`。

建议日志明确记录：

```text
source_format=docx
source_file=原始文件.docx
converted_pdf=converted/原始文件.pdf
parser_chain=libreoffice->mineru
```

这些属于运行诊断信息，不要求新增到当前 Milvus schema。

---

## 7. 上传接口和前端调整

### 7.1 上传接口

上传层必须在保存文件和创建后台任务前完成：

1. 后缀白名单校验；
2. 安全文件名处理，禁止绝对路径和 `..`；
3. 文件大小限制；
4. 文件签名与后缀基本一致性检查；
5. 空文件检查；
6. 单次上传文件数量限制。

不支持的类型直接返回 4xx，不创建任务目录，也不进入 LangGraph。

### 7.2 前端

文件选择框调整为：

```html
accept=".pdf,.md,.doc,.docx"
```

页面提示至少包含：

- 支持 PDF、Markdown、DOC、DOCX；
- Word 文件会先转换为 PDF；
- 不支持密码保护和宏文档；
- 复杂排版可能与 Microsoft Word 显示存在差异；
- 文件大小限制。

---

## 8. 并发、隔离与资源控制

### 8.1 独立 LibreOffice profile

每个转换任务必须使用独立 `UserInstallation` 目录，不能共享系统用户的默认 LibreOffice profile。

原因：

- LibreOffice profile 存在锁和运行状态；
- 多个后台任务共享 profile 可能互相等待或错误复用已有进程；
- 容器通常没有初始化过桌面用户 profile；
- 独立目录便于任务结束后清理。

### 8.2 并发限制

FastAPI `BackgroundTasks` 不等于资源隔离。多个大 Word 同时转换会竞争 CPU、内存和磁盘。

当前低并发场景建议：

- Word 转换设置进程内信号量；
- 初始最大并发数为 2；
- MinerU 上传可继续使用现有流程；
- 压测后再调整并发，不直接等于 API 并发数。

多实例部署时，每个实例的并发上限会叠加，需要结合容器资源限制计算总转换并发。

### 8.3 超时与进程清理

- 每次转换设置硬超时；
- 超时后终止当前 LibreOffice 进程及其子进程；
- 删除该任务未完成的输出 PDF；
- 清理任务独立 profile；
- 不使用全局进程名批量终止 LibreOffice，以免杀死其他任务或管理员进程；
- 进程无法终止时记录高优先级错误并让任务失败。

---

## 9. 安全方案

1. 只接收 `.doc`、`.docx`，不接收 `.docm`。
2. LibreOffice 进程使用低权限、非 root 用户。
3. 转换目录限制在当前 `task_id` 目录内。
4. 不将用户文件名直接拼接进 shell 命令。
5. 不允许 Word 文档指定输出路径。
6. 转换容器原则上不需要主动访问公网；如果部署条件允许，应限制其网络权限。
7. 不挂载宿主机用户目录和办公文档目录。
8. 限制上传大小、转换时间、输出大小和并发数，防止资源耗尽。
9. 对 DOCX 的 ZIP 结构设置解压大小和文件数量上限；即使不自行解压，也应把异常包作为高风险输入。
10. 转换产生的外部链接、宏、嵌入对象不作为可信内容执行。
11. MinerU 解析结果 ZIP 仍需保留现有或补充 Zip Slip、文件数量和解压总大小防护。

LibreOffice 转换不是安全沙箱。生产环境应依靠容器、低权限账户、文件系统边界、资源限制和网络策略共同隔离不可信文档。

---

## 10. 异常分类与任务状态

建议为日志和 API 状态区分以下错误类别：

| 错误 | 处理 |
| --- | --- |
| `unsupported_file_type` | 上传阶段拒绝，不创建后台任务 |
| `invalid_file_signature` | 上传或入口阶段拒绝 |
| `encrypted_document` | 明确提示不支持加密文档 |
| `libreoffice_not_found` | 部署错误，服务健康检查失败 |
| `libreoffice_timeout` | 终止当前进程树，任务失败 |
| `libreoffice_exit_error` | 保存退出码和截断后的 stderr，任务失败 |
| `converted_pdf_missing` | 即使退出码为 0 也判定失败 |
| `converted_pdf_invalid` | 删除无效 PDF，任务失败 |
| `mineru_parse_failed` | 沿用现有 MinerU 异常处理 |
| `empty_markdown` | 解析结果为空，任务失败 |

任务状态原则：

```text
只有 Word 转 PDF、MinerU、Markdown 处理、metadata、切分、Embedding、Milvus
全部成功，任务才能标记为 completed。
```

不支持格式、转换失败和解析为空都不能通过提前 `END` 被视为成功。

---

## 11. 日志和可观测性

每次转换记录：

- `task_id`；
- 原始格式和安全化文件名；
- LibreOffice 版本；
- 转换耗时；
- 退出码；
- 输入和输出文件大小；
- 生成 PDF 页数；
- MinerU 解析耗时；
- 最终 Markdown 长度；
- 失败阶段和错误类别。

禁止记录：

- 文档完整正文；
- 密钥和 MinerU token；
- 未截断的超长 LibreOffice 输出；
- 用户原始绝对路径中的无关系统信息。

建议监控指标：

```text
word_conversion_total
word_conversion_success_total
word_conversion_failure_total{reason}
word_conversion_duration_seconds
word_conversion_active
converted_pdf_size_bytes
```

---

## 12. 测试方案

### 12.1 单元测试

使用 mock 子进程，不依赖真实 LibreOffice：

1. `.doc/.docx` 后缀识别，包含大小写后缀；
2. 不支持格式明确失败；
3. 命令参数使用数组且包含独立 profile、输出目录；
4. 文件名包含空格、中文和括号时参数不被拆分；
5. 退出码非 0 时失败；
6. 退出码为 0 但无 PDF 时失败；
7. 输出多个 PDF 时失败；
8. PDF 为空或文件签名错误时失败；
9. 超时后执行进程树清理；
10. 成功时只更新 `pdf_path/converted_pdf_path`，不覆盖原始文件路径和标题。

### 12.2 LibreOffice 集成测试

在固定 LibreOffice 和字体环境中准备：

- 简单中文 DOCX；
- 旧版 DOC；
- 多级标题；
- 多页正文；
- 图片；
- 普通表格和合并单元格表格；
- 页眉、页脚和页码；
- 中文、英文混排；
- 特殊字体缺失样本；
- 损坏文档；
- 密码保护文档；
- 超大文档；
- 多任务并发样本。

校验：

- PDF 可打开且至少一页；
- 中文无乱码和大面积方框；
- 标题、表格、图片顺序基本正确；
- 不产生目录外文件；
- 并发任务输出和 profile 不互相污染；
- 超时任务不会留下持续运行的进程。

### 12.3 端到端测试

分别上传 MD、PDF、DOC、DOCX，验证：

1. 四种格式均能走到预期路由；
2. DOC/DOCX 生成有效 PDF；
3. 生成 PDF 成功送入 MinerU；
4. `md_content` 非空；
5. 图片处理节点可继续执行；
6. metadata、chunks 和向量字段符合现有契约；
7. Milvus 写入成功；
8. 失败任务状态为 `failed`，并能定位失败阶段。

### 12.4 RAG 回归测试

选择内容相同或接近的 Word/PDF 样本，对比：

- MinerU Markdown 标题结构；
- Markdown 表格完整性；
- chunk 数量和顺序；
- 关键段落是否进入 chunk；
- Dense/Sparse Recall@K；
- Rerank 后关键证据位置；
- 最终回答是否引用到正确内容。

Word 转 PDF 会改变导入数据的版面和部分结构，因此即使 Milvus Schema 和查询代码不变，也必须补充导入及检索回归。

---

## 13. 部署健康检查和发布步骤

### 13.1 启动检查

导入服务启动时检查：

1. LibreOffice 可执行文件存在且可执行；
2. `soffice --version` 能在短时间内成功返回；
3. 任务根目录可写；
4. 可创建并删除测试 profile 目录；
5. 中文字体已安装；
6. MinerU 配置继续有效。

启动检查不需要每次都转换真实文档；部署流水线和发布后冒烟测试再执行实际 Word 转 PDF。

### 13.2 发布顺序

1. 固定部署系统、LibreOffice 版本和字体清单。
2. 在开发环境完成 DOC、DOCX 转换冒烟测试。
3. 增加 Word 转 PDF service 和单元测试。
4. 增加 LangGraph Word 路由。
5. 增加上传白名单和前端格式提示。
6. 在测试环境执行 LibreOffice 集成测试。
7. 执行 DOC/DOCX -> PDF -> MinerU -> Milvus 端到端测试。
8. 执行现有 MD、PDF 回归，确认原链路不受影响。
9. 限制 Word 转换并发，灰度开放 DOCX。
10. 观察失败率、耗时和资源占用后，再开放旧版 DOC。

### 13.3 回滚方式

如果 Word 转换导致服务不稳定：

1. 从上传白名单临时移除 `.doc/.docx`；
2. 保留原有 MD、PDF 路由；
3. 不修改或回滚 Milvus Schema，因为本方案没有新增索引字段；
4. 已成功导入的 Word 文档已经成为普通 chunks，无需删除；
5. 保留失败任务的原文件、日志和转换诊断，用于定位后再恢复功能。

---

## 14. 对现有模块的预计影响

| 模块 | 预计调整 | 说明 |
| --- | --- | --- |
| `app/api/http/import_server.py` | 修改 | 上传前校验 DOC/DOCX，规范错误返回 |
| `app/process/import_/page/import.html` | 修改 | 增加 `.doc,.docx` 和使用说明 |
| `app/rag/import_/entry_service.py` | 修改 | 识别四种格式并显式拒绝其他格式 |
| `app/process/import_/agent/state.py` | 修改 | 增加源格式、转换 PDF 路径等状态字段 |
| `app/process/import_/agent/main_graph.py` | 修改 | 增加 Word 条件路由和节点连接 |
| `app/process/import_/agent/nodes/node_word_to_pdf.py` | 新增 | Word 转 PDF 节点适配层 |
| `app/rag/import_/word_convert_service.py` | 新增 | LibreOffice 调用、超时、校验和诊断 |
| `app/rag/import_/config.py` 或统一 settings | 修改 | 增加可执行路径、超时、并发等配置 |
| 部署文件 | 修改/新增 | 安装 LibreOffice Writer 和中文字体 |
| `pdf_parse_service.py` | 原则上不改 | 继续消费 `pdf_path` |
| `split_service.py` | 不改 | 继续消费 MinerU Markdown |
| `embedding_service.py` | 不改 | chunk 契约不变 |
| `index_service.py` | 不改 | Milvus schema 不变 |
| 查询链路 | 不改 | 检索字段和向量不变 |

---

## 15. 验收标准

- Windows、Linux/Docker 环境均能找到并调用固定版本 LibreOffice。
- DOC、DOCX 都能转换为非空、合法、至少一页的 PDF。
- 每个任务使用独立输出目录和 LibreOffice profile。
- 文件名包含中文、空格和括号时能够正常转换。
- 转换命令不经过 shell 字符串拼接。
- 超时、退出异常、无输出、无效 PDF 都会使任务进入 `failed`。
- `local_file_path` 和 `file_title` 始终指向原始 Word 语义，`pdf_path` 指向中间 PDF。
- Word 生成的 PDF 可以无分支地复用现有 MinerU 节点。
- 现有 MD、PDF 导入行为不发生回归。
- Word 导入后的 metadata、chunk、Embedding 和 Milvus record 与现有契约一致。
- Milvus Schema 和查询链路不因新增 Word 输入发生变化。
- 部署文档包含 LibreOffice、字体、可执行路径、数据目录权限和健康检查说明。

---

## 16. 最终建议

当前阶段采用以下落地策略：

```text
同一导入服务容器安装 LibreOffice Writer 和中文字体
  + DOC/DOCX统一转PDF
  + 每任务独立profile和输出目录
  + 最大转换并发初始设为2
  + 转换超时初始设为120秒
  + 严格校验PDF后再调用MinerU
  + 初期保留中间PDF用于排错
```

先支持 DOCX 灰度验证，再开放旧版 DOC。该方案能以较小的业务改动复用现有 PDF 导入能力，同时把 LibreOffice 的部署、并发和安全风险限制在独立的输入转换环节。
