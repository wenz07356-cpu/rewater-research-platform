import copy
import json
import uuid
from typing import TypedDict, Optional
from app.shared.runtime.logger import logger
class ImportGraphState(TypedDict):
    #任务追踪
    task_id:Optional[str]
    #传入后保存的文件夹
    local_dir:Optional[str]
    #传入文件地址=local_dir/file.filename
    local_file_path:Optional[str]
    #判断结果
    is_md_read_enabled:bool
    is_pdf_read_enabled:bool
    #兜底item_name
    file_title:Optional[str]
    #pdf解析入口文件地址
    pdf_path:Optional[str]

    #md文件/图片地址
    md_path: Optional[str]
    #切片原材料
    md_content:Optional[str]
    #载体
    chunks:Optional[list[str]]  # 根据实际元素类型调整
    #文档主语
    item_name:Optional[str]
    #向量数据库
    embedding_content:Optional[list[list[float]]] #根据实际元素类型调整

graph_default_state: ImportGraphState = {
    'task_id': None,
    'local_file_path': None,
    'is_md_read_enabled': False,
    'is_pdf_read_enabled': False,
    'file_title': None,
    'pdf_path': None,
    'local_dir': None,
    'md_path': None,
    'md_content': None,
    'chunks': None,
    'item_name': None,
    'embedding_content':None,
}

#**overrides:可变关键字传参  自动将多个键值对转成字典
def create_default_state(**overrides) -> ImportGraphState:
    """
    创建默认状态，支持覆盖。
    :param overrides:
    :return:
    """
    new_state = copy.deepcopy(graph_default_state)
    #update():直接原位修改，有就修改，没有key就新增。
    new_state.update(overrides)  #原地修改 无返回值
    return new_state


def get_default_state() -> ImportGraphState:
    """
    返回一个新的状态实例，避免全局污染
    :return:
    """
    return copy.deepcopy(graph_default_state)


if __name__ == '__main__':
    state = create_default_state(task_id=str(uuid.uuid4()),local_file_path = "**")
    #字典转json输出，不用挤在一行，每个key一行。
    logger.info(json.dumps(state, indent=2,ensure_ascii=False))

