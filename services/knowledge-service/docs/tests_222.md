# Ragas 主评估体系精简方案

> 目标：放弃现有评估实现，以 Ragas 作为主要评估框架，同时保留“金标 chunk ID + 分层结果记录”的诊断能力。  
> 本文只讨论设计，不修改或删除代码。  
> Ragas API 以实际安装并锁定的 0.4.x 版本为准。

## 1. 结论

方案可行，而且比继续扩展当前评估代码更适合本项目。

建议采用：

```text
人工审核的精简金标题库
        ↓
执行完整 RAG 查询链路
        ↓
记录四层 chunk ID + 最终答案和上下文
        ↓
Ragas 五项语义指标（主要评分）
        +
chunk ID 确定性指标（定位问题）
```

具体取舍如下：

- 放弃当前 HAK 180 演示数据、现有题库生成方式和以现有 runner 为中心的流程。
- Ragas 负责主要质量评估：Faithfulness、Answer Relevancy、Context Precision、Context Recall、Answer Correctness。
- 保留每题的金标 chunk ID。
- 记录普通检索、HyDE、RRF、Rerank 四层实际输出的 chunk ID。
- 建议顺手保留非常简单的 ID precision、ID recall 和 must-hit rate 计算；这部分不是一套独立评估框架，只是几个确定性公式。
- 评估必须执行到最终答案节点，因为前三个答案类指标需要真实 `response`。

不建议“只使用 Ragas，完全不记录 chunk ID”。原因是 Ragas 发现 Context Recall 下降后，只能说明最终上下文有问题，不能直接判断是普通召回、HyDE、RRF 还是 Rerank 导致的。

## 2. 可以删除什么，应该保留什么

### 2.1 可以放弃的部分

当前 `app/rag_eval` 中与 HAK 180 演示强绑定的内容可以由新体系替代：

- 固定的 HAK 180 测试知识；
- 固定的两条演示问题；
- 为测试数据单独入库的流程；
- 以 HAK 180 为前提的过滤条件和 Web 占位数据；
- 当前只运行到 `reranked_docs` 的批量 runner；
- 当前中文报告结构和演示 artifact。

### 2.2 思路上应保留的部分

- `case_id`：稳定关联题库、运行结果和回归历史。
- `gold chunk IDs`：标记回答该问题所需的相关证据。
- `must-hit chunk IDs`：标记不能遗漏的核心证据。
- 四层结果：`embedding_chunks`、`hyde_embedding_chunks`、`rrf_chunks`、`reranked_docs`。
- 单题明细：不能只保存整批平均分。
- 实验配置快照：保证不同运行可以比较。

### 2.3 不建议立即物理删除

实施时不要先删除旧代码再开发新体系。更稳妥的迁移顺序是：

1. 建立新金标题库。
2. 跑通完整查询和五项 Ragas 指标。
3. 用少量固定样本验证新报告中的答案、上下文和 chunk ID 都可追溯。
4. 新旧体系并行跑一次，确认没有遗漏必要能力。
5. 再删除 HAK 180 演示逻辑和不再使用的入口。

这里的“放弃现有评估体系”应理解为重新设计，而不是第一步就清空 `app/rag_eval`。

## 3. `tests_111.md` 的列头是否太多

是的，如果把其中所有建议字段都作为首版必填项，人工维护成本偏高。

原方案的字段适合长期建设大型评测平台，但当前目标是：

- 支持 Ragas 五项指标；
- 保留金标 chunk ID；
- 方便人工复核；
- 能区分开发集和最终测试集；
- 不让人工维护程序本来可以生成的信息。

因此建议继续使用两个文件，但大幅精简人工维护的 `gold_dataset.csv`。运行结果文件由程序生成，列多一些不会增加人工标注负担。

## 4. 精简后的金标题库

### 4.1 推荐的 10 个列头

```csv
case_id,user_input,reference,gold_contexts_json,must_hit_chunk_ids_json,question_type,answerable,split,review_status,notes
```

| 列名 | 必填 | 作用 |
| --- | --- | --- |
| `case_id` | 是 | 唯一题号，用来关联所有运行结果 |
| `user_input` | 是 | 用户问题，对应 Ragas `user_input` |
| `reference` | 是 | 人工审核的标准答案，对应 Ragas `reference` |
| `gold_contexts_json` | 是 | 合并保存金标 chunk ID、来源和证据原文，便于复核 |
| `must_hit_chunk_ids_json` | 建议 | 不能遗漏的核心 chunk；必须是 gold chunk 的子集 |
| `question_type` | 建议 | `fact/procedure/comparison/reason/unanswerable` 等，用于分类看分数 |
| `answerable` | 是 | `true/false`，区分正常回答与应拒答问题 |
| `split` | 是 | `dev/test`，防止使用 test 集反复调参 |
| `review_status` | 是 | `draft/reviewed/rejected`；只运行 reviewed 样本 |
| `notes` | 否 | 记录歧义、边界和审核说明 |

这 10 列已经满足首版功能，不需要继续保留以下独立列：

- `reference_contexts_json`
- `reference_context_ids_json`
- `source_files_json`
- `source_sections_json`

它们合并进一个 `gold_contexts_json` 即可，减少重复维护。

### 4.2 `gold_contexts_json` 的结构

该字段保存一个 JSON 数组，每个元素是一条证据：

```json
[
  {
    "chunk_id": "chunk-101",
    "file_title": "再生水规范.md",
    "section_title": "水质要求",
    "content": "用于支撑标准答案的原始证据文本"
  },
  {
    "chunk_id": "chunk-108",
    "file_title": "运行指南.md",
    "section_title": "操作步骤",
    "content": "另一条原始证据文本"
  }
]
```

这样做的优点：

- 人工复核时能同时看到 ID、文件、章节和原文。
- 程序可直接提取所有 `chunk_id` 作为 gold chunk IDs。
- 多文档问题无需再额外维护 `scope`，可以根据不同 `file_title` 的数量自动判断。
- 不会出现 ID 列表、文本列表和来源列表顺序不一致的问题。

### 4.3 可以进一步删减吗

理论上可以只保留 6 列：

```csv
case_id,user_input,reference,gold_contexts_json,split,review_status
```

但不建议这么做。`answerable` 对不可回答题很重要；`question_type` 对定位不同问题类型的表现很有用；`must_hit_chunk_ids_json` 能区分“一般相关证据”和“绝对不能漏的证据”。这三个字段的维护成本不高，建议保留。

`notes` 可以为空，因此最终推荐仍是 10 列。

### 4.4 CSV 示例

为了便于阅读，下面展示的是概念示例。实际 CSV 中 `gold_contexts_json` 内的双引号必须按照 CSV 规则转义。

```csv
case_id,user_input,reference,gold_contexts_json,must_hit_chunk_ids_json,question_type,answerable,split,review_status,notes
rewater_001,某类再生水应满足哪些基本要求？,根据资料应满足要求A和要求B。,"[{""chunk_id"":""chunk-101"",""file_title"":""规范.md"",""section_title"":""基本要求"",""content"":""要求A和要求B的原文""}]","[""chunk-101""]",fact,true,dev,reviewed,
```

## 5. 运行结果不必追求列少

`run_results.csv` 是程序生成的，不需要人工逐列填写。因此字段是否较多不是主要问题，重点是能完整回查。

推荐列头：

```csv
run_id,case_id,response,retrieved_contexts_json,layer_results_json,faithfulness,answer_relevancy,context_precision,context_recall,answer_correctness,id_metrics_json,latency_ms,error_message,config_snapshot_json
```

| 列名 | 说明 |
| --- | --- |
| `run_id` | 一次实验的唯一标识 |
| `case_id` | 关联金标题库 |
| `response` | 本项目真实生成的最终答案 |
| `retrieved_contexts_json` | 最终真正传给答案模型的上下文文本，顺序必须保留 |
| `layer_results_json` | 四层的 chunk ID、排名和必要 metadata |
| 五个 Ragas 分数 | 每题逐项保存 |
| `id_metrics_json` | 各层 ID precision、recall、must-hit rate |
| `latency_ms` | 端到端耗时 |
| `error_message` | 失败原因；失败题不能静默删除 |
| `config_snapshot_json` | 模型、Prompt、top-k、阈值等配置 |

### 5.1 `layer_results_json` 推荐结构

```json
{
  "embedding": ["chunk-101", "chunk-206"],
  "hyde": ["chunk-101", "chunk-305"],
  "rrf": ["chunk-101", "chunk-206", "chunk-305"],
  "rerank": ["chunk-101", "chunk-305"]
}
```

首版只保存 ID 即可。如果以后需要分析打分过程，再给每项增加 `rank`、`score` 和 `retrieval_source`。不要在尚未用到时提前增加大量字段。

## 6. Ragas 五项指标的数据映射

| Ragas 字段 | 数据来源 |
| --- | --- |
| `user_input` | `gold_dataset.csv.user_input` |
| `reference` | `gold_dataset.csv.reference` |
| `response` | 完整查询链路真实生成的答案 |
| `retrieved_contexts` | `reranked_docs` 中最终实际用于回答的 `content` 列表 |

五项指标的用途：

| 指标 | 主要判断 |
| --- | --- |
| Faithfulness | 回答中的事实是否有实际检索上下文支撑 |
| Answer Relevancy | 回答是否直接回应问题 |
| Context Precision | 相关上下文是否排在无关内容之前 |
| Context Recall | 检索上下文是否覆盖标准答案中的必要信息 |
| Answer Correctness | 最终回答与标准答案是否一致 |

注意：金标 `gold_contexts_json[*].content` 不能当作 `retrieved_contexts` 传给 Ragas。Ragas 必须评估系统这一次真实找回的上下文，而不是人工提供的正确证据。

## 7. 金标 chunk ID 应如何使用

从 `gold_contexts_json` 提取：

```text
gold_chunk_ids = 所有 gold_contexts_json[*].chunk_id
```

每一层都可以用三个简单公式诊断：

```text
ID Precision = 当前层命中的 gold chunk 数 / 当前层返回 chunk 数
ID Recall = 当前层命中的 gold chunk 数 / gold chunk 总数
Must-hit Rate = 当前层命中的 must-hit chunk 数 / must-hit chunk 总数
```

建议每层都计算，而不只是记录 ID。实现成本很低，但能快速得到如下诊断：

| 现象 | 初步判断 |
| --- | --- |
| Embedding Recall 已经低 | 切分、过滤、查询改写或 Embedding 有问题 |
| Embedding/HyDE 各自不错，RRF 后降低 | 融合策略或去重有问题 |
| RRF Recall 高，Rerank 后降低 | Reranker 或保留数量有问题 |
| Rerank ID 指标高，Ragas Faithfulness 低 | 答案模型没有忠实使用证据 |
| Rerank ID Recall 高，Context Recall 低 | 金标 chunk 可能过宽，或 chunk 内容并未完整支撑 reference，需要复核标注 |

这些指标完全确定、无额外模型调用，可以作为 Ragas 的补充，而不是旧评估体系的延续。

## 8. 新评估流程

### 步骤一：加载和校验金标

1. 读取 `gold_dataset.csv`。
2. 只选择 `review_status=reviewed` 的样本。
3. 解析 `gold_contexts_json` 和 `must_hit_chunk_ids_json`。
4. 校验 case ID 唯一、chunk ID 非空、must-hit 是 gold 的子集。
5. 校验 answerable 样本都有非空 reference 和证据。

### 步骤二：执行真实完整查询

1. 使用 `user_input` 调用项目真实查询图。
2. 执行普通检索、HyDE、RRF、Rerank 和最终答案生成。
3. 为评估使用独立 session，避免污染正常历史记录。
4. 回归测试默认关闭或固定 Web 检索，避免外部内容变化。
5. 采集最终 `response` 和四层结果。

### 步骤三：构造 Ragas 输入

1. `user_input` 使用题库问题。
2. `reference` 使用人工标准答案。
3. `response` 使用真实最终答案。
4. `retrieved_contexts` 按原顺序使用最终 `reranked_docs[*].content`。
5. 不允许用 reference、金标证据或 AI 预生成答案替代真实运行结果。

### 步骤四：计算指标

1. 调用 Ragas 计算五项指标。
2. 用金标 ID 计算四层确定性指标。
3. 不可回答题额外计算“是否正确拒答”；这不能完全由五项 Ragas 指标代替。
4. 单题失败要记录错误，不能从汇总分母中静默消失。

### 步骤五：输出与汇总

1. 保存逐题 `run_results.csv`。
2. 生成 `summary.json`。
3. 汇总整体均值、中位数、P10 和有效样本数。
4. 按 `question_type`、`answerable`、`split` 分组。
5. test 集只用于阶段性验收，不用于反复调参。

## 9. 是否还需要 `reference_contexts`

Ragas 五项指标本身主要需要 `reference` 和实际的 `retrieved_contexts`，不要求每项都使用金标原文列表。但是人工审核仍需要看到“标准答案依据什么”。

因此不建议彻底删除金标证据，而是把它压缩进 `gold_contexts_json`：

- 对 Ragas：主要提供可靠的 reference 和标注质量保证。
- 对 ID 指标：提供 gold chunk IDs。
- 对人工复核：提供文件、章节和证据原文。

这一个字段同时承担三种用途，是精简列头后仍然保留它的原因。

## 10. 不可回答题的特殊处理

如果题库包含知识库外问题，仅使用五项 Ragas 指标会有缺口。建议：

- `answerable=false`；
- `reference` 写明正确行为，例如“现有资料无法确定，需补充某项信息”；
- `gold_contexts_json` 可以是空数组；
- `must_hit_chunk_ids_json` 为空数组；
- 单独检查系统是否明确拒答、是否虚构事实、是否提出合理澄清问题。

不可回答题不要与正常题一起计算 ID recall，否则空 gold 集合会造成没有业务意义的 0 分或除零处理。

## 11. 最小实施范围

首版建议控制为：

1. 建立 30～50 条 reviewed 金标题目。
2. 金标题库只使用推荐的 10 列。
3. Ragas 作为主要评估框架，固定并锁定实际验证过的版本。
4. 执行完整查询链路并保存真实 response/context。
5. 保存四层 chunk ID。
6. 每层计算 ID precision、ID recall、must-hit rate。
7. 保存五项 Ragas 单题分数。
8. 对不可回答题增加一个简单的拒答正确率。
9. 输出逐题 CSV 和汇总 JSON。

暂时不必增加：

- 大量业务标签；
- reviewer、generation_method 等过程管理列；
- token 费用分析；
- 多轮对话评估；
- 实时评估平台；
- 图表和数据库存储；
- 每层复杂的 LLM 语义评分。

## 12. 最终建议

可以删除现有评估体系并用 Ragas 重建，但应把下面三项作为新体系的固定组成，而不是旧体系的历史包袱：

1. 金标证据：`gold_contexts_json`，其中包含 chunk ID、来源和原文。
2. 分层记录：保存 Embedding、HyDE、RRF、Rerank 四层 chunk ID。
3. 确定性诊断：每层计算简单的 ID precision、recall 和 must-hit rate。

人工维护的题库使用 10 列已经足够，`tests_111.md` 中其余字段可以先不使用。运行结果虽然字段稍多，但全部由程序生成，不会增加复核人员的标注负担。

最终的新体系可以概括为：

```text
Ragas 决定“整体回答质量好不好”
chunk ID 指标解释“检索链路哪里出了问题”
逐题记录保证“任何一个分数都能回查”
```

这种结构比完全保留旧体系简单，也比只使用 Ragas 更容易支持后续参数优化。
