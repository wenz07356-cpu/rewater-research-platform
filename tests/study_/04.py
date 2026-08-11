from app.process.import_.agent.state import ImportGraphState

def enrich_markdowm_images(state:ImportGraphState) ->ImportGraphState:
    """
    核心功能:图片增强
    业务逻辑:
    (1)文档提取复核；
    (2)提取上下文；
    (3)大模型总结；
    (4)上传minio，得到网络地址；
    (5)整体替换得到新的markdown。
    :param state:
    :return:
    """
    pass