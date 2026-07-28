import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI,BackgroundTasks,UploadFile,File
from fastapi.responses import FileResponse
from starlette.middleware.cors import CORSMiddleware
from mimetypes import guess_type

from app.api.schemas.import_ import UploadResponse, ImportStatusResponse
from app.process.import_.agent.main_graph import import_app
from app.process.import_.agent.state import get_default_state
from app.shared.config.settings_config import settings
from app.shared.runtime.logger import PROJECT_ROOT, logger


from app.shared.utils.task_utils import update_task_status, add_running_task, add_done_task, get_task_status, \
    get_done_task_list, get_running_task_list

app = FastAPI()
app.middleware(
    CORSMiddleware,
    allow_origins = list(settings.cors_origins) or ["*"],
    allow_methods = ["*"],
    allow_headers = ["*"],
)
@app.get("/html")
def import_html():
    html_Path = PROJECT_ROOT / "app" / "process" / "import_" / "page" / "import.html"
    return FileResponse(path = html_Path, media_type=guess_type(html_Path.name)[0])

def run_graph_task(task_id,local_file_path,local_dir):
    try:
        #全局状态
        update_task_status(task_id, "processing")
        logger.info(f"[{task_id}] 开始执行LangGraph全流程，本地文件路径：{local_file_path}")
        #初始化langGraph
        init_state = get_default_state()
        init_state["task_id"] = task_id  # 任务ID关联
        init_state["local_dir"] = local_dir  # 任务本地目录
        init_state["local_file_path"] = local_file_path  # 上传文件本地路径
        #流式调用langgraph，获取节点完成状态；
        for event in import_app.stream(init_state):
            for node_name,node_state_result in event.items():
                logger.info(f"[{node_name}] {node_state_result}")
        update_task_status(task_id, "completed")
        logger.info(f"[{task_id}] LangGraph全流程执行完毕，任务完成")
    except Exception as e:
        update_task_status(task_id, "failed")
        #exc_info=True  打印完整的异常堆栈，包括报错的文件路径、具体行号等
        logger.error(
            f"[{task_id}] LangGraph全流程执行失败，异常信息：{str(e)}", exc_info=True
        )

@app.post("/static")
async def upload_files(
        background_tasks:BackgroundTasks,
        files:list[UploadFile] = File(...)
):

    today_str = datetime.now().strftime("%Y%m%d")
    date_based_root_dir: Path = PROJECT_ROOT / "output" / today_str

    task_ids = []

    for file in files:
        task_id = str(uuid.uuid4())
        task_ids.append(task_id)
        logger.info(f"[{task_id}] 开始处理上传文件，文件名：{file.filename}，文件类型：{file.content_type}")

        add_running_task(task_id, "upload_file")

        task_local_dir : Path = date_based_root_dir / task_id
        task_local_dir.mkdir(parents=True,exist_ok=True)

        local_file_abs_path: Path = task_local_dir / file.filename

        with local_file_abs_path.open("wb") as file_buffer:
            shutil.copyfileobj(file.file, file_buffer)
        logger.info(f"[{task_id}] 文件已保存至本地，路径：{local_file_abs_path}")
        add_done_task(task_id, "upload_file")
        background_tasks.add_task(
            run_graph_task,
            task_id,
            str(task_local_dir),
            str(local_file_abs_path)
        )
        logger.info(f"[{task_id}] 已将LangGraph全流程加入后台任务，任务已启动")
    logger.info(f"多文件上传处理完毕，共处理{len(files)}个文件，生成TaskID列表：{task_ids}")
    return UploadResponse(
        code=200,
        message=f"Files uploaded successfully, total: {len(files)}",
        task_ids=task_ids
    )

@app.get("/status/{task_id}",
         summary="任务状态查询",
         description="根据TaskID查询单个文件的处理进度和全局状态",
         response_model=ImportStatusResponse)
async def get_status(task_id: str):
    status = get_task_status(task_id)
    done_list = get_done_task_list(task_id)
    running_list = get_running_task_list(task_id)
    # 记录日志
    logger.info(f"[{task_id}] 任务状态查询，当前状态：{status}，已完成节点：{done_list}")

    return ImportStatusResponse(
        code=200,
        task_id=task_id,
        status=status,
        done_list=done_list,
        running_list=running_list
    )