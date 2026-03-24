# 演示脚本：混合检索问答系统现场演示

## 🎬 演示概览

**演示时长**：15-20分钟
**目标受众**：技术面试官、技术负责人
**演示形式**：现场操作 + 架构讲解 + 问答互动
**核心亮点**：智能路由、混合检索、企业级特性

## 📋 演示前准备

### 环境检查
```bash
# 1. 检查服务状态
curl http://localhost:8001/health
# 预期输出：{"status": "healthy", "timestamp": "2025-03-25T10:30:00"}

# 2. 检查API文档
# 浏览器打开：http://localhost:8001/docs

# 3. 检查数据状态
python check_demo_data.py
```

### 数据准备
- MySQL中已导入：10万条教育QA数据（AI、Java、大数据等学科）
- Milvus中已向量化：5千份教学文档（PDF、Word、PPT）
- Redis缓存已预热：热门问题结果缓存

## 🚀 演示流程

### 第一阶段：架构概览（3分钟）

**讲解要点**：
1. **问题背景**：传统问答系统速度与准确率难以兼得
2. **解决方案**：混合检索架构 - MySQL快 + RAG准
3. **核心创新**：BERT智能路由，自动选择最佳检索策略

**可视化展示**：
```bash
# 展示系统架构图
cat docs/architecture.png  # 或直接打开浏览器展示
```

### 第二阶段：基础功能演示（5分钟）

#### 演示1：简单问题 - MySQL快速检索（<100ms）
```bash
# 使用curl测试
curl -X POST "http://localhost:8001/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Python是什么编程语言？",
    "source_filter": "ai"
  }'
```

**预期结果**：
- 响应时间：<100ms
- 答案来源：MySQL BM25检索
- 特点：快速、准确、无LLM生成痕迹

**讲解要点**：
- 展示MySQL检索的毫秒级响应
- 解释BM25算法原理
- 强调对简单问题的高效处理

#### 演示2：复杂问题 - RAG语义检索（1-3s）
```bash
curl -X POST "http://localhost:8001/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "请对比机器学习和深度学习的异同，并给出实际应用案例",
    "source_filter": "ai"
  }'
```

**预期结果**：
- 响应时间：1-3秒
- 答案来源：RAG生成（向量检索 + LLM生成）
- 特点：深度语义理解、结构化答案

**讲解要点**：
- 展示RAG对复杂问题的处理能力
- 解释向量检索流程
- 强调生成式答案的灵活性

### 第三阶段：高级功能演示（5分钟）

#### 演示3：智能路由展示
```python
# 演示脚本：智能路由决策过程
import requests
import time

test_cases = [
    ("Python是什么？", "简单问题 → MySQL检索"),
    ("如何实现神经网络的反向传播？", "中等复杂度 → 可能RAG"),
    ("请设计一个完整的推荐系统架构，需要考虑冷启动问题和实时性要求", "复杂问题 → RAG检索")
]

for query, expected in test_cases:
    print(f"\n问题: {query}")
    print(f"预期: {expected}")

    start = time.time()
    response = requests.post(
        "http://localhost:8001/query",
        json={"query": query, "source_filter": "ai"}
    )
    elapsed = time.time() - start

    print(f"实际响应时间: {elapsed:.3f}s")
    print(f"推断策略: {'MySQL' if elapsed < 0.2 else 'RAG'}")
```

**讲解要点**：
- BERT分类器的工作原理
- 响应时间与检索策略的关联
- 智能路由的准确率（可展示分类器评估报告）

#### 演示4：会话历史与多轮对话
```bash
# 生成会话ID
SESSION_ID=$(python -c "import uuid; print(uuid.uuid4())")
echo "会话ID: $SESSION_ID"

# 第一轮对话
curl -X POST "http://localhost:8001/query" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"什么是机器学习？\",
    \"session_id\": \"$SESSION_ID\"
  }"

# 第二轮对话（依赖上下文）
curl -X POST "http://localhost:8001/query" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"它有哪些主要算法？\",
    \"session_id\": \"$SESSION_ID\"
  }"
```

**讲解要点**：
- 会话历史在MySQL中的存储结构
- 上下文感知的问答机制
- 实际应用场景：学习辅导、技术支持

#### 演示5：文档上传与管理
```bash
# 上传PDF文档
curl -X POST "http://localhost:8001/api/upload" \
  -F "files=@docs/机器学习教程.pdf" \
  -F "source=ai"

# 查看上传日志
curl "http://localhost:8001/api/upload/logs?source=ai&limit=5"

# 演示回滚功能（需要具体的log_id）
# curl -X POST "http://localhost:8001/api/upload/rollback/123"
```

**讲解要点**：
- 多格式文档支持（PDF、Word、PPT、图片OCR）
- 事务性上传与回滚机制
- 企业级文档管理功能

### 第四阶段：性能对比与监控（3分钟）

#### 演示6：性能监控仪表板
```bash
# 展示Grafana监控面板（如果已部署）
# 或使用API获取性能指标
curl "http://localhost:8001/metrics"
```

**展示指标**：
1. **QPS（每秒查询数）**：当前负载情况
2. **响应时间分布**：P50、P95、P99
3. **检索策略分布**：MySQL vs RAG比例
4. **缓存命中率**：Redis缓存效果

#### 演示7：压力测试对比
```python
# 简单压力测试脚本
import concurrent.futures
import requests
import time

def test_query(query):
    start = time.time()
    requests.post(
        "http://localhost:8001/query",
        json={"query": query, "source_filter": "ai"},
        timeout=10
    )
    return time.time() - start

# 并发测试
queries = ["Python是什么？"] * 50  # 50个并发简单查询
with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
    times = list(executor.map(test_query, queries))

print(f"平均响应时间: {sum(times)/len(times):.3f}s")
print(f"最大响应时间: {max(times):.3f}s")
print(f"总吞吐量: {len(times)/sum(times):.1f} QPS")
```

**讲解要点**：
- 系统并发处理能力
- 混合架构的资源效率
- 与传统方案的性能对比

## 💡 演示技巧与注意事项

### 成功关键
1. **提前演练**：确保所有演示步骤流畅
2. **备选方案**：准备离线演示数据，避免网络问题
3. **重点突出**：每个演示环节突出1-2个核心优势
4. **互动设计**：预留时间让面试官提问或亲自尝试

### 常见问题准备
1. **如果MySQL宕机怎么办？** → 降级到纯RAG模式
2. **如何保证答案准确性？** → 多层评估体系（人工+自动）
3. **扩展性如何？** → 水平扩展方案已设计
4. **成本是多少？** → 比SaaS方案节省57%

### 技术深度展示
- **算法层面**：BM25、BERT分类、向量相似度计算
- **工程层面**：连接池、缓存策略、错误处理
- **架构层面**：微服务化、数据一致性、监控告警

## 📊 演示效果评估

### 定量指标
- 响应时间：简单问题<100ms，复杂问题<3s
- 准确率：演示问题100%正确回答
- 系统稳定性：无错误、无超时

### 定性反馈
- 架构设计清晰度
- 技术深度展示
- 演示表达能力
- 问题回答质量

## 🎯 定制化演示建议

### 针对技术面试官
- 重点展示：架构设计、算法实现、性能优化
- 深度内容：源代码走读、算法复杂度分析
- 扩展讨论：技术选型理由、替代方案比较

### 针对产品/业务面试官
- 重点展示：用户体验、业务价值、成本效益
- 深度内容：用户场景分析、ROI计算、市场竞争力
- 扩展讨论：产品路线图、商业化策略

### 针对CTO/技术负责人
- 重点展示：系统可靠性、扩展性、团队协作
- 深度内容：技术债务管理、团队技能要求、演进规划
- 扩展讨论：技术战略、人才招聘、创新文化

## 📁 附录：演示支持文件

### 1. 快速启动脚本
```bash
# demo_start.sh
#!/bin/bash
echo "启动演示环境..."
docker-compose -f demo/docker-compose.yml up -d
sleep 10
python demo/prepare_data.py
echo "演示环境准备完成！"
```

### 2. 演示数据包
```
demo_data/
├── sample_queries.json    # 演示问题集
├── test_documents/        # 测试文档
├── expected_outputs/      # 预期输出
└── performance_report.pdf # 性能报告
```

### 3. 故障处理指南
- API服务异常：重启命令、日志查看位置
- 数据库连接失败：连接字符串检查、网络诊断
- 性能下降：缓存清理、连接池调整

---

**演示负责人**：[你的姓名]
**最后更新**：2025年3月25日
**版本**：v1.0
**备注**：演示前请确保所有服务正常运行，建议提前30分钟准备环境。