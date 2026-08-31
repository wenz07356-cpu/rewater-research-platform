"""共享客户端包。

本模块刻意不做 eager import。导入某个 Milvus/MinIO 子模块时，不应顺带初始化
MongoDB 连接；调用方应从具体子模块导入所需函数。
"""

__all__: list[str] = []
