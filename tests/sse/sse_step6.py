import asyncio
import uuid
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

app = FastAPI()
# 配置跨域（生产环境建议限定具体origin）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# 缓存任务执行结果
task_cache = {}


class QueryRequest(BaseModel):
    query: str
    session_id: str = None


@app.post("/submit_query")
async def submit_query(req: QueryRequest, background_tasks: BackgroundTasks):
    # 生成或使用用户传入的session_id
    session_id = req.session_id or str(uuid.uuid4())
    # 将耗时任务加入后台执行
    background_tasks.add_task(long_task, session_id, req.query)
    return {"message": "任务已经启动", "session_id": session_id}


async def long_task(session_id: str, query: str):
    """模拟耗时的异步任务，分阶段生成结果"""
    task_cache[session_id] = []
    # 模拟5个进度步骤
    for i in range(5):
        # 存储进度消息
        task_cache[session_id].append({
            "event": "progress",  # 标记为进度事件
            "data": f"【{query}】的第{i + 1}段回答:xxx{i + 1}"
        })
        await asyncio.sleep(1)
    # 任务完成，标记为完成事件
    task_cache[session_id].append({
        "event": "complete",  # 标记为完成事件
        "data": f"【{session_id}】查询完成！所有结果已返回"
    })


@app.get("/stream/{session_id}")
async def stream(session_id: str):
    """SSE流式返回任务结果，包含自定义event属性"""

    async def event_generator():
        # 记录已发送的消息索引，避免重复发送
        sent_index = 0
        # 循环监听任务结果，直到收到完成事件
        while True:
            # 获取当前session的所有消息（无则为空列表）
            messages = task_cache.get(session_id, [])
            # 检查是否有未发送的新消息
            if len(messages) > sent_index:
                for msg in messages[sent_index:]:
                    # 拼接SSE格式：先写event，再写data，最后用\n\n结束
                    yield f"event: {msg['event']}\n"  # 自定义事件类型
                    yield f"data: {msg['data']}\n\n"  # 消息内容
                    sent_index += 1
                    # 如果是完成事件，发送后退出循环
                    if msg["event"] == "complete":
                        return
            # 无新消息时短暂休眠，避免高频轮询
            await asyncio.sleep(0.5)

    # 返回SSE响应，media_type固定为text/event-stream
    return StreamingResponse(event_generator(), media_type="text/event-stream")

# 启动方式（示例）：uvicorn main:app --reload
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)


