# import_ 模块优化设计

## 1. 目标与范围

本次优化只梳理导入链路的业务逻辑，不编写实现代码。目标是让文档导入流程形成清晰、稳定的单向数据流：

```text
Markdown 正文
  -> LLM 抽取文档级 metadata
  -> 按 Markdown 标题初切
  -> 长块细切、短块合并，表格和代码块专项处理
  -> 生成 chunk 级字段
  -> 生成稠密/稀疏向量
  -> 校验并写入 Milvus
```

三个 service 的职责边界如下：

- `item_name_service.py`：只负责文档级 metadata 抽取和规范化，不切分、不向量化、不入库。
- `split_service.py`：只负责 Markdown 结构解析、切块和 chunk 级字段生成，不根据文种选择切分规则。
- `index_service.py`：只负责入库数据校验、Milvus 集合准备、幂等写入，不补业务 metadata。

当前导入图顺序可继续保持：

```text
node_md_img
  -> node_document_metadata
  -> node_document_split
  -> node_bge_embedding
  -> node_import_milvus
```

虽然 metadata 节点仍在切分节点之前，但切分逻辑不再依赖 `document_type`。这样既保留现有工作流顺序，又消除“先判断文种才能切分”的耦合。

## 2. 统一字段约定

### 2.1 文档级业务 metadata

由 `item_name_service.py` 调用大模型生成，并下沉到每一个 chunk：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `region_names` | `list[str]` | 文件主体适用或研究地域，只允许“全国”、明确行政区名称或“不限” |
| `document_type` | `str` | 只允许：`政策`、`标准`、`规划`、`技术文件`、`其他` |
| `topics` | `list[str]` | 文档涉及的上位主题，建议 1～5 个 |
| `keywords` | `list[str]` | 可直接用于检索的具体关键词，建议 3～10 个 |

### 2.2 chunk 级业务字段

由 `split_service.py` 根据实际切块结果生成，大模型不负责输出：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `file_title` | `str` | 文件标题，来自导入状态或文件名 stem |
| `section_title` | `str` | chunk 对应的章节标题；合并多个短章节时为标题组合 |
| `content` | `str` | chunk 原始内容 |
| `context_type` | `str` | `text`、`table`、`code`；以后可扩展其他类型 |
| `token_count` | `int` | 最终 `content` 的 token 估算值 |

### 2.3 必要的基础设施字段

这些字段不是展示 metadata，但为幂等导入、排序和向量检索所必需：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `document_id` | `str` | 文档稳定标识，同一来源文件重新导入时保持不变 |
| `chunk_id` | `str` | chunk 稳定主键 |
| `chunk_index` | `int` | chunk 在文档中的顺序，从 0 开始 |
| `dense_vector` | `list[float]` | 稠密向量 |
| `sparse_vector` | `dict[int, float]` | 稀疏向量 |

`embedding_text` 只作为向量化阶段的临时字段，不写入 Milvus。展示标题也不重复存储，查询结果展示时按以下规则即时生成：

```text
section_title 非空且不同于 file_title：file_title / section_title
否则：file_title
```

### 2.4 明确移除的字段

新链路不再抽取、下沉或入库以下字段：

```text
page_start、page_end、region_level、region_codes、document_subtype、
document_number、validity_status、effective_date、source_name、
publish_date、expiry_date、issuing_authority、authors、source_url、
replaces、replaced_by、language、parser_version、ingested_at、
extraction_method、token_count_method
```

旧商品知识库字段也从新的 chunk collection 中移除：

```text
item_name、title、parent_title、part
```

其中 `content_type` 统一重命名为 `context_type`；原 `part` 的排序职责由全局唯一、语义明确的 `chunk_index` 承担。

---

# 第一部分：`app\rag\import_\split_service.py`

## 整体思路

### 1. 核心原理

所有文档统一按 Markdown 标题切分，不再区分政策、标准、规划、论文、报告等类型，也不再使用法规“章/节/条”、标准数字编号或论文固定章节名称作为文种专属规则。

统一切分流程：

1. 加载并清洗 Markdown。
2. 逐行扫描 Markdown，识别 `#`～`######` 标题并维护标题层级路径。
3. 表格和 fenced code block 优先识别，块内内容不参与标题判断。
4. 标题之间的内容形成初始 block。
5. 超长 block 按内容类型精细切分。
6. 过短且兼容的相邻 block 合并。
7. 为最终 chunk 生成 `section_title`、`context_type`、`token_count`、ID 和向量化文本。

### 2. 切分原则

- 标题边界优先于固定长度边界。
- 文种只属于 metadata，不影响切分策略。
- 表格和代码块不能与普通文本合并。
- 标题、表头、代码围栏属于理解上下文，细切后需要按类型适当重复。
- 普通文本优先按段落和句末标点切分，最后才允许字符级硬切。
- 短块合并必须保持原文顺序，不能跨越一级标题，不能把不同 `context_type` 混在一起。
- 最终写入 `content` 的内容必须与 `token_count`、`embedding_text` 使用的正文一致。
- 不再保留页码、条款号、文种专属路径等字段。

### 3. 建议核心参数

初期可沿用现有量级，后续通过检索评测统一调整：

| 参数 | 初始值 | 作用 |
| --- | ---: | --- |
| `CHUNK_SIZE` | 600 字符 | 普通文本细切的目标长度，不是硬上限 |
| `CHUNK_MAX_SIZE` | 1000 字符 | 普通 chunk 的最大长度 |
| `CHUNK_MIN` | 300 字符 | 低于该值时尝试与相邻兼容块合并 |
| `CHUNK_OVERLAP` | 30 字符 | 仅用于连续普通文本的相邻子块 |
| `TABLE_MAX_SIZE` | 1000 字符 | 表格子块最大长度 |
| `CODE_MAX_SIZE` | 1000 字符 | 代码子块目标上限 |

参数约束：

```text
0 <= CHUNK_OVERLAP < CHUNK_MIN <= CHUNK_SIZE <= CHUNK_MAX_SIZE
```

字符长度用于决定切分边界，`token_count` 用于记录和监控。当前阶段不混用不同模型 tokenizer，避免切分结果随模型切换而变化。

### 4. 中间 block 结构

初切和细切阶段使用内部结构，不直接入库：

```python
{
    "content": str,
    "context_type": "text" | "table" | "code",
    "section_path": list[str],
    "section_title": str,
    "heading_level": int | None,
    "part_index": int,
}
```

`section_path`、`heading_level` 和 `part_index` 只服务于切分、合并及生成 `section_title`，最终可以不写入 Milvus。

## 函数中文说明

### `def load_markdown_content(state) -> tuple[str, str]`

核心功能：从导入状态获取 Markdown 正文和文件标题，并完成基础校验与换行清洗。

步骤：

1. 从 `state` 获取 `md_content`、`file_title`、`md_path`。
2. `md_content` 为空时，校验 `md_path` 是否为有效文件并按 UTF-8 读取。
3. 最终正文仍为空时抛出 `ValueError`，终止导入。
4. `file_title` 为空时优先使用 `md_path.stem`；路径也不存在时使用“未命名文档”。
5. 将 `\r\n`、`\r` 统一为 `\n`，去除 UTF-8 BOM；不在此处压缩正文空行。
6. 将清洗后的 `md_content` 和 `file_title` 写回 `state`。
7. 返回正文和标题。

输入：

- `state`：导入节点状态。

输出：

- `md_content`：规范化后的 Markdown 正文。
- `file_title`：非空文件标题。

### `def _clean_heading(text) -> str`

核心功能：将 Markdown 标题内容清理成稳定的章节标题。

步骤：

1. 去掉开头的 `#` 和标题末尾可选的闭合 `#`。
2. 清理首尾空白和连续空白。
3. 去掉仅用于锚点的 HTML 标签，但保留可见文本。
4. 清理结果为空时返回“未命名章节”。

输入：`text`，原始标题行或标题正文。

输出：清洗后的标题字符串。

### `def _set_section_path(path, level, title) -> list[str]`

核心功能：依据 Markdown 标题层级更新当前章节路径。

步骤：

1. 将标题级别限制在 1～6。
2. 保留当前路径中级别更高的父标题。
3. 用新标题替换当前层级及其子层级。
4. 遇到层级跳跃时不虚构缺失标题。
5. 返回新列表，不原地修改传入的 `path`。

输入：当前标题路径、标题级别、标题文本。

输出：更新后的标题路径。

### `def _is_markdown_table(lines, index) -> bool`

核心功能：判断当前行是否为 Markdown 表格的表头行。

步骤：

1. 校验当前行和下一行均存在。
2. 当前行必须包含列分隔符 `|`。
3. 下一行必须符合 Markdown 表格分隔行语法。
4. 只返回判断结果，不消费行。

输入：全文行列表和当前索引。

输出：是否为 Markdown 表格起点。

### `def _consume_markdown_table(lines, index) -> tuple[list[str], int]`

核心功能：完整读取一个连续的 Markdown 表格。

步骤：

1. 收集表头行和分隔行。
2. 按顺序收集后续非空表格行。
3. 遇到空行、非表格行或文档结束时停止。
4. 返回表格原始行和下一待处理索引。

输入：全文行列表、表头索引。

输出：表格行列表、表格结束后的索引。

### `def _consume_html_table(lines, index) -> tuple[list[str], int]`

核心功能：完整读取 `<table>` 到 `</table>` 的 HTML 表格块。

步骤：

1. 从包含 `<table` 的当前行开始收集。
2. 不区分大小写查找闭合标签 `</table>`。
3. 遇到闭合标签或文档结束时停止。
4. 未找到闭合标签时保留已读取内容，同时记录 warning，避免丢文。

输入：全文行列表、HTML 表格起始索引。

输出：HTML 表格行列表、下一待处理索引。

### `def _consume_fenced_code(lines, index) -> tuple[list[str], int]`

核心功能：完整读取由三个反引号或三个波浪号包围的代码块。

步骤：

1. 记录起始围栏类型及可选语言标记。
2. 收集代码块内所有原始行，块内的 `#`、`|`、`<table>` 均不做结构识别。
3. 读取到同类型闭合围栏后结束。
4. 未闭合时读取到文档末尾并记录 warning。
5. 返回包含起止围栏的原始代码和下一索引。

输入：全文行列表、代码围栏起始索引。

输出：代码块行列表、下一待处理索引。

### `def _parse_markdown_blocks(md_content, file_title) -> list[dict]`

核心功能：仅依据通用 Markdown 结构，将正文解析为按原文顺序排列的初始 blocks。

步骤：

1. 将正文拆成行并初始化 `section_path=[]`、`section_title=file_title`。
2. 逐行扫描，识别优先级为：fenced code、HTML/Markdown 表格、Markdown 标题、普通文本。
3. 遇到标题时先落盘前一个文本 block，再更新标题路径。
4. 标题行保留在后续文本 block 的 `content` 中，使 chunk 脱离 metadata 后仍可理解。
5. 表格标题若紧邻表格且符合“表/Tab./Table”形式，将其并入表格内容并作为该 block 的 `section_title`。
6. 代码块独立生成 `context_type=code` 的 block。
7. 表格独立生成 `context_type=table` 的 block。
8. 其他内容生成 `context_type=text` 的 block。
9. 跳过纯空 block；全文没有标题时使用 `file_title` 作为 `section_title`。

输入：规范化后的 Markdown 正文、文件标题。

输出：初始结构 block 列表。

### `def split_by_titles(md_content, file_title) -> list[dict]`

核心功能：提供“按标题初切”的公开入口。

步骤：

1. 校验 `md_content` 和 `file_title`。
2. 调用 `_parse_markdown_blocks`。
3. 保证输出顺序与原文一致。
4. 不接收 `document_type`，不调用任何文种判断逻辑。

输入：Markdown 正文、文件标题。

输出：尚未执行长度细化的结构 block 列表。

### `def _split_oversized_unit(text, target_size) -> list[str]`

核心功能：把超长段落拆成可继续组合的小语义单元。

步骤：

1. 长度不超过 `target_size` 时原样返回。
2. 优先按空行和换行拆段。
3. 段落仍过长时按中文、英文句末标点切句。
4. 单句仍过长时再按字符窗口硬切。
5. 去掉空单元，保持原始顺序。

输入：连续文本、目标字符长度。

输出：较小文本单元列表。

### `def _split_text_block(block, target_size, max_size, overlap) -> list[dict]`

核心功能：对超长普通文本 block 做段落和句子级细切。

步骤：

1. 未超过 `max_size` 时原样返回。
2. 使用 `_split_oversized_unit` 生成语义单元。
3. 按顺序把单元组合到接近 `target_size`。
4. 后续子块可携带前块尾部 `overlap`，但不能只由重叠文本构成。
5. 每个子块保留原 `section_title` 和 `section_path`。
6. 若标题行只出现在第一个子块，后续子块补充同一标题行。
7. 任何结果超过 `max_size` 时继续切分，不能用 `piece[:max_size]` 静默截断正文。
8. 为同一 block 的子块设置递增 `part_index`。

输入：文本 block、目标长度、最大长度、重叠长度。

输出：细切后的文本 blocks。

### `def _split_table_block(block, max_size) -> list[dict]`

核心功能：在不破坏表格列语义的前提下拆分大型表格。

步骤：

1. 未超过上限时保持表格为一个 block。
2. Markdown 表格按数据行切分，每个子表重复表名、表头和分隔行。
3. 单行超过上限时保留完整行并记录 warning，不截断单元格。
4. HTML 表格优先按 `<tr>` 行切分，每个子块重复 `<table>`、表头区域和闭合标签。
5. 无法可靠识别行结构时保持原块，交由入库长度校验显式报错，不能把 HTML 字符串硬切坏。
6. 子块保持 `context_type=table` 并设置递增 `part_index`。

输入：表格 block、最大字符长度。

输出：一个或多个可独立理解的表格 blocks。

### `def _split_code_block(block, max_size) -> list[dict]`

核心功能：保护代码语法边界，并处理极长代码块。

步骤：

1. 未超过上限时原样返回。
2. 提取起始围栏、语言标记、代码正文和闭合围栏。
3. 优先按完整代码行组合子块，不在行中间截断。
4. 每个子块重复起始和闭合围栏。
5. 单行本身超过上限时允许独立成块并记录 warning。
6. 代码块之间不使用 overlap。
7. 子块保持 `context_type=code` 并设置递增 `part_index`。

输入：代码 block、最大字符长度。

输出：一个或多个语法闭合的代码 blocks。

### `def _merge_short_blocks(blocks, min_size, max_size) -> list[dict]`

核心功能：合并过短的相邻内容，减少缺乏上下文的小 chunk。

步骤：

1. 按原文顺序遍历细切后的 blocks。
2. 只处理 `context_type=text`，表格和代码块永不参与合并。
3. 优先合并同一 `section_title` 的连续子块。
4. 仍然过短时，可合并同一父标题下的相邻短章节；禁止跨一级标题。
5. 合并后长度不得超过 `max_size`。
6. 合并不同短章节时，保留各自 Markdown 标题行，并将去重后的标题按 `；` 连接为新的 `section_title`。
7. 任一块已经达到 `min_size` 时不为了凑满目标长度强行跨章节合并。
8. 返回新列表，不改变原始 blocks 的相对顺序。

输入：细切后的 blocks、短块阈值、最大长度。

输出：完成安全合并的 blocks。

### `def refine_chunks(sections, max_len=CHUNK_MAX_SIZE, min_len=CHUNK_MIN) -> list[dict]`

核心功能：统一调度不同 `context_type` 的精细切分和短块合并。

步骤：

1. `text` 调用 `_split_text_block`。
2. `table` 调用 `_split_table_block`。
3. `code` 调用 `_split_code_block`。
4. 未知类型按普通文本处理并记录 warning。
5. 汇总细切结果后调用 `_merge_short_blocks`。
6. 校验结果非空且顺序未改变。

输入：标题初切结果、最大长度、最小长度。

输出：待定稿的 blocks。

### `def estimate_token_count(text) -> int`

核心功能：轻量估算中英文混合内容的 token 数量。

步骤：

1. 每个汉字计一个 token。
2. 连续英文或数字串计一个 token。
3. 非空白标点或符号计一个 token。
4. 返回非负整数。

输入：最终 chunk 正文。

输出：启发式 token 数量。

说明：该值用于统计和容量监控，不宣称与 BGE 模型 tokenizer 完全一致，因此无需再存 `token_count_method`。

### `def _build_embedding_text(chunk, metadata, file_title) -> str`

核心功能：构造只供向量化使用的上下文增强文本。

步骤：

1. 按顺序加入 `file_title`、`section_title`、`document_type`。
2. 加入去重后的 `region_names`、`topics`、`keywords`。
3. 最后加入原始 `content`。
4. 空字段不生成空行，列表字段用中文顿号连接。
5. 不把字段名、JSON 或向量写入正文。

输入：chunk block、文档 metadata、文件标题。

输出：向量化临时文本 `embedding_text`。

### `def _build_chunk_id(document_id, chunk_index) -> str`

核心功能：为 chunk 生成可重复计算的稳定主键。

步骤：

1. 校验 `document_id` 非空、`chunk_index` 非负。
2. 拼接 `document_id|chunk_index`。
3. 使用 SHA-256 生成固定长度十六进制字符串。
4. 不把正文加入 ID，保证同一文档同一序号在内容更新后可执行 upsert。

输入：文档 ID、chunk 顺序。

输出：稳定 `chunk_id`。

### `def _finalize_chunks(blocks, metadata, file_title) -> list[dict]`

核心功能：把内部 blocks 转换成供向量化和索引使用的最终 chunks。

步骤：

1. 跳过纯空内容，重新连续编号 `chunk_index`。
2. 从 block 读取 `section_title`、`context_type`、`content`。
3. 写入文档级 `region_names`、`document_type`、`topics`、`keywords`。
4. 写入 `file_title`、`document_id`。
5. 计算 `token_count` 和稳定 `chunk_id`。
6. 生成临时 `embedding_text`。
7. 不写入旧字段和已明确移除的字段。
8. 最终校验每个 chunk 的必需字段非空。

输入：完成细化的 blocks、文档 metadata、文件标题。

输出：最终 chunk 字典列表。

### `def backup_chunks(chunks, md_path) -> None`

核心功能：按需保存切分诊断文件，便于人工检查切分效果。

步骤：

1. `md_path` 为空时跳过。
2. 输出文件使用源 Markdown 同目录、同 stem 的 `.chunks.json`，避免与其他 JSON 结果混淆。
3. 使用 UTF-8、`ensure_ascii=False` 和缩进格式写入。
4. 备份失败记录 warning；是否中断导入由配置项决定，默认不中断主流程。

输入：最终 chunks、Markdown 路径。

输出：无返回值；可能生成诊断 JSON 文件。

### `def split_document(state) -> dict`

核心功能：串联 `split_service.py` 的完整处理流程并更新导入状态。

步骤：

1. 调用 `load_markdown_content`。
2. 校验 `state.document_metadata` 是否存在；正常导入图已在上游完成抽取，直接调用本 service 且 metadata 缺失时记录 warning 并兼容调用 LLM 抽取。
3. 调用 `split_by_titles` 完成通用 Markdown 标题初切。
4. 调用 `refine_chunks` 处理长块、短块、表格和代码。
5. 调用 `_finalize_chunks` 生成最终字段。
6. 结果为空时抛出 `ValueError`。
7. 按配置调用 `backup_chunks`。
8. 将结果写入 `state["chunks"]`，记录总数及各 `context_type` 数量。
9. 返回更新后的 `state`。

输入：包含 Markdown 正文/路径、标题和文档 metadata 的导入状态。

输出：写入 `chunks` 后的导入状态。

---

# 第二部分：`app\rag\import_\item_name_service.py`

## 整体思路

### 1. 核心职责

该文件名暂时保留以兼容现有导入图，但模块职责应明确改为“文档 metadata 抽取服务”。不再执行商品名称识别，也不再使用本地关键词规则先分类、LLM 再补充的双轨方案。

新的处理逻辑：

1. 从状态中取得文件标题和 Markdown 正文。
2. 为长文档构造能覆盖全文结构的 metadata 上下文。
3. 直接调用大模型，以 JSON 模式一次抽取四个文档级字段。
4. 严格做字段白名单、类型、枚举、数量和地域语义校验。
5. 校验失败时携带错误原因重试一次；再次失败则终止本次导入，不降级到旧规则结果。
6. 生成基础设施字段 `document_id`，写回状态。

### 2. LLM 输出结构

```json
{
  "region_names": ["深圳市"],
  "document_type": "技术文件",
  "topics": ["再生水厂用地", "工程设计"],
  "keywords": ["再生水厂", "用地指标", "平面布局"]
}
```

`file_title` 不需要模型返回；它来自导入输入。`section_title`、`context_type`、`token_count` 属于 chunk 级字段，不能让模型对整篇文档统一生成。

### 3. `region_names` 判定规则

`region_names` 表示文件主体地域，不是正文中出现过的所有地名。

- 全国性政策、国家标准或明确适用于全国的文件：`["全国"]`。
- 明确适用于某省、市、区的政策、标准、规划：填写完整行政区名称，例如 `["北京市"]`、`["广东省"]`、`["深圳市"]`、`["南山区"]`。
- 论文、研究报告、技术文件主要分析某个地方：填写研究对象所在地。例如正文主体是深圳再生水厂用地分析，则为 `["深圳市"]`。
- 文件同时、平等地研究多个明确地域时可以返回多个名称，但不能因为参考案例、发布机构地址、引用标准或背景描述而加入地名。
- 主体地域无法明确判断：`["不限"]`。
- `全国`、`不限` 均为互斥值，不能与其他地域同时出现。
- 地名优先使用带行政区后缀的规范中文名；模型输出“深圳”时规范化为“深圳市”，无法可靠补全时保留原词并触发校验重试，不能凭空推断。

### 4. `document_type` 判定规则

只允许以下中文值：

| 值 | 判定范围 |
| --- | --- |
| `政策` | 法律法规、条例、办法、规定、通知、意见、决定及行政管理文件 |
| `标准` | 国家、行业、地方、团体标准以及具备明确标准属性的规范、规程、导则 |
| `规划` | 总体规划、专项规划、行动规划、实施规划及以发展目标和任务安排为主体的文件 |
| `技术文件` | 论文、研究/评估/可研报告、设计文件、技术指南、技术手册、工程分析等 |
| `其他` | 无法归入以上四类的材料 |

分类以文件的主体功能为准，而不是只看某个关键词。例如论文引用政策不应分类为政策，政策附件引用标准不应分类为标准。

### 5. `topics` 与 `keywords`

- `topics` 是相对上位的知识主题，建议 1～5 个，例如“再生水利用”“水质要求”“工程设计”“运行管理”。
- `keywords` 是更具体的检索词，建议 3～10 个，例如“膜处理”“单位水量建设用地”“景观环境用水”。
- 两者均去重、去空值、去无意义泛词。
- 不强制使用固定主题词表，但 prompt 可提供再生水领域示例以提高一致性。
- 文档证据不足时允许返回空列表，不能为了满足数量建议编造词语。

### 6. 建议核心参数

| 参数 | 初始值 | 作用 |
| --- | ---: | --- |
| `METADATA_CONTEXT_MAX_CHARS` | 10000 | 发送给模型的正文前缀上限 |
| `METADATA_LLM_RETRY` | 1 | 结构或语义校验失败后的重试次数 |
| `TOPICS_MAX_COUNT` | 5 | topics 最大数量 |
| `KEYWORDS_MAX_COUNT` | 10 | keywords 最大数量 |
| `REGION_NAMES_MAX_COUNT` | 8 | 多地域文档最大地域数量 |

metadata 上下文采用简单、稳定的前缀策略：文件标题通过 prompt 独立传入，正文只取规范化后的前 10000 个字符，不再提取标题目录，也不再对正文中部和结尾进行采样。

## 函数中文说明

### `def _unique_strings(values, max_count) -> list[str]`

核心功能：将模型输出规范为有序、去重、非空的字符串列表。

步骤：

1. 非列表输入视为校验错误，不把普通字符串按字符拆开。
2. 清理每一项首尾空白和连续空格。
3. 丢弃空值和非字符串值。
4. 按首次出现顺序去重。
5. 超过 `max_count` 时截取并记录 warning，供 prompt 调优。

输入：原始值、允许的最大数量。

输出：规范化字符串列表。

### `def _build_metadata_context(content, max_chars=METADATA_CONTEXT_MAX_CHARS) -> str`

核心功能：按固定上限为 metadata 大模型构造简单、可预测的正文前缀。

步骤：

1. 校验正文为非空字符串且 `max_chars` 大于 0。
2. 去除 UTF-8 BOM，并将 `\r\n`、`\r` 统一为 `\n`。
3. 直接返回 `content[:max_chars]`。
4. 正文超过上限时记录 info 日志，日志只包含原长度和截取长度。
5. 文件标题不拼入本函数结果，由 prompt 的 `file_title` 参数独立传入。

输入：完整 Markdown 正文、最大字符数。

输出：最长 10000 字符的正文前缀。

### `def extract_metadata_by_llm(content, file_title) -> dict`

核心功能：直接调用大模型抽取四个文档级业务字段。

步骤：

1. 调用 `_build_metadata_context`。
2. 加载新版 `document_metadata_extraction.prompt`。
3. 在 prompt 中写明字段 JSON schema、中文枚举、地域主体判定规则和禁止猜测要求。
4. 使用模型 JSON mode 或结构化输出能力调用一次。
5. 解析结果必须为 JSON object。
6. 调用 `_normalize_llm_metadata` 做本地严格校验。
7. 校验失败时把错误摘要和原输出加入修正 prompt，重试一次。
8. 重试仍失败时抛出明确的 metadata 抽取异常，不启用关键词规则兜底。

输入：完整正文、文件标题。

输出：规范化后的 `region_names/document_type/topics/keywords`。

### `def _normalize_region_names(values) -> list[str]`

核心功能：校验地域名称的互斥关系和基本格式。

步骤：

1. 调用 `_unique_strings`。
2. 如果包含“全国”，结果必须只能是 `["全国"]`。
3. 如果包含“不限”，结果必须只能是 `["不限"]`。
4. 拒绝“全国、不限”等组合。
5. 明确行政区名称优先保留“省/自治区/市/区/县”等后缀。
6. 不在本地维护 `region_codes`，不根据不完整名称猜测编码或层级。
7. 空列表视为缺少必填判断，触发 LLM 修正；若正文确实不能判断，模型应返回 `["不限"]`。

输入：模型输出的地域列表。

输出：合法的 `region_names`。

### `def _normalize_llm_metadata(raw) -> dict`

核心功能：对白名单字段执行严格的类型和业务规则校验。

步骤：

1. 只读取 `region_names`、`document_type`、`topics`、`keywords`，丢弃并记录所有未知字段。
2. `document_type` 必须命中中文枚举，不能再接受 `policy/standard/plan/report/paper/other`。
3. 调用 `_normalize_region_names`。
4. 使用 `_unique_strings` 规范 topics 和 keywords。
5. 删除 topics 与 keywords 内部重复项；两组间允许语义相关，但避免完全相同项重复保存。
6. 校验单项最大长度，防止模型返回整句或整段。
7. 返回新字典，不修改原始结果。

输入：LLM 原始 JSON 字典。

输出：只包含四个合法业务字段的新字典。

### `def _build_document_id(state, file_title) -> str`

核心功能：生成不依赖模型、同一来源重复导入时稳定的文档标识。

步骤：

1. 优先复用调用方显式提供的合法 `document_id`。
2. 否则优先使用原始上传文件 `local_file_path` 的文件名；没有时使用 `md_path` 的文件名。上传目录包含日期和任务 ID，不能参与稳定 ID 计算。
3. 路径也不存在时使用规范化 `file_title` 作为来源标识，并记录可能重名的 warning；同名不同文档应由调用方显式提供 `document_id`。
4. 对来源标识执行 SHA-256，输出固定长度十六进制字符串。
5. 不将正文 hash 加入 `document_id`，保证文件内容更新后仍覆盖同一逻辑文档。

输入：导入状态、文件标题。

输出：稳定 `document_id`。

### `def apply_document_metadata(chunks, metadata) -> list[dict]`

核心功能：把文档级字段下沉到每个 chunk。

步骤：

1. 校验 metadata 包含 `document_id` 和四个业务字段。
2. 遍历 chunks。
3. 写入 `document_id`、`region_names`、`document_type`、`topics`、`keywords`。
4. 列表字段为每个 chunk 创建副本，避免共享可变列表。
5. chunk 中若已存在冲突的文档级值，视为流程错误而不是静默保留。
6. 返回更新后的 chunks。

输入：chunk 列表、规范化 metadata。

输出：已下沉文档级 metadata 的 chunk 列表。

### `def extract_document_metadata(state, force=False) -> dict`

核心功能：完成 metadata 抽取并写回导入状态。

步骤：

1. `force=False` 且现有 `document_metadata` 通过完整校验时直接复用。
2. 从 `state.md_content` 获取正文；为空时尝试读取 `md_path`。
3. 正文为空时抛出 `ValueError`。
4. 确定 `file_title`，但不让 LLM 重写文件标题。
5. 调用 `extract_metadata_by_llm`。
6. 调用 `_build_document_id` 并加入 metadata。
7. 将 `file_title`、`document_id`、`document_type`、`document_metadata` 写回 state。
8. 若 state 已有 chunks，调用 `apply_document_metadata`；正常工作流中通常尚未切分。
9. 记录文种、地域、topics 数量等摘要日志，不记录完整正文和 prompt。
10. 返回更新后的 state。

输入：导入状态、是否强制重新抽取。

输出：包含规范化 `document_metadata` 的导入状态。

### `def recognize_and_index_item_name(state) -> dict`

核心功能：仅作为旧调用方的临时兼容入口。

步骤：

1. 输出接口废弃 warning。
2. 调用 `extract_document_metadata(state)`。
3. 不生成 `item_name`，不执行索引写入。
4. 等外部调用方完成迁移后删除该函数，并将节点名改为 `node_document_metadata`。

输入：旧节点传入的状态。

输出：完成文档 metadata 抽取的状态。

### 7. 本文件应删除的旧逻辑

实现阶段应删除或停止使用以下类别的函数和常量：

- 英文 `DOCUMENT_TYPES`、`VALIDITY_STATUSES`、`REGION_LEVELS`。
- `_DOCUMENT_TYPE_RULES`、`_SUBTYPE_RULES`、`_REGIONS`、`_TOPIC_RULES`。
- `classify_document_type`。
- `_extract_document_number`、`_extract_dates`、`_extract_regions`、`_infer_validity` 等旧字段规则。
- `extract_metadata_by_rules` 和 `_merge_metadata`。

新版 prompt 也只输出四个业务字段，不再要求模型生成已删除字段。

---

# 第三部分：`app\rag\import_\index_service.py`

## 整体思路

### 1. 核心职责

索引服务只接收已经完成切分和向量化的 chunks，执行以下工作：

1. 校验 chunk 业务字段、基础设施字段和向量。
2. 把内部 chunk 转换为严格白名单的 Milvus record。
3. 创建或校验新版 collection schema。
4. 以 `chunk_id` 为主键执行 upsert。
5. 在新数据全部成功后删除同一 `document_id` 下已经失效的旧 chunk。

索引服务不再读取或写入 `item_name`，也不再以 `item_name` 作为重复导入清理条件。

### 2. 新版 Milvus schema

建议关闭 dynamic field，避免旧字段和临时字段被意外写入：

```text
enable_dynamic_field = False
```

| 字段 | Milvus 类型 | 约束/说明 |
| --- | --- | --- |
| `chunk_id` | `VARCHAR` | 主键，`auto_id=False`，最大 64 |
| `document_id` | `VARCHAR` | 最大 64，用于文档级幂等更新 |
| `chunk_index` | `INT32` | 文档内顺序 |
| `file_title` | `VARCHAR` | 最大 512 |
| `section_title` | `VARCHAR` | 最大 512 |
| `content` | `VARCHAR` | 最大 65535 |
| `context_type` | `VARCHAR` | 最大 32 |
| `region_names` | `ARRAY<VARCHAR>` | 最多 8 项，单项最大 128 |
| `document_type` | `VARCHAR` | 最大 32，中文枚举 |
| `topics` | `ARRAY<VARCHAR>` | 最多 5 项，单项最大 128 |
| `keywords` | `ARRAY<VARCHAR>` | 最多 10 项，单项最大 128 |
| `token_count` | `INT32` | 非负整数 |
| `dense_vector` | `FLOAT_VECTOR` | 维度等于 `MILVUS_VECTOR_DIM` |
| `sparse_vector` | `SPARSE_FLOAT_VECTOR` | 稀疏向量 |

向量索引继续使用：

- `dense_vector`：`AUTOINDEX`，`metric_type=IP`。
- `sparse_vector`：`SPARSE_INVERTED_INDEX`，`metric_type=IP`，算法 `DAAT_MAXSCORE`。

### 3. collection 迁移原则

当前 collection 的主键是自动生成的 `INT64 chunk_id`，同时还包含 `item_name/title/parent_title/part`，与新 schema 不兼容。Milvus 已存在 collection 不能通过“发现存在就直接返回”完成字段变更。

`prepare_chunks_collection` 优先检查配置集合。若其 schema 不兼容，则保留旧集合和旧数据，自动选择下一个版本名：普通名称追加 `_v2`，已有 `_vN` 后缀时递增版本号。版本集合不存在时自动创建；存在且兼容时直接复用；配置集合和版本集合均不兼容时才明确报错。系统不会自动删除或覆盖已有 collection。

### 4. 幂等写入原则

- `chunk_id` 是手动生成的 VARCHAR 主键。
- 同一 `document_id + chunk_index` 生成同一 `chunk_id`。
- 重新导入时先获取该文档已有 chunk IDs。
- 先 upsert 当前全部 chunks；全部成功后再删除“旧集合减当前集合”的失效 IDs。
- 如果批量 upsert 中途失败，不执行失效数据清理。旧数据仍可检索，重试后最终收敛。
- 不采用“先按 item_name 删除、再插入”的方式，避免字段失效、过滤表达式注入和插入失败造成整篇文档暂时消失。

### 5. 入库白名单

写入 Milvus 前只保留 schema 中声明的字段。以下内部字段即使存在也必须丢弃：

```text
embedding_text、section_path、heading_level、part_index、
以及所有旧字段和诊断字段
```

## 函数中文说明

### `def require_chunks(state) -> list[dict]`

核心功能：获取并完成 chunks 的第一层结构校验。

步骤：

1. 从 `state` 获取 `chunks`。
2. 校验其为非空列表。
3. 校验每一项均为字典。
4. 失败时抛出带 chunk 索引的 `ValueError`。
5. 返回原 chunks，不在该函数中修改数据。

输入：导入状态。

输出：非空 chunk 字典列表。

### `def _validate_chunk(chunk, index) -> None`

核心功能：严格校验单个 chunk 是否满足入库契约。

步骤：

1. 校验所有必填字段存在。
2. 校验 `chunk_id/document_id/file_title/section_title/content/context_type/document_type` 的类型、非空和最大长度。
3. 校验 `context_type` 命中 `text/table/code` 枚举。
4. 校验 `document_type` 命中五个中文枚举。
5. 校验 `region_names/topics/keywords` 为字符串数组且不超容量。
6. 校验 `chunk_index/token_count` 为非负整数。
7. 校验 `dense_vector` 长度等于 `MILVUS_VECTOR_DIM` 且元素可转为有限浮点数。
8. 校验 `sparse_vector` 非空、索引非负、权重为有限数。
9. 错误信息包含 chunk 序号和字段名，禁止只记录 warning 后跳过坏数据。

输入：单个 chunk、其在列表中的索引。

输出：无；非法时抛出异常。

### `def _to_milvus_record(chunk) -> dict`

核心功能：把内部 chunk 转换为严格字段白名单的 Milvus record。

步骤：

1. 只复制新版 schema 声明的字段。
2. 对字符串执行首尾空白清理，但不改写 `content` 内部格式。
3. 列表字段复制为新列表。
4. 数字字段转换为明确的 `int/float` 类型。
5. 不写入 `embedding_text`、标题路径和任何旧字段。
6. 返回新字典，不原地修改 chunk。

输入：已通过校验的 chunk。

输出：可写入 Milvus 的 record。

### `def prepare_chunk_records(chunks) -> list[dict]`

核心功能：在发生任何数据库修改前，一次性完成全量校验和 record 转换。

步骤：

1. 遍历全部 chunks。
2. 对每项调用 `_validate_chunk`。
3. 调用 `_to_milvus_record`。
4. 校验同一批次内 `chunk_id` 不重复。
5. 校验所有 chunks 的 `document_id` 相同；当前接口一次只索引一个文档。
6. 校验 `chunk_index` 连续且从 0 开始。
7. 返回 records。

输入：完成向量化的 chunks。

输出：通过完整校验的 Milvus records。

### `def _collection_schema_matches(client, collection_name) -> bool`

核心功能：判断已存在 collection 是否与新版 schema 完全兼容。

步骤：

1. 获取 collection 描述和字段列表。
2. 比较主键名称、类型和 `auto_id`。
3. 比较业务字段类型、VARCHAR 长度、ARRAY 容量及向量维度。
4. 比较 dynamic field 开关。
5. 返回布尔值，并为不匹配项生成可记录的差异摘要。

输入：Milvus client、collection 名称。

输出：schema 是否兼容。

### `def prepare_chunks_collection() -> str`

核心功能：确保新版 chunks collection 和向量索引可用。

步骤：

1. 获取 Milvus client 和配置中的 collection 名称。
2. 配置 collection 不存在时直接按新版 schema 创建。
3. collection 已存在时调用 `_collection_schema_matches`。
4. schema 兼容时直接复用配置 collection。
5. schema 不兼容时保留旧 collection，选择 `_v2` 或递增后的版本名称。
6. 版本 collection 不存在时创建 schema 及 dense/sparse 索引；存在且兼容时直接复用。
7. 配置集合和版本集合均不兼容时明确报错，不删除任何已有数据。

输入：无显式参数，使用 Milvus gateway 和配置。

输出：本次导入实际使用的 collection 名称。

### `def get_existing_chunk_ids(document_id, collection_name=None) -> set[str]`

核心功能：查询同一逻辑文档当前已经存在的 chunk IDs。

步骤：

1. 校验 `document_id` 为系统生成的十六进制字符串。
2. 使用转义后的精确过滤表达式查询 `document_id`。
3. 只请求 `chunk_id` 字段并处理分页。
4. 返回 ID 集合；文档首次导入时返回空集合。

输入：文档稳定 ID、`prepare_chunks_collection` 返回的实际 collection 名称。

输出：数据库中已有的 chunk ID 集合。

### `def upsert_chunks(records, batch_size=100, collection_name=None) -> int`

核心功能：分批 upsert 当前文档的全部 chunks。

步骤：

1. 校验 records 非空。
2. 按 `batch_size` 分批调用 Milvus upsert。
3. 累计成功写入数量。
4. 任一批失败立即抛出异常，停止后续批次。
5. 返回成功数量，并校验其等于 records 数量。

输入：Milvus records、批大小、实际 collection 名称。

输出：成功 upsert 的记录数。

### `def remove_stale_chunks(stale_chunk_ids, collection_name=None) -> int`

核心功能：删除重新导入后不再存在的旧 chunks。

步骤：

1. 空集合直接返回 0。
2. 校验所有 ID 格式，分批构造主键删除请求。
3. 只删除显式给出的旧 IDs，不使用宽泛标题或 `item_name` 过滤。
4. 返回删除数量并记录摘要日志。

输入：已确认失效的 chunk ID 集合、实际 collection 名称。

输出：删除数量。

### `def index_chunks(state) -> dict`

核心功能：完成单篇文档的校验、幂等写入和旧切块清理。

步骤：

1. 调用 `require_chunks`。
2. 调用 `prepare_chunk_records`；此时尚未修改数据库。
3. 调用 `prepare_chunks_collection` 并取得本次实际使用的 collection 名称。
4. 从 records 获取唯一 `document_id`。
5. 向实际 collection 调用 `get_existing_chunk_ids` 获取旧 ID 集合。
6. 向同一个实际 collection 调用 `upsert_chunks` 写入当前全部 records。
7. 计算 `stale_ids = existing_ids - current_ids`。
8. 仅在 upsert 全部成功后调用 `remove_stale_chunks`。
9. 记录新增/更新数量、清理数量、文档 ID 和 collection 名称。
10. 返回原 state；不把数据库返回对象塞入工作流状态。

输入：包含已向量化 chunks 的导入状态。

输出：索引完成后的原导入状态。

---

# 第四部分：跨模块落地约束

## 1. 状态字段调整

`ImportGraphState` 最终只需要保留与新导入链路有关的字段：

```python
task_id
local_dir
local_file_path
is_md_read_enabled
is_pdf_read_enabled
file_title
pdf_path
md_path
md_content
document_metadata
document_id
document_type
chunks
```

旧 `item_name` 和未使用的 `embedding_content` 应在兼容调用迁移完成后移除。

## 2. Prompt 调整

`app/resources/prompts/document_metadata_extraction.prompt` 应同步改为中文五分类和四字段 JSON，不再出现英文文种、效力状态、地域编码、作者、来源等旧要求。

Prompt 必须强调：

- 地域是文件主体地域，不是地名词频统计。
- 论文和技术报告也需要根据主要研究对象判断地域。
- 无法判断地域时返回 `不限`。
- 不得输出 JSON 之外的解释。
- 不得输出 schema 之外的字段。

## 3. 查询链路兼容风险

当前查询服务仍以 `item_names` 过滤 `item_name`，并读取 `title/parent_title/part`。新版 collection 上线前，查询链路必须同步改为：

- 可选按 `region_names`、`document_type`、`topics` 做 scalar filter。
- 召回输出字段改为 `file_title/section_title/context_type/content` 等新字段。
- 展示标题使用 `file_title + section_title`。
- 不再依赖 item-name collection 确认商品主体。

这部分不属于本次三个 service 的代码范围，但属于切换新版 collection 前的强制迁移项，否则导入成功后查询仍会因旧字段过滤而无结果。

## 4. 建议实施顺序

1. 修改 metadata prompt 和 `item_name_service.py`。
2. 修改 `split_service.py`，建立最终 chunk 契约。
3. 修改 embedding 输入，确认只消费临时 `embedding_text`。
4. 新建/切换 Milvus `chunks_v2` schema，并修改 `index_service.py`。
5. 同步修改查询链路的过滤与 output fields。
6. 使用政策、标准、规划、技术报告、论文各至少一份进行端到端回归。
7. 对超长文本、极短章节、大表格、HTML 表格、代码块、无标题 Markdown 分别增加测试。

## 5. 验收标准

- 任意文种都只按 Markdown 标题初切，切分函数不接收 `document_type`。
- metadata 模型只输出四个业务字段，`document_type` 全程使用中文。
- `region_names` 能区分主体地域与正文偶然提及地名。
- 最终 chunk 不包含已明确删除的字段。
- 表格和代码块不会与普通文本混合，也不会被静默截断。
- 所有 chunk 均有非空 `file_title/section_title/content/context_type`。
- `token_count` 与最终 content 对应。
- 同一文档重复导入不会产生重复 chunk，减少 chunk 数量时旧尾部数据会被清理。
- Milvus schema 不兼容时显式报错，不静默复用旧 collection。
- 查询结果可用 `file_title / section_title` 正确展示来源。
