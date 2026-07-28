from app.shared.runtime.logger import node_log, logger
from app.shared.utils.task_utils import add_done_task, add_running_task
from app.process.import_.agent.state import ImportGraphState
from app.rag.import_.item_name_service import recognize_and_index_item_name

@node_log("node_item_name_recognition")
def node_item_name_recognition(state: ImportGraphState) -> ImportGraphState:
    """
    节点: 主体识别 (node_item_name_recognition)
    为什么叫这个名字: 识别文档核心描述的物品/商品名称 (Item Name)。
    """
    add_running_task(state["task_id"], "node_item_name_recognition")
    state = recognize_and_index_item_name(state)
    add_done_task(state["task_id"], "node_item_name_recognition")
    return state


# ===================== 本地测试方法（直接运行调试，无需启动LangGraph） =====================
def test_node_item_name_recognition():
    """
    名称识别节点本地测试方法
    功能：模拟LangGraph流程输入，独立测试node_item_name_recognition节点全链路逻辑
    适用场景：本地开发、调试、单节点功能验证，无需启动整个LangGraph流程
    测试前准备：
        1. 确保项目环境变量配置完成（MILVUS_URL/ITEM_NAME_COLLECTION等）
        2. 确保大模型、Milvus、BGE-M3服务均可正常访问
        3. 确保prompt模板（item_name_recognition/product_recognition_system）已存在
    使用方法：
        直接运行该函数：if __name__ == "__main__": test_node_item_name_recognition()
    """
    logger.info("=== 开始执行商品名称识别节点本地测试 ===")
    try:
        # 1. 构造模拟的ImportGraphState状态（模拟上游节点产出数据）
        mock_state = ImportGraphState({
            "task_id": "test_task_123456",  # 测试任务ID
            "file_title": "再生水厂平面布局分析与节地策略探讨",  # 模拟文件标题
            "md_path":r"E:\project\zhishiku\output\再生水厂平面布局分析与节地策略探讨\再生水厂平面布局分析与节地策略探讨_new.md",
            "file_name": "再生水厂平面布局分析与节地策略探讨",  # 模拟原始文件名（兜底用）
            # 模拟文本切片列表（上游切片节点产出，含title/content字段）
            "chunks": [
                {
                    "title": "1 再生水厂占地",
                    "content": "## 1 再生水厂占地北京市的污水处理走在国内的前列,城区八座污水厂近些年逐步改造为再生水厂,分别为左外方庄再生水厂、吴家村再生水厂、北小河再生水厂、卢沟桥再生水厂、酒仙桥再生水厂、清河再生水厂、小红门再生水厂和高碑店再生水厂。再生水厂设计出水水质的确定主要依据《城市污水再生利用 景观环境用水水质》(GB/T 18921—2002) 中的“娱乐性河道类景观环境用水”的水质标准，部分指标参考了《地表水环境质量标准》(GB 3838—2002) 中Ⅳ类水体的标准。"
                },
                {
                    "title": "1.1 占地面积-1",
                    "content": "1.1 占地面积在八座污水厂改造为再生水厂的过程中，除清河污水厂由于扩建新征了少量土地外，其他七座再生水厂均未新征用地，而是在原厂预留用地内或者通过拆除部分现况建(构)筑物完成提标改造。八座再生水厂占地情况见表1和图1，再生水厂占地面积(y)与处理规模(x)呈较好的线性相关性，单位水量建设用地与处理规模整体趋势呈负相关。表 1 再生水厂用地面积  Tab. 1 Area of reclaimed water plants<table><tr><td>项目</td><td>规模/(104m3·d-1)</td><td>占地/m2</td><td>单位水量建设用地/(m2·m-3·d)</td></tr><tr><td>方庄</td><td>4</td><td>49 200</td><td>1.23</td></tr><tr><td>吴家村</td><td>8</td><td>77 591</td><td>0.97</td></tr><tr><td>北小河</td><td>10</td><td>58 500</td><td>0.59</td></tr><tr><td>卢沟桥</td><td>10</td><td>159 560</td><td>1.60</td></tr><tr><td>酒仙桥</td><td>20</td><td>230 000</td><td>1.15</td></tr><tr><td>清河</td><td>55</td><td>397 246</td><td>0.72</td></tr><tr><td>小红门</td><td>60</td><td>484 700</td><td>0.81</td></tr><tr><td>高碑店</td><td>100</td><td>655 000</td><td>0.66</td></tr></table>"
                },
            ]
        })

        # 2. 调用商品名称识别核心节点
        result_state = node_item_name_recognition(mock_state)

        # 3. 打印测试结果（调试用）
        logger.info("=== 商品名称识别节点本地测试完成 ===")
        logger.info(f"测试任务ID：{result_state.get('task_id')}")
        logger.info(f"最终识别商品名称：{result_state.get('item_name')}")
        logger.info(f"切片数量：{len(result_state.get('chunks', []))}")
        logger.info(f"第一个切片商品名称：{result_state.get('chunks', [{}])[0].get('item_name')}")

    except Exception as e:
        logger.error(f"商品名称识别节点本地测试失败，原因：{str(e)}", exc_info=True)


# 测试方法运行入口：直接执行该文件即可触发测试
if __name__ == "__main__":
    # 执行本地测试
    test_node_item_name_recognition()


