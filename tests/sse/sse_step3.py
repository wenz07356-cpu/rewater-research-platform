import asyncio
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import HTMLResponse

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

task_cache = {}

# 异步任务制造数据
async def long_task(session_id:str):
    task_cache[session_id] = []
    # 模拟5秒处理流程（解析查询图节点流程） 每秒1条结果
    for i in range(5):
        task_cache[session_id].append(f"会话：{session_id}处理结果{i+1}")
        await asyncio.sleep(1)

@app.get("/submit/{session_id}")
async def submit_task(session_id:str,background_tasks:BackgroundTasks):
    """
    触发异步任务，相当于开始解析！
    :param session_id: 会话id
    :param background_tasks: fastapi.BackgroundTask 提供的异步任务工具
    :return:
    """
    background_tasks.add_task(long_task, session_id)
    return {"message":"任务已启动","session_id":session_id}


@app.get("/stream/{session_id}")
async def stream_result(session_id:str):
    async def event_generator():
        while len(task_cache.get(session_id,[])) < 5:
            await asyncio.sleep(1)
            current_len = len(task_cache.get(session_id,[]))
            if current_len > 0:
                yield f"data: session：{session_id} 处理数据{task_cache[session_id][-1]}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)