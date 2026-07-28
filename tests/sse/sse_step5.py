import asyncio
import uuid
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

task_cache = {}

class QueryRequest(BaseModel):
    query: str
    session_id: str = None

@app.post("/submit_query")
async def submit_query(req: QueryRequest,background_tasks: BackgroundTasks):
    session_id = req.session_id or str(uuid.uuid4())
    background_tasks.add_task(long_task,session_id,req.query)
    return {"message":"任务已经启动","session_id":session_id}

async def long_task(session_id:str,query:str):
    task_cache[session_id] = []
    for i in range(5):
        task_cache[session_id].append(f"【{query}】的第{i+1}断回答:xxx{i+1}")
        await asyncio.sleep(1)
    task_cache[session_id].append(f"【{session_id}】查询完成！所有结果已返回")


@app.get("/stream/{session_id}")
async def stream(session_id:str):
    async def event_generator():
        while len(task_cache.get(session_id,[])) <= 5:
            await asyncio.sleep(0.5)
            current_len = len(task_cache.get(session_id,[]))
            if current_len > 0:
                yield f"data:{task_cache[session_id][-1]}\n\n;"
                if current_len == 6:
                    break
    return StreamingResponse(event_generator(), media_type="text/event-stream")