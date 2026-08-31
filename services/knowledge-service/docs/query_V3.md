# Query V3 局部优化建议：Web 候选字段与 Reranker 评分文本

## 1. 文档目的

本文只复核当前 Query 链路中 Web 候选字段和 Reranker 评分文本的设计，并给出局部优化方案，不代表代码已经修改。

本次分析范围：

- `app/rag/query/web_search_service.py`
- `app/rag/query/rerank_service.py`
- `app/rag/query/search_embedding_service.py`
- `app/rag/import_/item_name_service.py`
- `app/rag/import_/split_service.py`
- `app/rag/query/answer_output_service.py`

## 2. 结论摘要

| 待确认描述 | 结论 | 说明 |
| --- | --- | --- |
| Web 候选中的 `region_names`、`document_type`、`topics`、`keywords` 实际都是默认值 | 属实 | 当前 WebSearch 响应只解析标题、摘要和 URL，没有抽取这些 metadata |
| 这些 Web 空 metadata 会参与当前 Reranker 评分 | 不属实 | `build_rerank_text()` 明确跳过 `source == "web"` 的 metadata，Web 只使用标题和摘要 |
| 本地候选的上述 metadata 是文档级，而不是 chunk 独有 | 属实 | metadata 在文档级抽取，然后复制到该文档的每一个 chunk |
| Web 中保留大量空 metadata 字段目前存在冗余 | 基本属实 | 当前下游没有读取这些 Web 空字段，它们主要承担“统一候选外形”的作用 |
| 本地 Reranker 评分文本可以不再追加文档级 metadata | 方案合理，但需评测确认 | 可提升本地与 Web 评分输入的一致性并减少 token；但可能损失地域、文种等辅助相关性信号 |

推荐方向：

1. Web 候选只保留当前链路真正需要的公共字段和 Web 专属字段，不伪造空的本地 metadata。
2. Reranker 对本地和 Web 使用一致的核心评分文本：`display_title + content`。
3. 不从 Milvus Schema、Local Candidate 或答案证据中删除本地 metadata；只是不再把它拼入 Reranker 的评分副本。
4. 不为 Web 摘要额外调用 LLM 抽取 metadata。该操作会增加延迟、费用和不稳定性，而且短摘要不足以可靠地产生文档级 metadata。
5. 最终是否落地必须通过同一评测集对比，不能仅凭字段看起来冗余就判断排序效果必然提升。

## 3. 当前实现复核

### 3.1 Web 搜索实际生成了什么

`parse_web_search_response()` 当前只从 MCP 响应读取：

- `title`
- `snippet` 或 `content`
- `url`

随后为了让 Web 候选看起来与本地候选一致，填入以下默认字段：

```python
{
    "chunk_id": None,
    "document_id": None,
    "chunk_index": None,
    "file_title": None,
    "section_title": None,
    "context_type": "text",
    "region_names": [],
    "document_type": None,
    "topics": [],
    "keywords": [],
    "score": 0.0,
}
```

这些值不是从网页正文、搜索结果或查询条件中抽取出来的真实 metadata。

需要区分两个阶段：

1. `build_web_search_query()` 会把查询中的 `file_titles`、`region_names`、`document_types` 追加到搜索关键词，用于提高搜索命中率。
2. 搜索完成后，`parse_web_search_response()` 不会把这些查询条件回填成网页自身的 metadata。

第二点是合理的：查询条件描述的是用户想查什么，不等于某个网页已经被验证具有相同属性。例如用户搜索“深圳市 再生水 政策”，不能直接据此断言每个结果的 `document_type` 都是“政策”。

### 3.2 Web 空 metadata 当前是否被使用

当前主要下游行为如下：

| 阶段 | Web 实际使用字段 | 是否使用 Web 空 metadata |
| --- | --- | --- |
| 候选去重 | `url`，无 URL 时使用 `display_title + content` | 否 |
| Reranker 文本 | `display_title + content` | 否 |
| 动态 Top-K/多样性 | `candidate_id`；Web 的 ID 根据 URL 或文本生成 | 否 |
| 答案来源标签 | `source + url` | 否 |
| 答案证据 | `display_title + content + url` | 否 |

因此，`region_names=[]`、`topics=[]` 等字段目前不会改变 Web Reranker 分数，也不会进入最终答案 Prompt。它们的价值主要是让本地与 Web 都表现为一个字段较齐全的字典，但当前代码没有严格的统一候选类型约束，所以这种占位收益有限。

### 3.3 本地 metadata 的粒度

当前 `document_type`、`region_names`、`topics`、`keywords` 是文档级 metadata：

1. 导入阶段针对整篇 Markdown 调用模型抽取文档 metadata。
2. `apply_document_metadata()` 将同一份 metadata 复制到该文档的每个 chunk。
3. `_build_embedding_text()` 将标题、文种、地域、主题、关键词和 chunk 正文共同用于向量化。
4. Milvus 为每个 chunk 保存这些字段，以支持过滤、结果解释和下游使用。
5. 查询阶段 `normalize_local_candidates()` 把这些字段从 Milvus 命中恢复到本地候选。

所以用户描述“metadata 是整个文本的，而不是某一个 chunk 的”是准确的。它们存储在 chunk 记录上，是为了让 Milvus 能以 chunk 为检索单位执行过滤和返回完整上下文，不表示它们是针对每个 chunk 独立抽取的。

### 3.4 metadata 在当前 Reranker 中的作用

本地候选当前评分文本为：

```text
display_title
document_type；region_names；topics；keywords
content
```

Web 候选当前评分文本为：

```text
display_title
content
```

这会形成来源不对称：同一个 Reranker 在本地候选中能看到额外的分类和范围信息，在 Web 候选中看不到。

这种设计并非完全错误。文档级 metadata 可能补足短 chunk 缺失的地域或文种上下文，例如 chunk 正文只写“本办法适用于……”，而地域只出现在文件标题或文档 metadata 中。不过它也存在以下问题：

- 同一文档的每个 chunk 重复加入相同 metadata，占用 512 token 上限。
- metadata 已参与导入向量文本和本地检索，Reranker 再次加入可能产生重复增益。
- 本地与 Web 输入结构不一致，可能造成来源偏置。
- `topics`、`keywords` 是文档级概括，未必与当前 chunk 的具体内容相关。
- 文档 metadata 如果抽取不准，会在每个 chunk 的精排阶段重复放大误差。

因此，“Reranker 只比较标题和候选正文”是值得优先验证的局部优化方案，但不能在没有评测的情况下断言一定优于当前实现。

## 4. 推荐目标设计

### 4.1 候选数据采用公共字段加来源专属字段

不再要求 Web 候选伪装成本地 chunk。建议概念上拆成三部分：

#### 公共字段

```text
display_title
content
context_type
score
source
retrieval_source
```

#### 本地候选专属字段

```text
chunk_id
document_id
chunk_index
file_title
section_title
region_names
document_type
topics
keywords
token_count
```

#### Web 候选专属字段

```text
url
```

`candidate_id` 和 `rerank_score` 仍由 Reranker 合并阶段生成。这样可以保留异构来源的真实差异，同时继续共享排序所需的核心字段。

局部实现时，Web 候选建议至少保留：

```python
{
    "display_title": title or "网络搜索结果",
    "content": content,
    "context_type": "text",
    "score": 0.0,
    "source": "web",
    "retrieval_source": "web",
    "url": url,
}
```

这里保留 `context_type="text"` 是为了明确 Web 摘要按普通文本处理；保留 `score=0.0` 是为了让 Reranker 失败降级时仍具有明确的初始分数。其他本地专属空字段可以去掉。

### 4.2 Reranker 使用来源一致的评分文本

建议本地和 Web 都使用：

```text
display_title
content
```

也就是：

- 标题负责提供文档和章节语义。
- 正文负责提供当前候选的事实内容。
- 不加入 URL、内部 ID、上游分数或来源名称。
- 不加入 `document_type`、`region_names`、`topics`、`keywords`。

`display_title` 对本地结果已经由 `file_title / section_title` 组成，因此仍能保留最有价值的文档级定位信息，不会退化为只比较裸 chunk 正文。

### 4.3 metadata 保留在其他正确位置

本方案只调整“Reranker 看见的评分文本”，不删除 metadata 本身。

| metadata 使用位置 | 是否保留 | 原因 |
| --- | --- | --- |
| 导入阶段文档抽取 | 保留 | 为行业知识库提供文种、地域、主题和关键词 |
| chunk 向量化文本 | 先保留 | 当前 Hybrid Retrieval 依赖这些上下文增强召回 |
| Milvus Schema | 保留 | 支持硬过滤、软检索和结果解释 |
| Local Candidate | 保留 | 答案证据、调试和未来过滤仍需要 |
| Reranker 评分文本 | 建议移除 | 减少重复 token，并使本地/Web 评分输入一致 |
| 答案证据 metadata | 保留现状 | 文种、地域和内容类型有助于答案模型理解来源 |

本次局部优化不需要重建 Milvus collection，不需要重新导入数据，也不需要修改 QueryGraphState。

## 5. 不推荐的方案

### 5.1 不建议为了字段对齐而给 Web 结果抽取 metadata

原因：

- WebSearch 当前通常只有标题和短摘要，不是完整网页正文。
- 从短摘要推断地域、文种、主题容易产生幻觉或误标。
- 每轮搜索再调用一次或多次 LLM 会显著增加延迟和费用。
- 即使抽取成功，Web 与本地 metadata 的生成依据仍不一致，不能真正保证公平评分。

如果未来确实需要 Web metadata，应先增加可信网页抓取、正文清洗和来源校验，再把它作为独立能力设计，不应放进本次局部优化。

### 5.2 不建议从 Milvus 和 Local Candidate 删除 metadata

这些字段虽然是文档级，但仍承担：

- `region_names`、`document_type` 的硬过滤；
- 标题、主题、关键词的软检索增强；
- 答案证据解释；
- 离线评测中的范围分析。

删除它们会把一个局部 Reranker 优化扩大成导入 Schema 和检索策略迁移，风险与收益不匹配。

### 5.3 不建议直接认定去掉 metadata 一定提升排序

对于正文缺少地域、文种或主题词的 chunk，metadata 可能确实有帮助。正确做法是保留旧策略作为基线，用行业评测集比较，而不是只依据字段来源做结论。

## 6. 建议实施步骤

以下步骤是后续实施方案，本次不执行代码修改。

### 步骤一：建立可比较基线

1. 固定一份至少覆盖以下场景的 Query 评测集：
   - 明确地域，如“深圳市再生水现状”；
   - 明确文种，如“再生水相关政策”；
   - 明确文件标题；
   - 主题型问题；
   - chunk 正文不直接包含地域，但标题或 metadata 包含地域；
   - 本地与 Web 都有有效候选；
   - 仅本地或仅 Web 有候选。
2. 保存当前策略的 `rrf_chunks`、`web_search_docs`、Reranker 输入文本、`reranked_docs` 和最终答案证据。
3. 记录当前排序质量、来源分布、超长文本比例和平均耗时。

### 步骤二：明确候选字段契约

1. 定义公共候选字段、本地专属字段和 Web 专属字段。
2. 明确下游只能根据 `source` 读取来源专属字段。
3. 保持 `web_search_docs` 和 `rrf_chunks` 都是 `list[dict]`，不改变 QueryGraphState 顶层契约。
4. 不要求 Web 候选包含值恒为 `None` 或空列表的本地字段。

### 步骤三：精简 Web 候选

1. `parse_web_search_response()` 继续解析和清洗标题、摘要、URL。
2. 保留公共字段与 `url`。
3. 删除只用于伪装本地结构的空字段。
4. 保持现有 URL 去 fragment、去重和 Top-K 逻辑不变。
5. 保持 Web 搜索查询仍可使用 `file_titles`、`region_names`、`document_types`，但不把查询条件当作网页 metadata 回填。

### 步骤四：统一 Reranker 评分文本

1. 将 `build_rerank_text()` 统一为 `display_title + content`。
2. 去掉本地来源的 metadata 拼接分支。
3. 不修改候选原始 `content` 和 metadata。
4. 保持 512 token 控制、普通文本精简、表格/代码确定性截断逻辑不变。
5. 保持评分失败时的上游顺序降级逻辑不变。

### 步骤五：补充契约测试

至少覆盖：

1. Web 响应解析后不再包含本地专属空字段。
2. Web URL 去重行为不变。
3. 本地候选仍保留完整 metadata。
4. 本地和 Web 的 `build_rerank_text()` 都只包含标题与正文。
5. 本地 metadata 值不会出现在评分文本中。
6. 本地与 Web 合并后 `candidate_id` 唯一且稳定。
7. Web 缺少 URL 时仍可按标题与正文生成稳定 ID。
8. 仅本地、仅 Web、两者都有、两者都空四种输入均能完成。
9. Reranker 异常时仍按原有顺序降级。
10. 答案节点仍能生成正确的本地来源标签和 Web URL 来源标签。

### 步骤六：执行 A/B 离线评测

对比：

- A：当前 `标题 + 文档 metadata + chunk 正文`；
- B：建议的 `标题 + chunk 正文`。

重点指标：

- Reranker Top-1、Top-3、Top-6 证据命中率；
- MRR 或 nDCG；
- 本地与 Web 进入最终 Top-K 的比例；
- 明确地域、文种问题的命中率变化；
- Reranker 输入平均 token 数和超长比例；
- Reranker 延迟；
- 最终答案引用正确率和无依据回答比例。

建议验收条件：

1. 总体证据命中率不下降；
2. 地域、文种问题不能出现明显回退；
3. Web 与本地来源分布没有异常单边偏移；
4. 输入 token 和超长精简次数有可观下降，或者排序稳定性有明确提升；
5. 所有现有 Query 契约测试通过。

如果 B 在地域或文种问题上明显下降，应考虑折中方案：只保留 `region_names` 或 `document_type` 中经过硬过滤确认的字段，而不是恢复全部 `topics + keywords`。折中方案同样必须让评测结果决定。

### 步骤七：灰度与回滚

1. 将旧版与新版评分文本构造封装成可切换策略，先在离线评测中使用。
2. 小范围观察 Reranker 分数分布、来源比例和答案引用。
3. 确认指标稳定后再移除旧策略。
4. 回滚只需恢复 Web 候选占位字段和旧 `build_rerank_text()`，不涉及 Milvus 数据回滚。

## 7. 预计影响范围

如果后续实施，预计只需要调整：

- `app/rag/query/web_search_service.py`
- `app/rag/query/rerank_service.py`
- `tests/test_query_services.py`
- Query 设计文档和离线评测说明

明确不需要调整：

- Query Graph 节点数量和连边；
- QueryGraphState 顶层字段；
- Milvus collection Schema；
- 已导入的向量和文档数据；
- Query Understanding、RRF 和答案生成的主要业务流程。

## 8. 最终建议

本次描述中的核心判断基本成立，但需要修正一个关键认识：Web 候选虽然带有空 metadata 字段，当前 Reranker 实际并没有使用它们。

建议把优化拆成两个独立且可验证的局部变化：

1. 删除 Web 候选中无实际含义的本地专属空字段，明确异构来源契约。
2. 让本地与 Web 的 Reranker 统一比较 `display_title + content`，metadata 继续保留在检索、过滤和答案证据环节。

该方案不需要抽取 Web metadata，也不需要删除本地 metadata 或迁移 Milvus。最终是否采用“Reranker 不拼 metadata”，应由行业 Query 评测集的 A/B 结果决定。
