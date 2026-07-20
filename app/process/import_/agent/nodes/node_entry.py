import json

from app.shared.runtime.logger import node_log
from app.shared.utils.task_utils import add_done_task, add_running_task
from app.process.import_.agent.state import ImportGraphState
from app.rag.import_.entry_service import resolve_input_file

@node_log("node_entry")
def node_entry(state: ImportGraphState) -> ImportGraphState:
    """
    节点: 入口节点 (node_entry)
    为什么叫这个名字: 作为图的 Entry Point，负责接收外部输入并决定流程走向。
    """
    add_running_task(state["task_id"], "node_entry")
    state = resolve_input_file(state)
    add_done_task(state["task_id"], "node_entry")
    return state

if __name__ == '__main__':
    from app.shared.runtime.logger import logger
    from app.process.import_.agent.state import create_default_state
    # 单元测试：覆盖不支持类型、MD、PDF三种场景
    logger.info("===== 开始node_entry节点单元测试 =====")

    # 测试1: pdf文件
    test_state1 = create_default_state(
        task_id="test_task_001",
        local_file_path=r"E:\project\zhishiku\doc\1.法规政策相关\1.国家\关于加强城市节水工作的指导意见.pdf"
    )
    result_1 =  node_entry(test_state1)
    print(f"第一次测试结果: \n {json.dumps(result_1, indent=4, ensure_ascii=False)}")
    # 测试2: MD文件
    test_state2 = create_default_state(
        task_id="test_task_002",
        local_file_path=r"E:\project\zhishiku\output\再生水厂平面布局分析与节地策略探讨\再生水厂平面布局分析与节地策略探讨.md"
    )
    result_2 = node_entry(test_state2)
    print(f"第二次测试结果: \n {json.dumps(result_2, indent=4, ensure_ascii=False)}")
    # 测试3: doc文件
    test_state3 = create_default_state(
        task_id="test_task_003",
        local_file_path=r"E:\project\zhishiku\doc\2.标准规范相关\2.深圳\深圳市辰达市政服务有限公司再生水泵站巡查管理制度（试行）印发版.docx"
    )
    result_3 = node_entry(test_state3)

    print(f"第三次测试结果: \n {json.dumps(result_3, indent=4, ensure_ascii=False)}")

    logger.info("===== 结束node_entry节点单元测试 =====")