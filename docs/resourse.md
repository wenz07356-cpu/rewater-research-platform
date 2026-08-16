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

