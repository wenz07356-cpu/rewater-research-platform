from pymilvus import connections, utility, Collection, FieldSchema, CollectionSchema, DataType

# 1. 连接
connections.connect(host="192.168.125.128", port="19530")
print("✅ 连接成功")

# 2. 清理旧测试集合
if utility.has_collection("test_debug"):
    utility.drop_collection("test_debug")

# 3. 创建集合（1024维匹配BGE-M3）
fields = [
    FieldSchema("id", DataType.INT64, is_primary=True, auto_id=True),
    FieldSchema("embedding", DataType.FLOAT_VECTOR, dim=1024)
]
coll = Collection("test_debug", CollectionSchema(fields, "测试集合"))
print("✅ 集合创建成功")

# 4. 写入单条向量（核心修正：二维数组，外层是条数，内层是向量维度）
test_vector = [0.1] * 1024  # 单条1024维向量
res = coll.insert([ [test_vector] ])  # 外层列表对应字段，内层列表是批量向量
print(f"✅ 写入成功，插入条数：{res.insert_count}")

coll.flush()
print(f"✅ 落盘完成，总数据量：{coll.num_entities}")

connections.disconnect("default")