from fastapi import FastAPI, WebSocket, HTTPException, Query, Depends, UploadFile, File, Form
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.websockets import WebSocketDisconnect
import os
from pydantic import BaseModel
import asyncio
import json
import uuid
from typing import Optional, List, Dict, Any
import time
import re
import shutil
import zipfile
import tempfile
from pathlib import Path

# 导入现有的系统
from new_main import IntegratedQASystem
from base import logger

# 创建应用实例
app = FastAPI(title="问答系统API", description="集成MySQL和RAG的智能问答系统")

# 配置CORS，允许前端访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生产环境中应该限制为特定域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 创建静态文件目录
os.makedirs("static", exist_ok=True)

# 创建全局QA系统实例
qa_system = IntegratedQASystem()

# 定义日常问候用语模式和回复
GREETING_PATTERNS = [
    {
        "pattern": r"^(你好|您好|hi|hello)",
        "response": "你好！我是数智IT，专注于为你答疑解惑，很高兴为你服务！"
    },
    {
        "pattern": r"^(你是谁|您是谁|你叫什么|你的名字|who are you)",
        "response": "我是数智IT，你的智能学习助手，致力于提供 IT 相关的解答！"
    },
    {
        "pattern": r"^(在吗|在不在|有人吗)",
        "response": "我在！我是数智IT，随时为你解答问题！"
    },
    {
        "pattern": r"^(干嘛呢|你在干嘛|做什么)",
        "response": "我正在待命，随时为你解答 IT 学习相关的问题！有什么我可以帮你的？"
    }
]

# 定义请求模型
class QueryRequest(BaseModel):
    query: str
    source_filter: Optional[str] = None
    session_id: Optional[str] = None

# 定义响应模型
class QueryResponse(BaseModel):
    answer: str
    is_streaming: bool
    session_id: str
    processing_time: float

# 添加静态文件服务
app.mount("/static", StaticFiles(directory="static"), name="static")

# 根路径重定向到index.html
@app.get("/")
async def read_root():
    return FileResponse("static/index.html")

# 创建新会话
@app.post("/api/create_session")
async def create_session():
    session_id = str(uuid.uuid4())
    return {"session_id": session_id}

# 查询历史消息
@app.get("/api/history/{session_id}")
async def get_history(session_id: str):
    try:
        history = qa_system.get_session_history(session_id)
        return {"session_id": session_id, "history": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取历史记录失败: {str(e)}")

# 清除历史消息
@app.delete("/api/history/{session_id}")
async def clear_history(session_id: str):
    success = qa_system.clear_session_history(session_id)
    if success:
        return {"status": "success", "message": "历史记录已清除"}
    else:
        raise HTTPException(status_code=500, detail="清除历史记录失败")


# 检查是否为日常问候用语并返回模板回复
def check_greeting(query: str) -> Optional[str]:
    query_text = query.strip()  # 去除 # 前缀
    for pattern_info in GREETING_PATTERNS:
        if re.match(pattern_info["pattern"], query_text, re.IGNORECASE):
            return pattern_info["response"]
    return None


# 非流式查询接口
@app.post("/api/query")
async def query(request: QueryRequest):
    start_time = time.time()  # 记录开始时间
    # 使用请求中的 session_id 或生成新 ID
    session_id = request.session_id or str(uuid.uuid4())
    # 检查是否为日常问候
    greeting_response = check_greeting(request.query)
    if greeting_response:
        # 返回问候回复
        return {
            "answer": greeting_response,
            "is_streaming": False,
            "session_id": session_id,
            "processing_time": time.time() - start_time
        }
    # 执行 BM25 搜索
    answer, need_rag = qa_system.bm25_search.search(request.query, threshold=0.85)
    if need_rag:
        # 需要 RAG，提示使用 WebSocket
        return {
            "answer": "请使用WebSocket接口获取流式响应",
            "is_streaming": True,
            "session_id": session_id,
            "processing_time": time.time() - start_time
        }
    # 返回 MySQL 答案
    return {
        "answer": answer,
        "is_streaming": False,
        "session_id": session_id,
        "processing_time": time.time() - start_time
    }

# 流式查询WebSocket接口
@app.websocket("/api/stream")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()  # 接受 WebSocket 连接
    try:
        while True:
            # 接收客户端消息
            data = await websocket.receive_text()
            request_data = json.loads(data)  # 解析 JSON 数据
            # 获取查询参数
            query = request_data.get("query")
            source_filter = request_data.get("source_filter")
            session_id = request_data.get("session_id", str(uuid.uuid4()))
            start_time = time.time()  # 记录开始时间
            # 发送开始标志
            if websocket.client_state == websocket.client_state.CONNECTED:
                await websocket.send_json({
                    "type": "start",
                    "session_id": session_id
                })
            # 检查是否为日常问候
            greeting_response = check_greeting(query)
            if greeting_response:
                if websocket.client_state == websocket.client_state.CONNECTED:
                    # 发送问候回复
                    await websocket.send_json({
                        "type": "token",
                        "token": greeting_response,
                        "session_id": session_id
                    })
                    # 发送结束标志
                    await websocket.send_json({
                        "type": "end",
                        "session_id": session_id,
                        "is_complete": True,
                        "processing_time": time.time() - start_time
                    })
                break
            # 调用问答系统，流式处理查询
            collected_answer = ""
            for token, is_complete in qa_system.query(query, source_filter=source_filter, session_id=session_id):
                collected_answer += token  # 累积答案
                if is_complete and not collected_answer:
                    if websocket.client_state == websocket.client_state.CONNECTED:
                        # 发送结束标志
                        await websocket.send_json({
                            "type": "end",
                            "session_id": session_id,
                            "is_complete": True,
                            "processing_time": time.time() - start_time
                        })
                    break
                if token and websocket.client_state == websocket.client_state.CONNECTED:
                    # 发送 token 数据
                    await websocket.send_json({
                        "type": "token",
                        "token": token,
                        "session_id": session_id
                    })
                if is_complete:
                    if websocket.client_state == websocket.client_state.CONNECTED:
                        # 发送结束标志
                        await websocket.send_json({
                            "type": "end",
                            "session_id": session_id,
                            "is_complete": True,
                            "processing_time": time.time() - start_time
                        })
                    break
                await asyncio.sleep(0.01)  # 控制流式输出的速度
    except WebSocketDisconnect as e:
        # 记录 WebSocket 断开信息
        print(f"WebSocket disconnected: code={e.code}, reason={e.reason}")
    except Exception as e:
        # 记录错误信息
        print(f"WebSocket error: {str(e)}")
        if websocket.client_state == websocket.client_state.CONNECTED:
            # 发送错误消息
            await websocket.send_json({
                "type": "error",
                "error": str(e)
            })
    finally:
        try:
            if websocket.client_state == websocket.client_state.CONNECTED:
                # 关闭 WebSocket 连接
                await websocket.close()
        except Exception as e:
            # 记录关闭连接时的错误
            print(f"Error closing WebSocket: {str(e)}")


# 健康检查端点
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# 文件上传端点，用于更新知识库
@app.post("/api/upload")
async def upload_files(
    files: List[UploadFile] = File(...),
    source: str = Form(None),
    is_zip: bool = Form(False)
):
    """
    上传文件到知识库

    Args:
        files: 上传的文件列表
        source: 学科类别 (如 "ai", "java")，如果不提供则从文件名推断
        is_zip: 是否为zip压缩包，如果是则会解压后处理所有文件
    """
    # 初始化日志ID
    log_id = None
    try:
        # 验证学科类别
        valid_sources = qa_system.config.VALID_SOURCES
        if source and source not in valid_sources:
            return JSONResponse(
                status_code=400,
                content={"error": f"无效的学科类别。有效类别: {valid_sources}"}
            )

        # 文件大小限制验证
        MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB 单个文件限制
        MAX_TOTAL_SIZE = 50 * 1024 * 1024  # 50MB 总文件限制

        logger.info(f"开始文件大小验证，文件数量: {len(files)}")
        total_size = 0
        for uploaded_file in files:
            # 获取文件大小
            uploaded_file.file.seek(0, 2)  # 移动到文件末尾
            file_size = uploaded_file.file.tell()
            uploaded_file.file.seek(0)  # 回到文件开头

            # 检查单个文件大小
            if file_size > MAX_FILE_SIZE:
                return JSONResponse(
                    status_code=400,
                    content={"error": f"文件 {uploaded_file.filename} 超过 {MAX_FILE_SIZE//(1024*1024)}MB 限制"}
                )

            total_size += file_size

        # 检查总文件大小
        if total_size > MAX_TOTAL_SIZE:
            return JSONResponse(
                status_code=400,
                content={"error": f"总文件大小超过 {MAX_TOTAL_SIZE//(1024*1024)}MB 限制"}
            )

        # 准备日志信息
        if not files:
            return JSONResponse(
                status_code=400,
                content={"error": "没有上传文件"}
            )

        # 构建文件名描述
        if len(files) == 1:
            filename = os.path.basename(files[0].filename)
        else:
            first_filename = os.path.basename(files[0].filename)
            filename = f"{first_filename} 等 {len(files)} 个文件"

        # 确定日志中的学科类别
        log_source = source or "auto"

        # 记录上传开始
        log_id = qa_system.log_upload_start(filename, log_source)

        # 创建临时目录处理上传的文件
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            processed_files = []

            # 处理每个上传的文件
            for uploaded_file in files:
                # 安全处理文件名，防止路径遍历
                safe_filename = os.path.basename(uploaded_file.filename)
                file_path = temp_path / safe_filename

                # 保存上传的文件
                with open(file_path, "wb") as f:
                    content = await uploaded_file.read()
                    f.write(content)

                # 如果是zip文件，解压
                if is_zip or uploaded_file.filename.lower().endswith('.zip'):
                    zip_path = temp_path / "extracted"
                    zip_path.mkdir(exist_ok=True)
                    with zipfile.ZipFile(file_path, 'r') as zip_ref:
                        zip_ref.extractall(zip_path)
                    processed_files.append(str(zip_path))
                else:
                    processed_files.append(str(file_path))

            # 处理文档并添加到向量存储
            total_docs = 0
            for processed_path in processed_files:
                processed_path_obj = Path(processed_path)

                # 如果是目录，使用目录路径
                if processed_path_obj.is_dir():
                    directory_path = processed_path
                else:
                    # 如果是单个文件，创建以学科命名的子目录（模拟目录结构）
                    if source:
                        source_dir = temp_path / f"{source}_data"
                        source_dir.mkdir(exist_ok=True)
                        # 移动文件到学科目录，处理文件名冲突
                        base_name = processed_path_obj.name
                        new_path = source_dir / base_name
                        counter = 1
                        while new_path.exists():
                            # 添加数字后缀
                            stem = processed_path_obj.stem
                            suffix = processed_path_obj.suffix
                            new_path = source_dir / f"{stem}_{counter}{suffix}"
                            counter += 1
                        shutil.move(processed_path, new_path)
                        directory_path = str(source_dir)
                    else:
                        # 如果没有指定学科，使用文件名前缀
                        file_stem = processed_path_obj.stem
                        source_dir = temp_path / f"{file_stem}_data"
                        source_dir.mkdir(exist_ok=True)
                        # 移动文件到学科目录，处理文件名冲突
                        base_name = processed_path_obj.name
                        new_path = source_dir / base_name
                        counter = 1
                        while new_path.exists():
                            # 添加数字后缀
                            stem = processed_path_obj.stem
                            suffix = processed_path_obj.suffix
                            new_path = source_dir / f"{stem}_{counter}{suffix}"
                            counter += 1
                        shutil.move(processed_path, new_path)
                        directory_path = str(source_dir)

                # 导入文档处理模块
                from rag_qa.core.document_processor import process_documents

                # 处理文档
                documents = process_documents(directory_path)
                total_docs += len(documents)

                # 添加到向量存储
                vector_store = qa_system.vector_store
                vector_store.add_documents(documents)

                logger.info(f"从 {directory_path} 处理了 {len(documents)} 个文档块")

            # 记录上传完成
            if log_id:
                qa_system.log_upload_complete(log_id, total_docs)

            return {
                "status": "success",
                "message": f"成功处理 {len(files)} 个文件，生成 {total_docs} 个文档块并添加到知识库",
                "source": source or "auto",
                "total_documents": total_docs,
                "log_id": log_id
            }

    except Exception as e:
        logger.error(f"文件上传处理失败: {e}")
        # 记录上传失败
        if log_id:
            try:
                qa_system.log_upload_failed(log_id, str(e))
            except Exception as log_error:
                logger.error(f"记录上传失败日志时出错: {log_error}")

        return JSONResponse(
            status_code=500,
            content={"error": f"文件处理失败: {str(e)}"}
        )


# 获取知识库统计信息
@app.get("/api/knowledgebase/stats")
async def get_knowledgebase_stats():
    """获取向量存储的统计信息"""
    try:
        vector_store = qa_system.vector_store
        client = vector_store.client
        collection_name = vector_store.collection_name

        # 获取集合中的文档数量
        # 使用count_entities方法获取文档总数
        stats = client.get_collection_stats(collection_name)
        total_docs = stats.get("row_count", 0)

        # 获取按学科分组的文档数量
        sources_stats = {}
        for source in qa_system.config.VALID_SOURCES:
            try:
                # 使用query过滤获取该学科的文档数量
                result = client.query(
                    collection_name=collection_name,
                    filter=f"source == '{source}'",
                    output_fields=["id"],
                    limit=10000  # 设置较大限制以获取所有文档
                )
                count = len(result) if result else 0
                if count > 0:
                    sources_stats[source] = count
            except Exception as e:
                logger.warning(f"获取学科 {source} 统计失败: {e}")
                continue

        return {
            "collection_name": collection_name,
            "total_documents": total_docs,
            "sources": sources_stats,
            "valid_sources": qa_system.config.VALID_SOURCES
        }
    except Exception as e:
        logger.error(f"获取知识库统计信息失败: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"获取统计信息失败: {str(e)}"}
        )


# 删除知识库中指定学科的所有文档
@app.delete("/api/knowledgebase/{source}")
async def delete_knowledgebase_documents(source: str):
    """删除指定学科的所有文档"""
    try:
        # 验证学科类别
        valid_sources = qa_system.config.VALID_SOURCES
        if source not in valid_sources:
            return JSONResponse(
                status_code=400,
                content={"error": f"无效的学科类别。有效类别: {valid_sources}"}
            )

        vector_store = qa_system.vector_store
        client = vector_store.client
        collection_name = vector_store.collection_name

        # 删除指定学科的所有文档
        result = client.delete(
            collection_name=collection_name,
            filter=f"source == '{source}'"
        )

        # 记录删除操作
        logger.info(f"已删除学科 {source} 的所有文档，删除数量: {result.get('delete_count', 0)}")

        return {
            "status": "success",
            "message": f"已删除学科 {source} 的所有文档",
            "delete_count": result.get("delete_count", 0)
        }
    except Exception as e:
        logger.error(f"删除知识库文档失败: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"删除文档失败: {str(e)}"}
        )


# ========== 上传日志管理 API ==========

@app.get("/api/upload/logs")
async def get_upload_logs(
    source: Optional[str] = Query(None, description="按学科过滤"),
    limit: int = Query(50, ge=1, le=500, description="返回日志条数限制")
):
    """获取上传日志记录"""
    try:
        logs = qa_system.get_upload_logs(source=source, limit=limit)
        return {
            "status": "success",
            "logs": logs,
            "total": len(logs)
        }
    except Exception as e:
        logger.error(f"获取上传日志失败: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"获取上传日志失败: {str(e)}"}
        )


@app.delete("/api/upload/logs/{log_id}")
async def delete_upload_log(log_id: int):
    """删除上传日志记录"""
    try:
        deleted = qa_system.delete_upload_log(log_id)
        if deleted:
            return {
                "status": "success",
                "message": f"已删除日志记录 {log_id}"
            }
        else:
            return JSONResponse(
                status_code=404,
                content={"error": f"日志记录 {log_id} 不存在"}
            )
    except Exception as e:
        logger.error(f"删除上传日志失败: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"删除上传日志失败: {str(e)}"}
        )


@app.post("/api/upload/rollback/{log_id}")
async def rollback_upload(log_id: int):
    """回滚指定上传操作"""
    try:
        result = qa_system.rollback_upload(log_id)

        if result["success"]:
            return {
                "status": "success",
                "message": result["message"],
                "log_id": result.get("log_id"),
                "source": result.get("source"),
                "filename": result.get("filename"),
                "deleted_documents": result.get("deleted_documents", 0),
                "matched_documents": result.get("matched_documents", 0)
            }
        else:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": result["message"],
                    "log_id": result.get("log_id")
                }
            )
    except Exception as e:
        logger.error(f"回滚上传操作失败: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"回滚操作失败: {str(e)}",
                "log_id": log_id
            }
        )


# 获取有效的学科类别
@app.get("/api/sources")
async def get_sources():
    return {"sources": qa_system.config.VALID_SOURCES}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8001, reload=False)