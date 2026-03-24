# -*- coidng:utf-8 -*-
# 导入 MySQL 和 Redis 客户端，管理数据库和缓存
from mysql_qa import MySQLClient, RedisClient, BM25Search
# 导入 RAG 系统组件，用于知识库检索和答案生成
from rag_qa import VectorStore, RAGSystem
# 导入配置和日志工具，用于系统配置和日志记录
from base import logger, Config
# 导入 OpenAI 客户端，用于调用 DashScope API
from openai import OpenAI
# 导入时间库，用于记录处理时间
import time
# 导入 UUID 库，生成唯一会话 ID
import uuid
# 导入 pymysql 错误处理，用于数据库操作的异常捕获
import pymysql
class IntegratedQASystem:
    def __init__(self):
        # 初始化日志工具，用于记录系统运行信息
        self.logger = logger
        # 初始化配置对象，加载系统参数
        self.config = Config()
        # 初始化 MySQL 客户端，用于数据库操作
        self.mysql_client = MySQLClient()
        # 初始化 Redis 客户端，用于缓存管理
        self.redis_client = RedisClient()
        # 初始化 BM25 搜索模块，结合 MySQL 和 Redis
        self.bm25_search = BM25Search(self.redis_client, self.mysql_client)
        try:
            # 初始化 OpenAI 客户端，连接 DashScope API
            self.client = OpenAI(api_key=self.config.DASHSCOPE_API_KEY,
                                 base_url=self.config.DASHSCOPE_BASE_URL)
        except Exception as e:
            # 记录 OpenAI 初始化失败的错误日志
            self.logger.error(f"OpenAI 客户端初始化失败: {e}")
            # 抛出异常，终止初始化
            raise
        # 初始化向量存储，用于 RAG 系统的知识库管理
        self.vector_store = VectorStore()
        # 初始化 RAG 系统，传入向量存储和 DashScope API 调用函数
        self.rag_system = RAGSystem(self.vector_store, self.call_dashscope)
        # 初始化对话历史表，用于存储会话记录
        self.init_conversation_table()
        # 初始化上传日志表，用于记录文件上传操作
        self.init_upload_logs_table()

    def init_conversation_table(self):
        """初始化MySQL中的conversations表，用于存储对话历史"""
        try:
            # 确保数据库连接有效
            self.mysql_client.ensure_connection()
            # 创建 conversations 表，包含会话 ID、问题、答案和时间戳
            self.mysql_client.cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    session_id VARCHAR(36) NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    timestamp DATETIME NOT NULL,
                    INDEX idx_session_id (session_id)
                )
            """)
            # 提交数据库事务
            self.mysql_client.connection.commit()
            # 记录表初始化成功的日志
            self.logger.info("对话历史表初始化成功")
        except pymysql.MySQLError as e:
            # 记录表初始化失败的错误日志
            self.logger.error(f"初始化对话历史表失败: {e}")
            # 抛出异常，终止初始化
            raise

    def init_upload_logs_table(self):
        """初始化MySQL中的upload_logs表，用于存储文件上传日志"""
        try:
            # 确保数据库连接有效
            self.mysql_client.ensure_connection()
            # 创建 upload_logs 表
            self.mysql_client.cursor.execute("""
                CREATE TABLE IF NOT EXISTS upload_logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    filename VARCHAR(255) NOT NULL,
                    source VARCHAR(50) NOT NULL,
                    document_count INT DEFAULT 0,
                    status ENUM('processing', 'success', 'failed') DEFAULT 'processing',
                    start_time DATETIME NOT NULL,
                    end_time DATETIME NULL,
                    error_message TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_source (source),
                    INDEX idx_status (status),
                    INDEX idx_created_at (created_at)
                )
            """)
            # 提交数据库事务
            self.mysql_client.connection.commit()
            # 记录表初始化成功的日志
            self.logger.info("上传日志表初始化成功")
        except pymysql.MySQLError as e:
            # 记录表初始化失败的错误日志
            self.logger.error(f"初始化上传日志表失败: {e}")
            # 抛出异常，终止初始化
            raise

    # ========== 上传日志管理方法 ==========

    def log_upload_start(self, filename: str, source: str) -> int:
        """记录上传开始，返回日志ID"""
        try:
            self.mysql_client.ensure_connection()
            import datetime
            start_time = datetime.datetime.now()

            self.mysql_client.cursor.execute("""
                INSERT INTO upload_logs (filename, source, status, start_time)
                VALUES (%s, %s, 'processing', %s)
            """, (filename, source, start_time))

            self.mysql_client.connection.commit()
            log_id = self.mysql_client.cursor.lastrowid
            self.logger.info(f"上传开始记录，日志ID: {log_id}, 文件: {filename}, 学科: {source}")
            return log_id
        except pymysql.MySQLError as e:
            self.logger.error(f"记录上传开始失败: {e}")
            self.mysql_client.connection.rollback()
            raise

    def log_upload_complete(self, log_id: int, document_count: int):
        """记录上传完成"""
        try:
            self.mysql_client.ensure_connection()
            import datetime
            end_time = datetime.datetime.now()

            self.mysql_client.cursor.execute("""
                UPDATE upload_logs
                SET status = 'success', end_time = %s, document_count = %s
                WHERE id = %s
            """, (end_time, document_count, log_id))

            self.mysql_client.connection.commit()
            self.logger.info(f"上传完成记录，日志ID: {log_id}, 文档数: {document_count}")
        except pymysql.MySQLError as e:
            self.logger.error(f"记录上传完成失败: {e}")
            self.mysql_client.connection.rollback()
            raise

    def log_upload_failed(self, log_id: int, error_message: str):
        """记录上传失败"""
        try:
            self.mysql_client.ensure_connection()
            import datetime
            end_time = datetime.datetime.now()

            self.mysql_client.cursor.execute("""
                UPDATE upload_logs
                SET status = 'failed', end_time = %s, error_message = %s
                WHERE id = %s
            """, (end_time, error_message, log_id))

            self.mysql_client.connection.commit()
            self.logger.info(f"上传失败记录，日志ID: {log_id}, 错误: {error_message}")
        except pymysql.MySQLError as e:
            self.logger.error(f"记录上传失败失败: {e}")
            self.mysql_client.connection.rollback()
            raise

    def get_upload_logs(self, source: str = None, limit: int = 50) -> list:
        """获取上传日志"""
        try:
            self.mysql_client.ensure_connection()

            if source:
                self.mysql_client.cursor.execute("""
                    SELECT id, filename, source, document_count, status,
                           start_time, end_time, error_message, created_at
                    FROM upload_logs
                    WHERE source = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (source, limit))
            else:
                self.mysql_client.cursor.execute("""
                    SELECT id, filename, source, document_count, status,
                           start_time, end_time, error_message, created_at
                    FROM upload_logs
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (limit,))

            # 获取列名
            columns = [desc[0] for desc in self.mysql_client.cursor.description]
            rows = self.mysql_client.cursor.fetchall()

            # 转换为字典列表
            logs = []
            for row in rows:
                log_dict = dict(zip(columns, row))
                # 将datetime对象转换为字符串
                for key in ['start_time', 'end_time', 'created_at']:
                    if log_dict.get(key) and hasattr(log_dict[key], 'isoformat'):
                        log_dict[key] = log_dict[key].isoformat()
                logs.append(log_dict)

            return logs
        except pymysql.MySQLError as e:
            self.logger.error(f"获取上传日志失败: {e}")
            return []

    def delete_upload_log(self, log_id: int) -> bool:
        """删除上传日志记录"""
        try:
            self.mysql_client.ensure_connection()
            self.mysql_client.cursor.execute("DELETE FROM upload_logs WHERE id = %s", (log_id,))
            self.mysql_client.connection.commit()
            deleted = self.mysql_client.cursor.rowcount > 0
            if deleted:
                self.logger.info(f"删除上传日志记录，ID: {log_id}")
            return deleted
        except pymysql.MySQLError as e:
            self.logger.error(f"删除上传日志失败: {e}")
            self.mysql_client.connection.rollback()
            return False

    def rollback_upload(self, log_id: int) -> dict:
        """
        回滚指定上传操作

        根据上传日志的时间范围，删除对应时间段内上传的文档
        """
        try:
            self.mysql_client.ensure_connection()

            # 获取上传日志信息
            self.mysql_client.cursor.execute("""
                SELECT filename, source, start_time, end_time, document_count
                FROM upload_logs
                WHERE id = %s AND status = 'success'
            """, (log_id,))

            log_info = self.mysql_client.cursor.fetchone()
            if not log_info:
                return {
                    "success": False,
                    "message": "日志不存在或上传未成功"
                }

            filename, source, start_time, end_time, document_count = log_info

            # 如果没有结束时间，使用当前时间
            if not end_time:
                import datetime
                end_time = datetime.datetime.now()

            # 将时间转换为ISO格式字符串（用于Milvus过滤）
            start_iso = start_time.isoformat() if hasattr(start_time, 'isoformat') else str(start_time)
            end_iso = end_time.isoformat() if hasattr(end_time, 'isoformat') else str(end_time)

            # 从向量存储中删除对应时间段内该学科的文档
            vector_store = self.vector_store
            client = vector_store.client
            collection_name = vector_store.collection_name

            # 构建过滤条件：指定学科且在时间范围内
            filter_expr = f"source == '{source}' AND timestamp >= '{start_iso}' AND timestamp <= '{end_iso}'"

            # 先查询匹配的文档数量
            result = client.query(
                collection_name=collection_name,
                filter=filter_expr,
                output_fields=["id"],
                limit=10000
            )

            matched_count = len(result) if result else 0

            if matched_count > 0:
                # 执行删除
                delete_result = client.delete(
                    collection_name=collection_name,
                    filter=filter_expr
                )

                deleted_count = delete_result.get("delete_count", 0)
                self.logger.info(f"回滚上传成功，日志ID: {log_id}, 删除文档数: {deleted_count}")

                # 更新日志状态为已回滚（添加备注）
                self.mysql_client.cursor.execute("""
                    UPDATE upload_logs
                    SET error_message = CONCAT(IFNULL(error_message, ''), ' [ROLLBACK]')
                    WHERE id = %s
                """, (log_id,))
                self.mysql_client.connection.commit()

                return {
                    "success": True,
                    "message": f"成功回滚上传操作，删除了 {deleted_count} 个文档",
                    "log_id": log_id,
                    "source": source,
                    "filename": filename,
                    "deleted_documents": deleted_count,
                    "matched_documents": matched_count
                }
            else:
                self.logger.warning(f"回滚上传未找到匹配文档，日志ID: {log_id}")
                return {
                    "success": True,
                    "message": "未找到需要删除的文档，可能已被删除",
                    "log_id": log_id,
                    "source": source,
                    "filename": filename,
                    "deleted_documents": 0,
                    "matched_documents": 0
                }

        except Exception as e:
            self.logger.error(f"回滚上传操作失败: {e}")
            return {
                "success": False,
                "message": f"回滚失败: {str(e)}",
                "log_id": log_id
            }

    # ========== 原有方法 ==========

    def call_dashscope(self, prompt):
        """调用DashScope API生成答案（流式输出）"""
        try:
            # 创建聊天完成请求，启用流式输出
            completion = self.client.chat.completions.create(
                model=self.config.LLM_MODEL,  # 使用配置中的语言模型
                messages=[
                    {"role": "system", "content": "你是一个有用的助手。"},  # 系统提示
                    {"role": "user", "content": prompt},  # 用户输入的提示
                ],
                timeout=30,  # 设置 30 秒超时
                stream=True  # 启用流式输出
            )
            # 遍历流式输出的每个 chunk
            for chunk in completion:
                # print(f'chunk--》{chunk}')
                # print("*"*80)
                if chunk.choices and chunk.choices[0].delta.content:
            #         # 获取当前 chunk 的内容
                    content = chunk.choices[0].delta.content
                    yield content
        except Exception as e:
            # 记录 API 调用失败的错误日志
            self.logger.error(f"LLM调用失败: {e}")
            # 返回错误信息
            return f"错误：LLM调用失败 - {e}"

    def _fetch_recent_history(self, session_id):
        """获取最近5轮对话历史"""
        try:
            # 确保数据库连接有效
            self.mysql_client.ensure_connection()
            # 执行 SQL 查询，获取最近 5 轮对话
            self.mysql_client.cursor.execute("""
                      SELECT question, answer
                      FROM conversations
                      WHERE session_id = %s
                      ORDER BY timestamp DESC
                      LIMIT %s
                  """, (session_id, 5))
            # print(f'self.mysql_client.cursor.fetchall()---》{self.mysql_client.cursor.fetchall()}')
            # 使用 fetchmany 替代 fetchall，分批获取结果
            rows = self.mysql_client.cursor.fetchmany(5)
            # 将查询结果转换为字典列表
            history = [{"question": row[0], "answer": row[1]} for row in rows]
            # 将查询结果转换为字典列表
            # history = [{"question": row[0], "answer": row[1]} for row in self.mysql_client.cursor.fetchall()]
            # 反转结果，按时间正序返回
            return history[::-1]

        except pymysql.MySQLError as e:
            # 记录查询失败的错误日志
            self.logger.error(f"获取对话历史失败: {e}")
            # 返回空列表
            return []

    def get_session_history(self, session_id ):
        """从MySQL获取会话历史"""
        # 调用 _fetch_recent_history 获取对话历史
        return self._fetch_recent_history(session_id)

    def update_session_history(self, session_id: str, question: str, answer: str) -> list:
        """更新会话历史到MySQL，保留最近5轮对话"""
        try:
            # 确保数据库连接有效
            self.mysql_client.ensure_connection()
            # 插入新的对话记录
            self.mysql_client.cursor.execute("""
                INSERT INTO conversations (session_id, question, answer, timestamp)
                VALUES (%s, %s, %s, NOW())
            """, (session_id, question, answer))
            # 获取更新后的对话历史
            history = self._fetch_recent_history(session_id)
            # 删除超出 5 轮的旧记录
            self.mysql_client.cursor.execute("""
                DELETE FROM conversations
                WHERE session_id = %s AND id NOT IN (
                    SELECT id FROM (
                        SELECT id
                        FROM conversations
                        WHERE session_id = %s
                        ORDER BY timestamp DESC
                        LIMIT %s
                    ) AS sub
                )
            """, (session_id, session_id, 5))
            # 提交事务
            self.mysql_client.connection.commit()
            # 记录更新成功的日志
            self.logger.info(f"会话 {session_id} 历史更新成功")
            # 返回更新后的历史
            return history
        except pymysql.MySQLError as e:
            # 记录数据库操作失败的错误日志
            self.logger.error(f"更新会话历史失败: {e}")
            # 回滚事务
            self.mysql_client.connection.rollback()
            # 抛出异常
            raise
        except Exception as e:
            # 记录意外错误的日志
            self.logger.error(f"更新会话历史意外错误: {e}")
            # 回滚事务
            self.mysql_client.connection.rollback()
            # 抛出异常
            raise

    def clear_session_history(self, session_id: str) -> bool:
        """清除指定会话历史"""
        try:
            # 确保数据库连接有效
            self.mysql_client.ensure_connection()
            # 删除指定 session_id 的所有对话记录
            self.mysql_client.cursor.execute("""
                DELETE FROM conversations
                WHERE session_id = %s
            """, (session_id,))
            # 提交事务
            self.mysql_client.connection.commit()
            # 记录清除成功的日志
            self.logger.info(f"会话 {session_id} 历史已清除")
            # 返回 True 表示成功
            return True
        except pymysql.MySQLError as e:
            # 记录清除失败的错误日志
            self.logger.error(f"清除会话历史失败: {e}")
            # 回滚事务
            self.mysql_client.connection.rollback()
            # 返回 False 表示失败
            return False


    def query(self, query, source_filter=None, session_id=None):
        # print(f'你好')
        """查询集成系统，支持对话历史和流式输出"""
        start_time = time.time()  # 记录查询开始时间
        # 记录查询信息到日志
        self.logger.info(f"处理查询: '{query}' (会话ID: {session_id})")
        # 获取对话历史，若无 session_id 则返回空列表
        history = self.get_session_history(session_id) if session_id else []
        # print(f'history--->{history}')
        # 执行 BM25 搜索，获取答案和是否需要 RAG 的标志
        answer, need_rag = self.bm25_search.search(query, threshold=0.85)
        # print(f'answer-——》{answer}')
        # print(f'need_rag-——》{need_rag}')
        if answer:
            # 如果找到可靠答案，记录答案到日志
            self.logger.info(f"MySQL答案: {answer}")
            if session_id:
                # 更新对话历史
                self.update_session_history(session_id, query, answer)
            # 计算处理时间
            processing_time = time.time() - start_time
            # 记录处理时间到日志
            self.logger.info(f"查询处理耗时 {processing_time:.2f}秒")
            # 一次性返回答案，标记为完整
            yield answer, True
        elif need_rag:
            self.logger.info("无可靠MySQL答案，回退到RAG")
            # 初始化收集完整答案的字符串
            collected_answer = ""
            # 从 RAG 系统获取流式输出
            for token in self.rag_system.generate_answer(query, source_filter=source_filter, history=history):
                # 累积答案
                collected_answer += token
                # 逐 token 返回，标记为部分答案
                yield token, False
            if session_id:
                # 更新对话历史，存储完整答案
                self.update_session_history(session_id, query, collected_answer)
            # 计算处理时间
            processing_time = time.time() - start_time
            # 记录处理时间到日志
            self.logger.info(f"查询处理耗时 {processing_time:.2f}秒")
            # 返回空字符串，标记流结束
            yield "", True
        else:
            # 如果无答案，记录信息到日志
            self.logger.info("未找到答案")
            # 计算处理时间
            processing_time = time.time() - start_time
            # 记录处理时间到日志
            self.logger.info(f"查询处理耗时 {processing_time:.2f}秒")
            # 一次性返回默认答案，标记为完整
            yield "未找到答案", True

def main():
    # 定义主函数，提供命令行交互界面
    qa_system = IntegratedQASystem()  # 初始化问答系统
    # 生成唯一会话 ID
    session_id = str(uuid.uuid4())
    # 打印欢迎信息
    print("\n欢迎使用集成问答系统！")
    # 打印会话 ID
    print(f"会话ID: {session_id}")
    # 打印支持的学科类别
    print(f"支持的学科类别：{qa_system.config.VALID_SOURCES}")
    # 提示用户输入查询或退出
    print("输入查询进行问答，输入 'exit' 退出。")
    try:
        while True:
            # 获取用户输入的查询
            query = input("\n输入查询: ").strip()
            if query.lower() == "exit":
                # 如果用户输入 exit，记录退出日志
                logger.info("退出系统")
                # 打印退出信息
                print("再见！")
                # 退出循环
                break
            # 获取用户输入的学科过滤
            source_filter = input(f"请输入学科类别 ({'/'.join(qa_system.config.VALID_SOURCES)}) (直接回车默认不过滤): ").strip()
            if source_filter and source_filter not in qa_system.config.VALID_SOURCES:
                # 如果学科过滤无效，记录警告日志
                logger.warning(f"无效的学科类别 '{source_filter}'，将不过滤")
                # 设置为空，忽略过滤
                source_filter = None
            # 打印答案提示
            print("\n答案: ", end="", flush=True)
            # 初始化累积答案的字符串
            answer = ""
            # 迭代 query 方法的生成器
            for token, is_complete in qa_system.query(query, source_filter=source_filter, session_id=session_id):
                if token:
                    # 仅当 token 非空时打印
                    print(token, end="", flush=True)
                    # 累积答案
                    answer += token
                if is_complete:
                    # 如果是完整答案或流结束，换行并退出循环
                    print()
                    break
            # 打印对话历史
            history = qa_system.get_session_history(session_id)
            print("\n最近对话历史:")
            for idx, entry in enumerate(history, 1):
                # 按顺序打印历史记录
                print(f"{idx}. 问: {entry['question']}\n   答: {entry['answer']}")
    except Exception as e:
        # 记录系统错误日志
        logger.error(f"系统错误: {e}")
        # 打印错误信息
        print(f"发生错误: {e}")
    finally:
        # 关闭 MySQL 连接
        qa_system.mysql_client.close()

if __name__ == "__main__":
    # new_qa_system = IntegratedQASystem()
    # new_qa_system.call_dashscope(prompt="什么是AI")
    # answer = new_qa_system.query(query='什么是AI', session_id="603db0cf-cfa0-4433-9078-f37f3b29fd7c")
    # for value in answer:
    #     print(value)
    # results = new_qa_system._fetch_recent_history(session_id="603db0cf-cfa0-4433-9078-f37f3b29fd7c")
    # print(results)
    main()