你已经完成 docs 目录下的 ARCHITECTURE.md、PROJECT_CONTEXT.md、RAG_DESIGN.md、resource.md。

现在不要新增功能，请进入项目架构审查阶段。

目标：
把 rewater-agent 打造成一个面向 AI Agent 应用工程岗位展示的高质量项目。

请先全面分析当前代码仓库：

1. 对照 docs/ARCHITECTURE.md 检查当前代码实现是否一致：


2. 找出当前项目的问题：
请分类输出：

A. 架构问题
B. 代码组织问题
C. 模块职责问题
D. 命名和接口问题
E. 后续扩展风险

3. 不要大规模重构，请提出：
- 必须修改（影响项目质量）
- 建议修改（提升工程能力展示）
- 可以暂时不做（避免过度设计）

4. 给出下一阶段开发路线：
按照优先级排序：

P0：
必须完成，保证项目成为完整 Agent Demo

P1：
体现高级能力，提高面试竞争力

P2：
研究性质功能，可以后续增加


注意：
不要直接修改代码。
先输出分析报告，等待我确认后再执行修改。



#目标
优化import，理顺业务逻辑。

#具体思路
（1）app\rag\import_\split_service.py  
1）不用区分文本类型，所有类型的文本（政策法规、技术文件、标准等）直接根据md文件的标题初步切割，然后对于过长的content进行精细切割，然后对于短content进行合并。 
2）表格、代码块等按照现有思路执行。
（2）app\rag\import_\item_name_service.py  
1）直接上大模型进行matadate抽取。
region_names：全国、省份、城市、区、不限。（文件主体地名：明确了范围的应该标注地名，这里就包括适用范围，如政策、标准等，北京市再生水管理办法，region_names为北京市；还包括论文、技术文件类，介绍某个地方，如再生水厂用地分析报告，内部主要是深圳市的用地分析，region_names为深圳市。如主体不明确则为不限。）
document-type：政策、标准、规划、技术文件、其他。（备注：使用中文）
context_type：text、table等
topics：
keywords:
token_count：
section_title：
主要这些就可以。有关page_start、page_end、region_level、region_codes、document_subtype、document_number、validity_status、effective_date、source_name这都不需要。
将来展示字段用：file title+section_title 就行。
（3）app\rag\import_\index_service.py
对应前面的内容。

#具体要求
1.进一步完善具体思路，把app\rag\import_\split_service.py 、app\rag\import_\item_name_service.py 、app\rag\import_\index_service.py的思路补全，先不写代码，涉及的函数写好核心功能、输入输出、步骤。
2.最终以import_.md存放到docs目录下。
3.格式要求。
第一部分：app\rag\import_\split_service.py
整体思路：
包括对当前service核心内容说明，包括但不限于原理、原则、核心参数等。
函数中文说明：
示例
def load_markdown_content(state) ->md_content , file_title:
    核心功能：参数获取和校验
    步骤：1. 获取三个参数  md_content , file_title , md_path
         2. md_content 非空校验 -> 空 -> md_path 校验 读取..
         3. file_title 非空校验 -> 空 -> md_path 校验 stem  -> default...
         4. 统一换成符号(数据清洗)  md_content \n\r |  \r  -> \n -> state[md_content] ..
         5. 返回md_content file_title
    输入：state:节点状态
    输出：  md_content：md文件内容
            file_title：文件标题


#目标：
编写import方面的业务代码,确保逻辑自洽，能够跑通。
#内容要求：
1.主要参照docs\import_.md里面的思路。其中 第二部分：`app\rag\import_\item_name_service.py`：“长文档上下文不能只截取开头 16000 字符，否则可能漏掉正文主体地域。建议组成顺序为：文件标题、全部 Markdown 标题目录、正文开头、均匀抽取的中部片段、正文结尾，并在总长度上限内分配。”思路修改为简单的前10000字截取即可，最大长度限制为10000字，在这个思路的基础上修改后面的函数说明。 
2.整体import部分协调一致即可，如果常量、函数、文件名等需要改名称，就修改名称，确保整个import部分能够跑通。
3.影响整个进程的地方以及关键节点需要加日志，包括error、warning、info等。
#代码要求：
1.函数代码都应该有注释，应该包括核心功能、输入输出、步骤等。除此之外，一些难理解的地方也可以加上注释。
2.代码风格统一，使用PEP8标准。
3.代码结构清晰，函数功能单一，避免出现重复代码。
#其他：
1.如果最终函数与docs\import_.md的不一致，同步修改docs\import_.md即可，本次重点在代码。

#目标：
根据现有import环节，对现有query提出修改思路。不编写实现代码，不写具体函数逻辑，只输出核心思路。
#内容要求:
1.分析现有query代码，保持整体框架和所用资源不变。
2.整体修改思路、原则、原理。
3.每个service的核心作用。
4.其他方便我后续做出修改决策的内容。
#输出要求：
以query.md存放到docs目录下。


#目标：
根据query.md的整体思路，对现有query部分的service节点内的函数的业务逻辑进行明确，先不写代码，涉及的函数写好核心功能、输入输出、步骤。

#内容和格式要求。
1.各个节点的业务逻辑先写好。
第一部分：app\rag\query\item_name_confirm_service.py
整体思路：
包括对当前service核心内容说明，包括但不限于原理、原则、核心参数等。
函数中文说明：
示例
def load_markdown_content(state) ->md_content , file_title:
    核心功能：参数获取和校验
    步骤：1. 获取三个参数  md_content , file_title , md_path
         2. md_content 非空校验 -> 空 -> md_path 校验 读取..
         3. file_title 非空校验 -> 空 -> md_path 校验 stem  -> default...
         4. 统一换成符号(数据清洗)  md_content \n\r |  \r  -> \n -> state[md_content] ..
         5. 返回md_content file_title
    输入：state:节点状态
    输出：  md_content：md文件内容
            file_title：文件标题
2.对应用到的propmt也同步输出。
3.一些常量选择、检索方式写明选择理由。
#输出要求：
以query_V1.md存放到docs目录下。



#目标：
编写query方面的业务代码,确保逻辑自洽，能够跑通。
#内容要求：
1.主要参照docs\query_V1.md里面的思路。
2.整体query部分协调一致即可，如果常量、函数、文件名等需要改名称，就修改名称，确保整个query部分能够跑通。
3.影响整个进程的地方以及关键节点需要加日志，包括error、warning、info等。
4.同步修改prompt内相关内容。
#代码要求：
1.函数代码都应该有注释，应该包括核心功能、输入输出、步骤等。除此之外，一些难理解的地方也可以加上注释。
2.代码风格统一，使用PEP8标准。
3.代码结构清晰，函数功能单一，避免出现重复代码。
#其他：
1.如果最终函数与docs\query_V1.md的不一致，同步修改docs\query_V1.md即可，本次重点在代码。


#目标：
优化query来源问题，修改代码
#现状：
目前调用的情况示例：
问题：国家污水资源化政策中，有关宣传力度方面的内容。
回答：国家污水资源化政策中，有关宣传力度方面的内容是：结合世界水日、中国水周、全国城市节水宣传周等主题宣传活动，采取多种形式广泛深入开展宣传工作，加强科普教育，提高公众对污水资源化利用的认知度和认可度，消除公众顾虑，增强使用意愿。完善公众参与机制，充分发挥舆论监管、社会监督和行业自律作用，营造全社会共同参与污水资源化利用的良好氛围 [来源1]。

这个[来源1]用户不知道什么情况。

#修改思路：
1.来源是milvus数据库中的文件，包括直接搜索和hype搜索到的，只要是milvus的，统一为[本地知识库/file_title/section_title]
2.来源为web的，统一为[网络搜索/url]。

#要求：
1.函数代码都应该有注释，应该包括核心功能、输入输出、步骤等。除此之外，一些难理解的地方也可以加上注释。
2.代码风格统一，使用PEP8标准。
3.代码结构清晰，函数功能单一，避免出现重复代码。

#bug修复
刚刚测试时候发生了bug，请检查原因，日志地址：
E:\project\rewater-agent-data-base\logs\app_20260816
现在时间是2026-08-16 下午 09:07:07.
现在先不直接修改代码，先输出原因和解决方案。


#任务：
复核web搜索功能是否能够正常使用。如果app\rag\query\search_embedding_hyde_service.py和app\rag\query\search_embedding_service.py都没有检索到的话，是否web功能可以输出内容。
#问题：
示例：
提问：深圳市再生水发展水平
回答：深圳市再生水发展水平的相关情况在提供的参考证据中未提及该问题的相关信息。
像这种问题完全可以web搜到一定答案，但是却没有。
#要求：
先不修改代码，复核原因，提出解决方案。内容输出到docs\query_V2.md。




#目的：
请为当前 rewater-agent 的query流程的7个节点增加节点调试入口脚本。不是编写pytest测试，而是提供开发阶段手动运行的debug脚本，只做简单测试，能走完看看就行。

#用于：
1. 验证各个graph node是否可以独立运行
2. 查看输入state要求
3. 查看node输出state变化
4. 方便理解整个Agent执行流程

#要求：
不修改业务代码，只在相关node节点下面增加
if __name__ == "__main__":

#示例：
if __name__ == "__main__":
    test_state = {
        "session_id": "xxxx",
        "is_stream": False,
        "rewritten_query": "深圳市再生水现状",
    }
    result_state = node_web_search_mcp(test_state)
    print(result_state)


#修改测试案例：
app\rag\query\rerank_service.py缺乏web_search_docs，不方便测试，至少要有一个web_search_docs。
#修改位置：
不修改业务代码，只修改以下部分。
if __name__ == "__main__":
    test_state = {
        "session_id": "debug-rerank",
        "is_stream": False,
        "rewritten_query": "深圳市再生水现状",
        "query_filters": {
            "file_titles": [],
            "region_names": ["深圳市"],
            "document_types": [],
            "topics": ["再生水现状"],
            "keywords": ["再生水"],
            "hard_fields": [],
            "strict": False,
        },
        "rrf_chunks": [
            {
                "chunk_id": "debug-chunk-1",
                "file_title": "深圳市再生水利用示例资料",
                "section_title": "发展现状",
                "display_title": "深圳市再生水利用示例资料 / 发展现状",
                "content": "深圳市持续推进再生水设施建设和利用。",
                "context_type": "text",
                "region_names": ["深圳市"],
                "document_type": "规划",
                "topics": ["再生水利用"],
                "keywords": ["设施建设"],
                "score": 0.03,
                "source": "milvus",
                "retrieval_sources": ["embedding", "hyde"],
                "url": "",
            }
        ],
        "web_search_docs": [],
    }
    result_state = node_rerank(test_state)
    print(result_state)



#任务：
局部优化。
#具体内容：
1.确认app\resources\prompts里面没有用到的prompt，直接删除。

#目标：
确认描述里面的内容，提供局部优化思路，不修改代码。
#描述：
1.app\rag\query\web_search_service.py里面搜索里面增加了很多，但是实际跑起来是默认值，最后app\rag\query\rerank_service.py环节里面也有用到如region_names、topics等这些内容。
        result.append(
            {
                "chunk_id": None,
                "document_id": None,
                "chunk_index": None,
                "file_title": None,
                "section_title": None,
                "display_title": title or "网络搜索结果",
                "content": content,
                "context_type": "text",
                "region_names": [],
                "document_type": None,
                "topics": [],
                "keywords": [],
                "score": 0.0,
                "source": "web",
                "retrieval_source": "web",
                "url": url,
            }
2.app\rag\query\rerank_service.py里面使用构造含标题和必要 metadata 的 Reranker 评分文本，但是我觉得metadata是整个文本的，而不是某一个chunk的，并且web又没有加metadata，去提取metadata感觉没必要。所以是否在构造milvus来源的Reranker 评分文本中不要加metadata了。
#具体要求：
1.确认#描述中的问题是否属实。
2.如果属实，不修改代码，提供优化思路和详细步骤。
3.相关内容输出到docs\query_V3.md。


#目标：
优化代码。
#具体任务：
1.Reranker部分。 对本地和 Web 使用一致的核心评分文本：`display_title + content`。
2.确定能跑通。

#目标：
局部优化思路。
#问题描述
最终回答展示字段[来源]是web搜索的时候，输出的示例：
应用场景不断拓展，福田区在莲花北垃圾转运站实现再生水100%替代自来水用于清洗及清洁，每年节约自来水约3000立方米，节省水费2万余元；宝安区德昌电机厂项目实现再生水规模化用于冲厕，每年节约自来水约12万吨，节省水费50万元以上 [网络搜索/http://www.szlhq.gov.cn/lhswj/gkmlpt/content/12/12884/post_12884500.html]。

后面有链接地址，但是不能直接点开，我想做成可以直接点开的方式。

#具体要求
1.只提供优化思路和步骤。不修改代码。
2.内容输出到docs\query_V4.md。



#目标：
局部优化：
#描述：
导入模块只支持pdf和md，想新增一个docx和doc。
#具体要求：
只提供优化思路和步骤。不修改代码。


#背景：
我是一个agent初学者，有关评估部分的内容，不太清楚。
#任务：
对tests中代码进行解读和评估，分析原理、必要性、不足以及改进方案。
#具体要求：
1.只提供优化思路和步骤。不修改代码。
2.内容输出到docs\tests_.md。
3.由于是初学者，还需要提供本项目评估的全流程和步骤。


请帮我生成一组用于评估当前RAG的问题集
要求：
1. 参考eval\hak180产品安全手册.md
2. 格式 csv
3. 列头 question, ground_truth
4. 生成10对问题和答案
5. 保存在 eval目录下 名称为 qa.csv
6. 编码格式要求：UTF-8 BOM 编码
7. 把 “HAK 180烫金机:” 作为问题开头，明确问题的主体。



生成评估程序的提示词
请帮我生成一个基于ragas的评估程序，用于评估当前项目的rag流程。
要求：
1. 读取我的问题集 eval\qa.csv
2. 用问题集的question去调用我的rag流程，流程入口 knowledge\processor\query_process\main_graph.py 中的query_app
◦ 获取最终的answer 和 context（从state中提取 reranked_docs）
3. 调用ragas框架，使用对以下5个指标进行评估：
Faithfulness, Answer Relevancy, Context Precision, Context Recall, Answer Correctness
4. 把最终评估结果写入一个文件 eval\qa_eval.csv 列头为 question,context,answer , ground_truth, faithfulness, answer_relevancy, context_precision, context_recall, answer_correctness
5. csv 文件编码格式要求：UTF-8 BOM
6. 要求每个方法要有详细注释
7. 把每个步骤的核心函数用 step_1_xx \step_2_xx ... 来命名
8. 评估程序保存在eval目录下，名称为 eval.py
9. 评估过程中需要的模型工具可以使用 knowledge\utils 中的工具
10. 只生成该评估程序，不要修改其他已有程序.

#目标：
解决本项目评估过程中的思路问题，不修改代码。
#主要问题：
我现在认为评估过程就分成以下几个步骤。
1. 生成问题集。
2. 生成评估代码。
3.执行评估代码，基于结果优化参数。

基于上述步骤，我个人面临以下问题：
1.生成问题集：
1）我打算使用AI帮我形成问题集合，格式 csv，缺乏一个基于本项目的提示词，比如列头应该有哪些方便后续的评估。
2）有关生成问题集的方式，目前我想到的是给一个文本md然后生成对应的问题集，是否有其他方式，给几个文本md生成一个问题集？
2.生成评估代码：
1）评估代码我也打算使用AI生成，首先需要一段生成评估代码的提示词，要符合本项目要求。
2）有关评估框架，我主要调用ragas框架，使用对以下5个指标进行评估：Faithfulness, Answer Relevancy, Context Precision, Context Recall, Answer Correctness。但是对ragas框架不太熟悉，我好像也没安装，应该告知如何安装使用。
3.优化
优化的问题后面再说。
#具体要求：
1.只提供思路和步骤,不修改代码。
2.内容输出到docs\tests_111.md。

#目标：
评估系统思路进一步优化。
#具体要求：
1.我打算要删除现有评估体系，使用ragas框架进行评估，但是保留“金标 chunk ID + 分层结果记录”这个思路，是否可行。
2.docs\tests_111.md里面的列头是不是太多了，满足功能的同时方便复核就行，如果确实需要这么多，那就这么多。
3.输出到docs\tests_222.md。

#目标：
基于docs\tests_222.md生成问题集的提示词和生成评估代码的提示词。
#具体要求：
1.只生成提示词
2.输出到docs\tests_333.md。

docs\tests_333.md里面的提示词1，里面需要我提供一下参数。
1.帮我为每个参数增加注释，说明每个参数是干嘛的。
2.另外关于document_chunks是用来干嘛的?我直接传两个md文件行吗？此外如果要传chunks，你可以直接调用milvus来帮我生成吗？

只解答，不进行实际操作。

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



#目标：
解答问题
#描述。
1.不可回答问题是什么意思？有什么意义，可不可以不要？
2.devv_ratio和test_ratio的含义是什么？有什么意义，可不可以不要？



#目标：
修改docs\tests_333.md提示词。
#具体要求：
1.题目类型太细了，直接不要分题目类型：fact, definition, procedure, condition, reason, comparison, summary, unanswerable等等这些，对应修改第二个提示词。
2.通过项目中的 Milvus 查询接口读取并导出这些文件对应的真实切片，把document_chunks补全。本次的文件名（milvus里面的file_title）：成果2-1：深圳市国家再生水利用配置试点城市终期评估材料——自评估报告、深圳市再生水、雨水利用规范
3.输出到docs\tests_444.md。



#目标：
优化提示词app\rag_eval\ragas\prompt_coding
#具体要求：
1.根据app\rag_eval\ragas\rag_gold_questions.csv来修改。
2.之前的评估代码和问题集就不要参考了，我已经删除了。
3.直接在app\rag_eval\ragas\prompt_coding修改。


#目标：
优化评估代码。
#具体要求：
app\rag_eval\ragas\runs\20260819T174911-4c85faeb\summary.json这种最终的评估结果



#目标：
优化query环节，增强用户和后台的交互。
#问题描述：
有关query环节，用户的问题有侧重性，有时候希望高context precision，有时候希望高context recall。问题的不同有时候期望也不同。能不能把一些config参数放到前台，让用户自己选择，我们给四种模式，第一种就是现在这种，第二种突出高context precision，第三种突出高context recall，第四种是用户自己调整参数。
#具体要求：
1.先不弄代码，只提供思路。分析可行性，给出具体的参数，分析哪些参数可以让用户筛选。
2.输出到docs\query_V5.md。
