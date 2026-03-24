# -*-coding:utf-8-*-
# core/rag_agent.py - 最小可行Agent实现
import sys
import os
import time
from typing import List, Dict, Any, Optional

# 获取当前文件所在目录的绝对路径
current_dir = os.path.dirname(os.path.abspath(__file__))
# print(f'current_dir--》{current_dir}')
# 获取core文件所在的目录的绝对路径
rag_qa_path = os.path.dirname(current_dir)
# print(f'rag_qa_path--》{rag_qa_path}')
sys.path.insert(0, rag_qa_path)
# 获取根目录文件所在的绝对位置
project_root = os.path.dirname(rag_qa_path)
sys.path.insert(0, project_root)

from base import logger, Config
from core.new_rag_system import RAGSystem

conf = Config()


class RAGAgent:
    """
    最小可行Agent实现
    实现基本的思考-行动-观察循环
    """

    def __init__(self, vector_store, llm):
        """
        初始化Agent

        Args:
            vector_store: 向量存储实例
            llm: 大语言模型调用函数（非流式，返回字符串）
        """
        # 基础组件
        self.vector_store = vector_store
        self.llm = llm  # 非流式LLM函数

        # 将非流式LLM包装为流式函数（兼容RAGSystem接口）
        def stream_llm_wrapper(prompt):
            # 非流式调用，返回包含单个字符串的列表
            result = llm(prompt)
            yield result

        # 内部RAG系统（复用现有逻辑）
        self.rag_system = RAGSystem(vector_store, stream_llm_wrapper, agent_mode=False)

        # 对话记忆（简单的列表记忆）
        self.conversation_history: List[Dict[str, str]] = []

        # 最大记忆轮数
        self.max_history_turns = 5

        logger.info("RAGAgent初始化完成")

    def _think(self, query: str) -> Dict[str, Any]:
        """
        思考阶段：分析查询，决定行动策略

        Args:
            query: 用户查询

        Returns:
            思考结果字典，包含策略和元数据
        """
        logger.info(f"Agent思考阶段 - 查询: '{query}'")

        # 分析查询复杂度
        complexity = self._analyze_query_complexity(query)

        # 检查是否需要检索（基于对话历史）
        need_retrieval = self._decide_if_need_retrieval(query)

        # 选择检索策略
        if need_retrieval:
            strategy = self._select_retrieval_strategy(query, complexity)
        else:
            strategy = "direct_llm"  # 直接使用LLM，无需检索

        # 构建思考结果
        thought = {
            "query": query,
            "complexity": complexity,
            "need_retrieval": need_retrieval,
            "strategy": strategy,
            "timestamp": time.time()
        }

        logger.info(f"Agent思考结果: {thought}")
        return thought

    def _act(self, thought: Dict[str, Any], source_filter: Optional[str] = None) -> Dict[str, Any]:
        """
        行动阶段：执行思考结果

        Args:
            thought: 思考结果
            source_filter: 学科过滤

        Returns:
            行动结果字典，包含检索结果和元数据
        """
        logger.info(f"Agent行动阶段 - 策略: {thought['strategy']}")

        action_result = {
            "thought": thought,
            "retrieved_docs": [],
            "context": "",
            "execution_time": 0
        }

        start_time = time.time()

        try:
            if thought["strategy"] == "direct_llm":
                # 无需检索，直接使用LLM
                logger.info("使用直接LLM策略")
                action_result["context"] = ""

            elif thought["strategy"] in ["direct", "hyde", "subquery", "backtracking"]:
                # 使用RAG系统检索
                logger.info(f"使用RAG检索策略: {thought['strategy']}")

                # 调用RAG系统检索
                context_docs = self.rag_system.retrieve_and_merge(
                    query=thought["query"],
                    source_filter=source_filter,
                    strategy=self._map_strategy_name(thought["strategy"])
                )

                action_result["retrieved_docs"] = context_docs

                # 构建上下文
                if context_docs:
                    context = "\n\n".join([doc.page_content for doc in context_docs])
                    action_result["context"] = context
                    logger.info(f"检索到 {len(context_docs)} 个相关文档")
                else:
                    action_result["context"] = ""
                    logger.info("未检索到相关文档")

            else:
                # 未知策略，降级为直接检索
                logger.warning(f"未知策略 {thought['strategy']}，降级为直接检索")
                context_docs = self.rag_system.retrieve_and_merge(
                    query=thought["query"],
                    source_filter=source_filter,
                    strategy=None  # 使用默认策略选择
                )

                if context_docs:
                    context = "\n\n".join([doc.page_content for doc in context_docs])
                    action_result["context"] = context
                    action_result["retrieved_docs"] = context_docs

        except Exception as e:
            logger.error(f"Agent行动阶段失败: {e}")
            action_result["error"] = str(e)
            action_result["context"] = ""

        action_result["execution_time"] = time.time() - start_time
        logger.info(f"Agent行动完成，耗时: {action_result['execution_time']:.2f}s")

        return action_result

    def _observe_and_synthesize(self, thought: Dict[str, Any], action_result: Dict[str, Any]) -> str:
        """
        观察和综合阶段：生成最终答案

        Args:
            thought: 思考结果
            action_result: 行动结果

        Returns:
            最终答案文本
        """
        logger.info("Agent观察和综合阶段")

        # 准备Prompt
        if thought["strategy"] == "direct_llm" or not action_result.get("context"):
            # 无上下文，直接回答
            prompt = f"请回答以下问题：\n\n问题：{thought['query']}\n\n请直接给出答案。"
        else:
            # 有上下文，使用RAG格式
            from core.prompts import RAGPrompts
            rag_prompt = RAGPrompts.rag_prompt()
            prompt = rag_prompt.format(
                context=action_result.get("context", ""),
                question=thought["query"],
                phone=conf.CUSTOMER_SERVICE_PHONE
            )

        # 调用LLM生成答案
        try:
            answer = self.llm(prompt)
            logger.info("Agent成功生成答案")
        except Exception as e:
            logger.error(f"Agent生成答案失败: {e}")
            answer = f"抱歉，处理您的问题时出错。请联系人工客服：{conf.CUSTOMER_SERVICE_PHONE}"

        return answer

    def process_query(self, query: str, source_filter: Optional[str] = None, history: Optional[List[Dict[str, str]]] = None) -> str:
        """
        处理用户查询的完整Agent流程

        Args:
            query: 用户查询
            source_filter: 学科过滤
            history: 外部对话历史，格式: [{"question": "...", "answer": "..."}, ...]

        Returns:
            最终答案
        """
        logger.info(f"Agent开始处理查询: '{query}'")

        # 如果有外部历史，合并到内部对话历史中
        if history:
            self._merge_external_history(history)

        # 1. 思考：分析查询，决定策略
        thought = self._think(query)

        # 2. 行动：执行策略，获取上下文
        action_result = self._act(thought, source_filter)

        # 3. 观察和综合：生成答案
        answer = self._observe_and_synthesize(thought, action_result)

        # 4. 更新对话历史
        self._update_conversation_history(query, answer, thought, action_result)

        logger.info(f"Agent处理完成，查询: '{query[:50]}...'")
        return answer

    def _analyze_query_complexity(self, query: str) -> str:
        """
        分析查询复杂度

        Args:
            query: 用户查询

        Returns:
            复杂度等级: "simple", "medium", "complex"
        """
        # 简单启发式规则
        query_length = len(query)

        if query_length < 20:
            return "simple"
        elif query_length < 50:
            return "medium"
        else:
            return "complex"

    def _decide_if_need_retrieval(self, query: str) -> bool:
        """
        决定是否需要检索

        Args:
            query: 用户查询

        Returns:
            True如果需要检索，False如果可以直接用LLM回答
        """
        # 检查对话历史中是否有相关信息
        if self.conversation_history:
            last_turn = self.conversation_history[-1]
            # 如果上一个问题是相关的，且当前问题是追问
            if self._is_follow_up_query(query, last_turn["query"]):
                # 可以使用历史上下文，可能不需要重新检索
                return False

        # 检查是否是通用知识问题（复用现有分类器）
        try:
            # 使用RAG系统的查询分类器
            category = self.rag_system.query_classifier.predict_category(query)
            if category == "通用知识":
                return False
        except:
            # 分类器失败，保守起见进行检索
            pass

        # 默认需要检索
        return True

    def _select_retrieval_strategy(self, query: str, complexity: str) -> str:
        """
        选择检索策略

        Args:
            query: 用户查询
            complexity: 查询复杂度

        Returns:
            策略名称: "direct", "hyde", "subquery", "backtracking"
        """
        # 基于复杂度的简单策略选择
        if complexity == "simple":
            return "direct"
        elif complexity == "medium":
            # 中等复杂度，随机选择增强策略用于测试
            import random
            strategies = ["direct", "hyde", "subquery", "backtracking"]
            return random.choice(strategies[1:])  # 排除direct
        else:  # complex
            # 复杂查询使用子查询或回溯
            import random
            return random.choice(["subquery", "backtracking"])

    def _map_strategy_name(self, agent_strategy: str) -> Optional[str]:
        """
        将Agent策略名称映射到RAG系统策略名称

        Args:
            agent_strategy: Agent内部策略名称

        Returns:
            RAG系统策略名称
        """
        mapping = {
            "direct": None,  # None表示使用默认策略选择
            "hyde": "假设问题检索",
            "subquery": "子查询检索",
            "backtracking": "回溯问题检索"
        }
        return mapping.get(agent_strategy, None)

    def _is_follow_up_query(self, current_query: str, previous_query: str) -> bool:
        """
        判断当前查询是否是上一个查询的追问

        Args:
            current_query: 当前查询
            previous_query: 上一个查询

        Returns:
            True如果是追问
        """
        # 简单规则：检查是否包含指代词
        follow_up_keywords = ["它", "这个", "那个", "上述", "之前", "上面", "下面", "接着"]

        for keyword in follow_up_keywords:
            if keyword in current_query:
                return True

        # 检查是否是简短追问
        if len(current_query) < 15 and len(previous_query) > 20:
            return True

        return False

    def _update_conversation_history(self, query: str, answer: str,
                                    thought: Dict[str, Any],
                                    action_result: Dict[str, Any]):
        """
        更新对话历史

        Args:
            query: 用户查询
            answer: 助手回答
            thought: 思考结果
            action_result: 行动结果
        """
        turn = {
            "query": query,
            "answer": answer,
            "thought": thought,
            "action_result": {
                "strategy": thought["strategy"],
                "retrieved_docs_count": len(action_result.get("retrieved_docs", [])),
                "execution_time": action_result.get("execution_time", 0)
            },
            "timestamp": time.time()
        }

        self.conversation_history.append(turn)

        # 限制历史长度
        if len(self.conversation_history) > self.max_history_turns:
            self.conversation_history = self.conversation_history[-self.max_history_turns:]

        logger.info(f"对话历史更新，当前轮数: {len(self.conversation_history)}")

    def _merge_external_history(self, external_history: List[Dict[str, str]]):
        """
        合并外部对话历史到内部对话历史中

        Args:
            external_history: 外部对话历史，格式: [{"question": "...", "answer": "..."}, ...]
        """
        if not external_history:
            return

        logger.info(f"合并外部对话历史，共 {len(external_history)} 轮")

        # 将外部历史转换为内部格式
        for i, turn in enumerate(external_history):
            if "question" in turn and "answer" in turn:
                internal_turn = {
                    "query": turn["question"],
                    "answer": turn["answer"],
                    "thought": {
                        "query": turn["question"],
                        "complexity": "unknown",
                        "need_retrieval": True,
                        "strategy": "unknown",
                        "timestamp": time.time() - (len(external_history) - i) * 60  # 模拟时间戳
                    },
                    "action_result": {
                        "strategy": "unknown",
                        "retrieved_docs_count": 0,
                        "execution_time": 0.5
                    },
                    "timestamp": time.time() - (len(external_history) - i) * 60
                }
                self.conversation_history.append(internal_turn)

        # 限制历史长度
        if len(self.conversation_history) > self.max_history_turns * 2:  # 允许更多历史
            self.conversation_history = self.conversation_history[-self.max_history_turns * 2:]

        logger.info(f"历史合并完成，当前总轮数: {len(self.conversation_history)}")

    def get_conversation_summary(self) -> Dict[str, Any]:
        """
        获取对话摘要

        Returns:
            对话摘要字典
        """
        return {
            "total_turns": len(self.conversation_history),
            "strategies_used": [turn["action_result"]["strategy"] for turn in self.conversation_history],
            "avg_execution_time": sum(turn["action_result"]["execution_time"] for turn in self.conversation_history) / max(len(self.conversation_history), 1)
        }


if __name__ == '__main__':
    # 测试代码
    print("测试RAGAgent...")

    # 这里需要实际环境才能运行
    # vector_store = VectorStore()
    # llm = lambda prompt: f"测试回答: {prompt[:50]}..."
    # agent = RAGAgent(vector_store, llm)
    # answer = agent.process_query("什么是人工智能？")
    # print(f"答案: {answer}")

    print("测试完成（需要实际环境运行）")