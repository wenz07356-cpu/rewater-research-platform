import shutil
import time
import requests

from app.infra.document_parse.mineru_gateway import mineru_gateway
from app.process.import_.agent.state import ImportGraphState, create_default_state
from app.rag.import_.config import MINERU_MODEL_VERSION, MINERU_POLL_TIMEOUT_SECONDS, MINERU_POLL_INTERVAL_SECONDS, \
    MINERU_DOWNLOAD_TIMEOUT_SECONDS
from app.shared.runtime.logger import step_log,logger,PROJECT_ROOT
from pathlib import Path

@step_log("parse_pdf_to_markdown")
def parse_pdf_to_markdown(state: ImportGraphState) -> ImportGraphState:
    """
    PDF 解析服务：
    1. 调用 MinerU
    2. 下载并解压解析结果
    3. 获取 Markdown 路径和正文内容
    4. 回写 md_path / md_content / local_dir
    """
    # 先校验 PDF 路径和输出目录，避免把非法输入送进解析服务。
    pdf_path_obj, local_dir_path_obj = validate_pdf_paths(state)
    # 上传 PDF 到 MinerU，并轮询直到服务端返回最终压缩包地址。
    zip_url = upload_pdf_and_poll(pdf_path_obj)
    logger.info(f"minerU返回的zip地址:{zip_url}")
    # 下载结果包并提取最终 Markdown 文件。
    md_path_obj:Path = download_and_extract_markdown(zip_url, local_dir_path_obj, pdf_path_obj.stem)
    state["md_path"] = str(md_path_obj)
    state["md_content"] = md_path_obj.read_text(encoding="utf-8")
    return state

@step_log("validate_pdf_paths")
def validate_pdf_paths(state: dict) -> tuple[Path, Path]:
    """
    校验PDF文件路径与输出目录，确保文件存在、目录可用并自动补全目录
    :param state: 流程状态字典，包含 pdf_path、local_dir 字段
    :return: 元组(解析后的PDF路径对象, 本地输出目录对象)
    :raises ValueError: pdf_path 为空时抛出异常
    :raises FileNotFoundError: PDF文件不存在时抛出异常
    """
    # 从状态中读取PDF文件路径和本地输出目录
    pdf_path = state.get("pdf_path")
    local_dir = state.get("local_dir")

    # 校验PDF路径是否为空，为空则终止流程并抛出异常
    if not pdf_path:
        logger.error("pdf_path的参数值为空,无法读取文件!")
        raise ValueError("pdf_path的参数值为空,无法读取文件!")

    # 输出目录为空时，使用项目根目录下的output作为默认目录，并回写到状态中
    if not local_dir:
        logger.warning("没有传入local_dir地址,给与默认值!")
        local_dir = PROJECT_ROOT / "output"
        state["local_dir"] = str(local_dir)

    # 转为Path对象，方便后续路径操作
    pdf_path_obj = Path(pdf_path)
    local_dir_obj = Path(local_dir)

    # 校验PDF文件是否真实存在，不存在则抛出异常
    if not pdf_path_obj.exists() or not pdf_path_obj.is_file():
        logger.error(f"pdf_path:{pdf_path_obj},但是没有文件存在!")
        raise FileNotFoundError(f"pdf_path:{pdf_path_obj},但是没有文件存在!")

    # 输出目录不存在则自动创建（支持多级目录，已存在也不报错）
    if not local_dir_obj.exists():
        logger.warning(f"local_dir:{local_dir_obj}地址没有文件夹,我们需要主动创建!")
        local_dir_obj.mkdir(parents=True, exist_ok=True)

    # 返回路径对象供后续业务使用
    return pdf_path_obj, local_dir_obj


@step_log("upload_pdf_and_poll")
def upload_pdf_and_poll(pdf_path_obj: Path) -> str:
    """
    核心功能：上传PDF文件到MinerU服务，并轮询等待解析完成，最终返回解析结果的下载地址
    业务逻辑：
    (1)配置检查；
    (2)构造请求报文；
    (3)网络状态确认；
    (4)收到响应报文；
    (5)业务状态确认；
    (6)获取上传地址，上传，用Session+put 标准操作；
    (7)轮询获取下载地址(构造请求报文，网络状态)；
    :param pdf_path_obj: 本地PDF文件路径对象；
    :return: 解析完成后的ZIP压缩包下载地址；
    """

    # 1. 校验MinerU服务配置（base_url和api_key必须存在）
    if not mineru_gateway.base_url or not mineru_gateway.api_key:
        logger.error("minerU配置错误,请检查minerU配置!")
        raise ValueError("minerU配置错误,请检查minerU配置!")

    # 2. 构造请求地址和请求头
    url = f"{mineru_gateway.base_url}/file-urls/batch"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {mineru_gateway.api_key}",
    }

    # 3. 构造请求参数：文件名 + 使用的模型版本
    data = {
        "files": [{"name": pdf_path_obj.stem,
                   "is_ocr": True}],
        "model_version": MINERU_MODEL_VERSION
    }

    # 4. 请求MinerU获取文件预上传地址
    response = requests.post(url, headers=headers, json=data)
    if response.status_code != 200:
        logger.error(f"申请上传地址失败,返回状态码为:{response.status_code},网络状态错误，无法继续业务!")
        raise RuntimeError(f"申请上传地址失败,返回状态码为:{response.status_code},网络状态错误，无法继续业务!")

    # 5. 解析返回结果，校验业务状态码
        """
        响应示例
        {
        "code": 0,
        "data": {
        "batch_id": "2bb2f0ec-a336-4a0a-b61a-241afaf9cc87",
        "file_urls": ["https://***"]
        },
        "msg": "ok",
        "trace_id": "c876cd60b202f2396de1f9e39a1b0172"
}
        """
    result_dict = response.json()
    if result_dict["code"] != 0:
        logger.error(
            f"申请地址网络状态成功!但是业务失败!错误码:{result_dict['code']},失败信息:{result_dict['msg']}"
        )
        raise RuntimeError(
            f"申请地址网络状态成功!但是业务失败!错误码:{result_dict['code']},失败信息:{result_dict['msg']}"
        )

    # 6. 提取上传URL和任务批次ID
    #file_urls是预签名地址 第三方文件服务器的地址（想要往服务器上传文件需要认证）
    #方案1：上传的时候传入token；
    #方案2：预先认证  预先签名地址 ->put(代码) ->代理（vpn）会添加额外的请求头  ->电脑的网络（网卡）  ->文件服务器  大概率报错
    #尽量让请求更加干净 不要携带其他不相关的代理头 session
    file_upload_urls = result_dict.get("data",{}).get("file_urls",[])
    batch_id = result_dict.get("data",{}).get("batch_id")
    file_upload_url = None
    if len(file_upload_urls) > 0:
        file_upload_url = file_upload_urls[0]
    if not batch_id:
        logger.error(f"申请minerU解析文件，返回的batch_id为空，业务无法继续进行！业务中断！")
        raise ValueError(f"申请minerU解析文件，返回的batch_id为空，业务无法继续进行！业务中断！")
    # 7. 上传PDF文件到MinerU的存储地址
    with requests.Session() as session:
        # session.trust_env = False 是告诉 requests ： 不要信任系统环境变量里的代理、证书、认证等配置 。
        # session.trust_env = False 的意思就是：
        # - 别用系统里自动带来的代理、证书、账号配置
		# - 只按我这个代码里写的内容发请求
        #上传的地址是, 预签名上传地址 , OSS / S3 / 对象存储直传地址 非常脆弱
        #上传文件服务器，只有网络状态，没有业务状态。
        session.trust_env = False
        upload_response = session.put(file_upload_url, data=pdf_path_obj.read_bytes())
        if upload_response.status_code != 200:
            logger.error(
                f"上传文件失败,返回状态码为:{upload_response.status_code},请检查minerU配置!"
            )
            raise RuntimeError(
                f"上传文件失败,返回状态码为:{upload_response.status_code},请检查minerU配置!"
            )

    # 8. 构造轮询查询地址
        #获取minerU解析结果
        #方案一：回调（minerU -> 我们的服务器fastAPI）申请地址的时候，请求体callback = 我们的地址
        #方案二：轮询(我们 -> 3s -> minerU -> batch_id -> 解析结果)
    poll_url = f"{mineru_gateway.base_url}/extract-results/batch/{batch_id}"
    timeout = MINERU_POLL_TIMEOUT_SECONDS
    interval_time = MINERU_POLL_INTERVAL_SECONDS
    start_time = time.time()

    # 9. 开始轮询任务解析状态
    while True:
        # 超时判断
        if time.time() - start_time > timeout:
            logger.error(f"轮询获取{batch_id}对应的解析结果超时！耗时为：{time.time() - start_time}")
            raise TimeoutError(f"轮询获取{batch_id}对应的解析结果超时！耗时为：{time.time() - start_time}")

        try:
            # 请求轮询接口
            poll_response = requests.get(poll_url, headers=headers)
        except Exception:
            logger.warning("请求出现异常!可以稍后重试!!")
            time.sleep(interval_time)
            continue

        # 网络异常处理：5xx可重试，其他直接报错
        if poll_response.status_code != 200:
            if 500 <= poll_response.status_code < 600:
                logger.warning(f"可有修复的网络异常,状态码为:{poll_response.status_code}")
                time.sleep(interval_time)
                continue
            else:
                logger.error(f"不可修复的网络状态异常,状态码为:{poll_response.status_code},稍后再试，等待服务器修复")
                raise RuntimeError(f"不可修复的网络状态异常,状态码为:{poll_response.status_code}")

        # 解析返回结果
        poll_response_dict = poll_response.json()
        if poll_response_dict["code"] != 0:
            logger.error(
                f"轮询业务异常,错误码:{poll_response_dict['code']},失败信息:{poll_response_dict['msg']}"
            )
            raise RuntimeError(
                f"轮询业务异常,错误码:{poll_response_dict['code']},失败信息:{poll_response_dict['msg']}"
            )

        # 10. 获取解析任务状态
        extract_result = poll_response_dict.get("data",{}).get("extract_result",[])
        if len(extract_result) == 0:
            logger.warning(f"解析结果extract_result为空，跳过本次！稍后再试")
            time.sleep(MINERU_POLL_INTERVAL_SECONDS)
            continue
        extract_result_state = extract_result[0].get("state")

        # 任务完成 → 返回下载地址
        if extract_result_state == "done":
            extract_result_url = extract_result[0].get("full_zip_url")
            if not extract_result_url:
                logger.error(
                    f"获取：{batch_id}对应的解析结果，任务已经完成，但是full_zip_url为空！业务失败，提前终止！"
                )
                raise RuntimeError(
                    f"获取：{batch_id}对应的解析结果，任务已经完成，但是full_zip_url为空！业务失败，提前终止！"
                )
            return extract_result_url

        # 任务失败 → 抛出异常
        if extract_result_state == "failed":
            raise RuntimeError(f"已经完成了解析,但是失败了!!失败信息:{extract_result['err_msg']}")

        # 任务仍在处理中 → 等待后继续轮询
        logger.warning(f"解析正在进行中,状态:{extract_result_state}!")
        time.sleep(interval_time)

@step_log("download_and_extract_markdown")
def download_and_extract_markdown(zip_url: str, local_dir_path_obj: Path, stem: str) -> Path:
    """
    (1)请求报文
    (2)网络确认
    (3)响应报文
    (4)解压文件
    (5)md文件确认

    Args:
        zip_url: MinerU 返回的 ZIP 下载地址
        local_dir_path_obj: 本地存放解压文件的目录
        stem: 原始 PDF 的文件名（不带后缀，用于重命名 MD）

    Returns:
        Path: 最终整理好的 MD 文件路径对象
    """
    # ---------------------- 1. 下载 ZIP 压缩包 ----------------------
    # 发送请求下载解析好的 ZIP 文件
    response = requests.get(zip_url, timeout=MINERU_DOWNLOAD_TIMEOUT_SECONDS)
    if response.status_code != 200:
        logger.error(
            f"向指定地址：{zip_url}下载zip文件报错，状态码为：{response.status_code},业务无法继续"
        )
        raise RuntimeError(
            f"向指定地址：{zip_url}下载zip文件报错，状态码为：{response.status_code},业务无法继续"
        )
    # 拼接 ZIP 保存路径：输出目录 + 文件名_result.zip
    zip_path_obj = local_dir_path_obj / f"{stem}_result.zip"

    """
    response
        .status_code ->网络状态
        .json() ->服务器返回的json字符串 ->dict
        .text ->服务器范围的json字符串 ->str ->json.loads
        .content ->服务器返回的字节数据
    """

    # 将二进制内容写入 ZIP 文件
    zip_path_obj.write_bytes(response.content)

    # ---------------------- 2. 解压 ZIP 文件 ----------------------
    # 解压目录 = 输出目录 / PDF 文件名（无后缀）
    extract_path_obj = local_dir_path_obj / stem
    # 如果解压目录已存在，先删除（防止旧文件干扰）
    if extract_path_obj.exists():
        shutil.rmtree(extract_path_obj)
    # 创建新的解压目录
    extract_path_obj.mkdir(parents=True, exist_ok=True)
    # 解压 ZIP 包到目标目录
    #unpack_archive(原目录，现目录)
    shutil.unpack_archive(zip_path_obj, extract_path_obj)

    # ---------------------- 3. 查找所有 MD 文件 ----------------------
    # 递归查找解压目录下所有 .md 文件
    #rglob("*.md")  Path下面的函数，遍历文件夹中文件，生成一个生成器。
    md_file_list = list(extract_path_obj.rglob("*.md"))
    # 没有找到 MD 文件则抛出异常
    if not md_file_list:
        logger.error(f"在:{extract_path_obj}没有任何md文件!")
        raise FileNotFoundError(f"在:{extract_path_obj}没有任何md文件!")

    # ---------------------- 4. 按优先级选择 MD 文件 ----------------------
    # 优先级 1：找和 PDF 同名的 MD（最标准）
    for md_file in md_file_list:
        if md_file.stem == stem:
            logger.info(f"向指定地址：{zip_url}下载zip文件，解压后的文件名，等于原文件名{stem},直接返回！")
            return md_file

    # 优先级 2：找不到同名，找 full.md（MinerU 默认完整导出文件）
    target_md_obj = None
    for md_file in md_file_list:
        if md_file.name.lower() == "full.md":
            target_md_obj = md_file
            break

    # 优先级 3：还找不到，直接取第一个 MD
    if not target_md_obj:
        target_md_obj = md_file_list[0]

    # ---------------------- 5. 重命名为统一规范名称 ----------------------
    # 将选中的 MD 重命名为 {stem}.md（和 PDF 同名）
    logger.info(f"触发重命名机制，原名称：{md_file.stem},目标名称{stem}")
    #with_name只修改path对象  rename是真的在磁盘原位改名。
    return target_md_obj.rename(target_md_obj.with_name(f"{stem}.md"))

