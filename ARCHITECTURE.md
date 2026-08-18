# 技术架构文档 — 保险智能助手

> 本文档详细描述系统的整体架构、节点设计、工作流、思维链、RAG 检索流水线及各项优化策略。

---

## 目录

1. [系统总体架构](#1-系统总体架构)
2. [技术栈选型](#2-技术栈选型)
3. [Agent 主图设计](#3-agent-主图设计)
4. [节点详解](#4-节点详解)
5. [意图路由与条件分支](#5-意图路由与条件分支)
6. [RAG 子图设计](#6-rag-子图设计)
7. [查询语句优化](#7-查询语句优化)
8. [多路召回](#8-多路召回)
9. [RRF 融合算法](#9-rrf-融合算法)
10. [重排序](#10-重排序)
11. [上下文拼装](#11-上下文拼装)
12. [工具子图与 HITL](#12-工具子图与-hitl)
13. [思维链（Chain-of-Thought）](#13-思维链chain-of-thought)
14. [LLM 路由策略](#14-llm-路由策略)
15. [会话持久化](#15-会话持久化)
16. [Embedding 与向量库](#16-embedding-与向量库)
17. [关键参数配置](#17-关键参数配置)

---

## 1. 系统总体架构

```
┌─────────────────────────────────────────────────────────────┐
│                        前端 (Vue 3)                         │
│  Chat.vue  │  KnowledgeBase.vue  │  Inspect.vue  │  Login  │
└──────┬─────┴──────────┬──────────┴────────┬────────┴────────┘
       │ SSE            │ REST              │ REST
       ▼                ▼                   ▼
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI 后端                             │
│  ┌─────────┐  ┌───────────┐  ┌──────────┐  ┌───────────┐  │
│  │ routes  │  │   auth    │  │ schemas  │  │  UserStore │  │
│  └────┬────┘  └───────────┘  └──────────┘  └───────────┘  │
│       │                                                      │
│  ┌────▼──────────────────────────────────────────────────┐  │
│  │              LangGraph Agent 主图                      │  │
│  │  compress → rewrite → route_intent                    │  │
│  │      ├─ chitchat → final_generate → END               │  │
│  │      ├─ rag_subgraph → merge → assemble → final       │  │
│  │      ├─ tool_subgraph → merge → assemble → final     │  │
│  │      └─ both (fan-out) → assemble → final            │  │
│  └───────────────────────────────────────────────────────┘  │
│       │              │                    │                  │
│  ┌────▼────┐  ┌─────▼─────┐  ┌──────────▼────────┐         │
│  │  LLM    │  │ Retriever │  │   Tool Registry    │         │
│  │ Router  │  │  Vector   │  │  policy_query      │         │
│  │         │  │  BM25     │  │  claim_query       │         │
│  │ DeepSeek│  │  Rerank   │  │  high_risk (HITL)  │         │
│  │ Ollama  │  │  ChromaDB │  │                    │         │
│  └─────────┘  └───────────┘  └────────────────────┘         │
│       │              │                                        │
│  ┌────▼────┐  ┌─────▼──────────────────┐                     │
│  │ SQLite  │  │   data/chroma/         │                     │
│  │ checkpoint│ │   (向量持久化)          │                     │
│  └─────────┘  └────────────────────────┘                     │
└─────────────────────────────────────────────────────────────┘
```

### 分层职责

| 层 | 职责 | 技术 |
|---|---|---|
| 表现层 | 用户交互、SSE 流式渲染、会话管理 | Vue 3 + Element Plus |
| 接入层 | 鉴权、路由、请求校验、SSE 推送 | FastAPI + JWT |
| 编排层 | Agent 图调度、意图路由、子图协调 | LangGraph StateGraph |
| 检索层 | 向量召回、BM25 召回、RRF 融合、Rerank | ChromaDB + rank-bm25 + Ollama |
| 工具层 | 保单查询、理赔查询、高风险操作 HITL | LangChain Tools |
| 模型层 | LLM 调用、Embedding、Rerank | DeepSeek API + Ollama |
| 持久层 | 会话状态持久化、向量数据持久化 | SQLite + ChromaDB |

---

## 2. 技术栈选型

| 组件 | 选型 | 选型理由 |
|---|---|---|
| Agent 框架 | LangGraph | 原生支持图编排、条件路由、子图嵌套、HITL interrupt、checkpointer |
| Web 框架 | FastAPI | 原生 async、SSE 支持、自动 OpenAPI 文档 |
| LLM (主力) | DeepSeek Chat | 高性价比、中文能力强、API 兼容 OpenAI |
| LLM (降级) | Ollama + qwen3.5:0.8b | 本地 CPU 推理、无需 GPU、离线可用 |
| Embedding | nomic-embed-text (Ollama) | 768 维、中英文支持、本地部署 |
| Rerank | bge-reranker-v2-m3 (Ollama) | 中文 rerank SOTA、本地部署 |
| 向量库 | ChromaDB (PersistentClient) | 轻量、嵌入式、无需独立服务、持久化 |
| BM25 | rank-bm25 | 纯 Python、无需 Elasticsearch |
| 会话持久化 | AsyncSqliteSaver | LangGraph 原生支持、异步、持久化 |
| 前端 | Vue 3 + Element Plus | 组件丰富、中文生态好 |

---

## 3. Agent 主图设计

主图定义在 [graph.py](file:///Users/yang/wise/policy_agent/backend/core/graph.py) 中，采用 LangGraph 的 `StateGraph` 构建。

### 图结构

```
START
  │
  ▼
compress (对话压缩)
  │
  ▼
rewrite (查询改写)
  │
  ▼
route_intent (意图路由) ──┐
  │                      │
  ├─ chitchat ───────────┼──→ final_generate → END
  │                      │
  ├─ rag ────────────────┤
  │   rag_subgraph       │
  │   merge_rag          │
  │                      │
  ├─ tool ───────────────┤
  │   tool_subgraph      │
  │   merge_tool         │
  │                      │
  └─ both ───────────────┘
      fanout_both
      ├─→ rag_subgraph → merge_rag ──┐
      └─→ tool_subgraph → merge_tool ┘
                                    │
                                    ▼
                                 assemble
                                    │
                                    ▼
                              final_generate
                                    │
                                    ▼
                                   END
```

### 状态定义

主图状态 `AgentState` 定义在 [state.py](file:///Users/yang/wise/policy_agent/backend/core/state.py)：

```python
class AgentState(dict):
    messages: list[BaseMessage]      # 完整对话历史
    user_query: str                  # 原始用户问题
    thread_id: str                   # 会话线程 ID
    user_id: str                     # 用户标识
    compressed_history: str          # 压缩后的对话摘要
    rewritten_query: str             # 改写后的查询
    intent: str                      # 意图分类结果
    tool_plan: list[ToolCall]        # 工具调用计划
    rag_context: str                # RAG 检索到的上下文
    rag_draft: str                   # RAG 草稿回答
    tool_results: list[ToolResult]  # 工具执行结果
    hitl_reviews: list[HitlReview]   # HITL 审核记录
    assembled_context: str           # 拼装后的完整上下文
    final_answer: str                # 最终回答
    metadata: dict                   # 元数据
```

### Fan-out 并行机制

当意图为 `both` 时，LangGraph 的 fan-out 机制让 `rag_subgraph` 和 `tool_subgraph` **并行执行**：

```python
graph.add_edge("fanout_both", "rag_subgraph")
graph.add_edge("fanout_both", "tool_subgraph")
```

`assemble` 节点作为**屏障同步点**（barrier），等待两条分支都完成后才执行。

---

## 4. 节点详解

### 4.1 对话压缩节点 `compress`

文件：[compression.py](file:///Users/yang/wise/policy_agent/backend/core/nodes/compression.py)

**目的**：将长对话历史压缩为简洁摘要，减少后续 LLM 调用的 token 消耗。

**触发条件**：当 `messages` 超过 3 条时触发，否则跳过返回空字符串。

**Prompt 设计**：
- 保留用户核心需求和意图
- 保留已确认的关键事实和数据
- 保留未解决的问题
- 输出限制 200 字以内

**LLM 选择**：`TaskType.LIGHT`（轻量任务，使用低成本模型）

### 4.2 查询改写节点 `rewrite`

文件：[query_rewrite.py](file:///Users/yang/wise/policy_agent/backend/core/nodes/query_rewrite.py)

**目的**：结合对话上下文，对用户查询进行三维改写。

**改写维度**：

| 维度 | 说明 | 示例 |
|---|---|---|
| 指代消解 | 将"他/这个/那个"替换为具体内容 | "他的保单" → "张三的保单" |
| 子问题拆分 | 复杂问题拆分为 2-5 个独立子问题 | "车险理赔流程和所需材料" → ["车险理赔流程", "车险理赔所需材料"] |
| 同义词扩展 | 补充保险领域同义词 | "重疾险" → ["重大疾病保险", "重疾险", "大病保险"] |

**输出格式**（JSON）：
```json
{
  "rewritten_query": "改写后的完整问题",
  "sub_queries": ["子问题1", "子问题2"],
  "synonyms": {"子问题1": ["同义词1", "同义词2"]}
}
```

**容错机制**：
- LLM 返回非 JSON → 使用原始 query
- 代码块包裹（```json）→ 自动去除
- 子问题为空 → 默认使用 rewritten_query

### 4.3 意图路由节点 `route_intent`

文件：[intent_router.py](file:///Users/yang/wise/policy_agent/backend/core/nodes/intent_router.py)

**目的**：判断用户意图，决定后续执行路径。

**意图分类**：

| 意图 | 描述 | 后续路径 |
|---|---|---|
| `chitchat` | 闲聊、问候 | 直接 final_generate |
| `rag` | 知识性问题 | rag_subgraph → assemble |
| `tool` | 操作性问题 | tool_subgraph → assemble |
| `both` | 混合需求 | fan-out 并行 |

**双重判断机制**：

1. **关键词规则优先**（最可靠）
   - `TOOL_KEYWORDS`：保单/理赔/缴费/核保/退保等
   - `RAG_KEYWORDS`：什么是/怎么/条款/流程/介绍等
   - 同时命中 → `both`
   
2. **LLM 判断补充**
   - 关键词未命中时，调用 LLM 做语义判断
   - LLM 返回 JSON `{"intent": "...", "reason": "..."}`

3. **合并策略**：关键词结果优先于 LLM 结果

### 4.4 上下文拼装节点 `assemble`

文件：[answer_assemble.py](file:///Users/yang/wise/policy_agent/backend/core/nodes/answer_assemble.py)

**目的**：将 RAG 检索结果和工具执行结果合并为统一上下文。

**输出格式**：
```
【知识库参考】
[1] 车险理赔流程：事故报案 → 现场勘查 → 定损核价...
(来源: doc_abc123)

【业务数据】
- 工具 query_policies 返回: {"policies": [...]}
- 工具 query_claims 返回: {"claims": [...]}
```

### 4.5 最终回答节点 `final_generate`

文件：[final_generate.py](file:///Users/yang/wise/policy_agent/backend/core/nodes/final_generate.py)

**目的**：基于拼装后的上下文，生成用户可读的最终回答。

**System Prompt 设计原则**：
1. 回答要准确、简洁，符合保险行业规范
2. 如果参考信息中有数据，请引用具体数据
3. 如果参考信息不足，请明确告知用户"根据现有信息无法回答"，不要编造
4. 适当使用保险术语，但要通俗易懂
5. 回答用中文

**意图分流**：
- `chitchat`：使用轻量 prompt，直接回答
- 其他意图：使用完整 system prompt + assembled context

**消息累积**：生成回答后，将 AI 消息追加到 `messages` 列表，供 checkpointer 持久化。

---

## 5. 意图路由与条件分支

### 条件路由实现

```python
def _route_after_intent(state: AgentState) -> str:
    intent = state.get("intent", "chitchat")
    if intent == "rag":
        return "rag_subgraph"
    elif intent == "tool":
        return "tool_subgraph"
    elif intent == "both":
        return "fanout_both"
    else:
        return "final_generate"

graph.add_conditional_edges(
    "route_intent",
    _route_after_intent,
    {
        "rag_subgraph": "rag_subgraph",
        "tool_subgraph": "tool_subgraph",
        "final_generate": "final_generate",
        "fanout_both": "fanout_both",
    },
)
```

### 路径表

| 意图 | 执行路径 | 节点序列 |
|---|---|---|
| chitchat | 直接回答 | compress → rewrite → route → final_generate |
| rag | 仅检索 | compress → rewrite → route → rag_subgraph → merge_rag → assemble → final |
| tool | 仅工具 | compress → rewrite → route → tool_subgraph → merge_tool → assemble → final |
| both | 并行 | compress → rewrite → route → fanout → [rag_subgraph + tool_subgraph] → assemble → final |

---

## 6. RAG 子图设计

文件：[rag_subgraph.py](file:///Users/yang/wise/policy_agent/backend/core/subgraphs/rag_subgraph.py)

### 子图结构

```
rag_query_rewrite (查询改写 + 子问题拆分)
  │
  ├──────────────┐
  ▼              ▼
vector_retrieval  bm25_retrieval    ← 并行执行
  │              │
  └──────┬───────┘
         ▼
    rrf_fusion (RRF 融合)
         │
         ▼
      rerank (重排序)
         │
         ▼
  assemble_context (上下文拼装)
         │
         ▼
   generate_draft (草稿回答)
         │
         ▼
        END
```

### 子图状态

```python
class RagSubState(TypedDict):
    user_query: str
    rewritten_query: str
    sub_queries: list[str]
    vector_docs: list[dict]        # 向量召回结果
    bm25_docs: list[dict]          # BM25 召回结果
    rrf_docs: list[dict]           # RRF 融合结果
    reranked_docs: list[dict]      # 重排序结果
    context: str                   # 最终上下文
    draft_answer: str              # 草稿回答
    inspect_trace: dict            # 检查追踪（供 Inspect 页面展示）
```

### 全链路追踪

每个节点都将中间结果写入 `inspect_trace`，通过 `inspect_trace` 字段传递到最终结果，供 `/api/rag/inspect` 接口返回全链路调试数据：

```python
"inspect_trace": {
    "vector_docs": [...],   # 向量召回快照
    "bm25_docs": [...],    # BM25 召回快照
    "rrf_docs": [...],     # RRF 融合快照
    "reranked_docs": [...], # 重排序快照
    "context": "..."        # 最终上下文
}
```

---

## 7. 查询语句优化

### 7.1 指代消解

利用对话历史摘要（`compressed_history`）解决多轮对话中的指代问题。

**示例**：
```
用户：我的寿险保单有哪些保障？
助手：您的寿险保单包含...
用户：那他的理赔流程是什么？  ← "他" 指代 "寿险保单"
```

改写后查询：`"寿险保单的理赔流程是什么"`

### 7.2 子问题拆分

将复杂查询拆分为多个子查询，每个子查询独立进行多路召回，最后合并去重。

**示例**：
```
原始查询：车险理赔流程和需要什么材料？
拆分结果：
  - sub_queries[0]: "车险理赔流程"
  - sub_queries[1]: "车险理赔所需材料"
```

### 7.3 同义词扩展

在改写阶段为每个子问题补充保险领域同义词，提高召回率。这些同义词会在 BM25 检索时起到关键词扩展作用。

**示例**：
```json
{
  "重疾险": ["重大疾病保险", "大病保险", "重疾"],
  "免赔额": ["起付线", "自付额", "deductible"]
}
```

### 7.4 多轮上下文感知

改写时注入 `compressed_history`，确保改写后的 query 包含完整的上下文信息：

```python
context_text = f"\n\n对话历史摘要：\n{compressed}" if compressed else ""
prompt = f"当前用户问题：{user_query}{context_text}"
```

---

## 8. 多路召回

### 8.1 向量召回 (Vector Retrieval)

文件：[vector.py](file:///Users/yang/wise/policy_agent/backend/retrievers/vector.py)

**技术**：ChromaDB + Ollama nomic-embed-text (768 维)

**流程**：
1. 对每个子查询进行 embedding
2. 在 ChromaDB 中执行 cosine 相似度搜索
3. 返回 top-k 结果（默认 k=20）
4. 跨子查询去重（基于 `id` 或 `content[:50]`）

**距离转分数**：
```python
score = 1.0 - distance  # ChromaDB 返回 cosine distance，转换为相似度
```

**降级策略**：
- ChromaDB 不可用 → 内存向量存储 + 手动 cosine 相似度
- Ollama 不可用 → MockEmbeddings（确定性伪随机向量）

### 8.2 BM25 召回 (BM25 Retrieval)

文件：[bm25.py](file:///Users/yang/wise/policy_agent/backend/retrievers/bm25.py)

**技术**：rank-bm25 (BM25Okapi) + 自定义中文分词

**分词策略**：
```python
def _tokenize(text: str) -> list[str]:
    tokens = text.split()                          # 空格分词
    char_tokens = [c for c in text                 # 中文字符逐字分词
                   if '\u4e00' <= c <= '\u9fff']
    return tokens + char_tokens
```

**索引构建**：
1. 从 ChromaDB 加载所有文档
2. 对每个文档进行分词
3. 构建 `BM25Okapi` 索引
4. 懒加载 + 缓存（首次查询时初始化）

**查询**：
1. 对 query 进行同样的分词
2. 使用 `bm25.get_scores()` 获取每个文档的 BM25 分数
3. 按分数降序排列，取 top-k

### 8.3 多路召回去重

两路召回结果通过 `id`（或 `content[:100]` 作为 fallback）进行去重：

```python
seen_keys: set[str] = set()
for sq in sub_queries:
    docs = retriever.retrieve(sq, top_k=k)
    for d in docs:
        key = d.get("id", d.get("content", "")[:50])
        if key not in seen_keys:
            seen_keys.add(key)
            all_docs.append(d)
```

---

## 9. RRF 融合算法

文件：[rag_subgraph.py](file:///Users/yang/wise/policy_agent/backend/core/subgraphs/rag_subgraph.py) 中的 `_rag_rrf_fusion`

### 算法原理

**Reciprocal Rank Fusion (RRF)** 是一种无需校准的多路检索结果融合方法，通过排名倒数加权来合并不同来源的检索结果。

### 公式

```
RRF_score(d) = Σ  1 / (k + rank_i(d))
              sources
```

其中：
- `d` = 文档
- `rank_i(d)` = 文档 d 在第 i 路检索结果中的排名（从 1 开始）
- `k` = 平滑参数（默认 60），防止排名靠前的文档获得过高权重

### 实现代码

```python
def _rag_rrf_fusion(state: RagSubState) -> dict:
    k = settings.rag_rrf_k  # 默认 60
    
    doc_scores: dict[str, float] = {}
    doc_data: dict[str, dict] = {}
    
    for source, docs in source_docs.items():      # vector, bm25
        for rank, doc in enumerate(docs, start=1):
            key = doc.get("id", doc.get("content", "")[:100])
            rrf_score = 1.0 / (k + rank)
            doc_scores[key] = doc_scores.get(key, 0.0) + rrf_score
            if key not in doc_data:
                doc_data[key] = doc
    
    # 按融合分数降序排列，取 top-k
    sorted_keys = sorted(doc_scores, key=lambda x: doc_scores[x], reverse=True)
    rrf_docs = [doc_data[key] for key in sorted_keys[:settings.rag_top_k_rrf]]
```

### 融合效果示例

假设向量召回和 BM25 召回各返回 3 条结果：

| 文档 | 向量排名 | BM25排名 | RRF 得分 |
|---|---|---|---|
| DocA | 1 | 3 | 1/61 + 1/63 = 0.0323 |
| DocB | 2 | 1 | 1/62 + 1/61 = 0.0325 |
| DocC | 3 | 未命中 | 1/63 + 0 = 0.0159 |
| DocD | 未命中 | 2 | 0 + 1/62 = 0.0161 |

最终排序：DocB > DocA > DocD > DocC

### RRF 优势

1. **无需归一化**：不同检索器的分数尺度不同（cosine 0-1 vs BM25 无上限），RRF 只用排名，避免归一化问题
2. **互补性**：向量召回擅长语义相似，BM25 擅长关键词精确匹配，融合后覆盖面更广
3. **可调性**：k 值控制排名权重的衰减速度，k 越大各排名差异越小

---

## 10. 重排序

文件：[rerank.py](file:///Users/yang/wise/policy_agent/backend/retrievers/rerank.py)

### 模型

`dengcao/bge-reranker-v2-m3`（通过 Ollama 本地部署）

### 重排序策略

#### 策略一：Ollama Embedding 重排（主策略）

将 query + document 拼接为 pair，通过 bge-reranker 模型 embedding，用 embedding 向量的 L2 范数作为相关性分数：

```python
pair_text = f"{query}\n{content}"           # Cross-encoder 风格输入
resp = client.post(f"{base_url}/api/embed",
                   json={"model": model, "input": pair_text})
embedding = resp.json()["embeddings"][0]
score = sqrt(sum(x * x for x in embedding))  # 向量范数作为分数
```

**原理**：bge-reranker 模型的 embedding 编码了 query-doc 对的语义相关性，范数越大表示越相关。

#### 策略二：启发式重排（降级策略）

当 Ollama 不可用时，使用关键词重叠度 + 原始分数的加权组合：

```python
char_overlap = len(query_chars & content_chars) / max(len(query_chars), 1)
combined_score = existing_score * 0.6 + char_overlap * 0.4
```

### 重排序流程

1. 输入：RRF 融合后的 top-N 文档列表（默认 N=20）
2. 对每个文档计算 rerank_score
3. 按 rerank_score 降序排列
4. 输出：top-k 文档（默认 k=5）

### 模型可用性检测

```python
@property
def model_available(self) -> bool:
    # 检查 Ollama /api/tags 是否包含 rerank_model
    resp = httpx.Client(timeout=5.0).get(f"{base_url}/api/tags")
    tags = resp.json().get("models", [])
    return any(m["name"].startswith(rerank_model) for m in tags)
```

检测结果缓存，避免每次重排序都发 HTTP 请求。

---

## 11. 上下文拼装

文件：[rag_subgraph.py](file:///Users/yang/wise/policy_agent/backend/core/subgraphs/rag_subgraph.py) 中的 `_rag_assemble_context`

### 拼装规则

1. **去重**：已在 RRF 阶段完成
2. **Token 预算控制**：总上下文不超过 `rag_max_context_tokens`（默认 3000）

```python
est_tokens = len(content) // 4    # 中文约 4 字符 ≈ 1 token
if total_tokens + est_tokens > settings.rag_max_context_tokens:
    break
```

3. **来源标注**：每条结果附带来源信息

```
[1] 车险理赔流程：事故报案 → 现场勘查...
(来源: doc_abc123)

[2] 理赔所需材料：行驶证、驾驶证、事故责任书...
(来源: doc_def456)
```

### 草稿回答生成

在上下文拼装后，使用 LLM 生成草稿回答（`draft_answer`），供主图的 `assemble` 节点参考：

```python
prompt = f"""基于以下知识库内容回答用户问题。如果知识库内容不足，请明确说明。

用户问题：{user_query}

知识库内容：
{context}
"""
```

---

## 12. 工具子图与 HITL

文件：[tool_subgraph.py](file:///Users/yang/wise/policy_agent/backend/core/subgraphs/tool_subgraph.py)

### 子图结构

```
plan_tools (LLM 规划工具调用)
  │
  ▼
execute_tools (执行工具，高风险工具触发 HITL)
  │
  ├─ should_continue == "end" → END
  └─ should_continue == "continue" → plan_tools (多轮)
```

### 工具注册表

文件：[registry.py](file:///Users/yang/wise/policy_agent/backend/tools/registry.py)

| 工具名 | 风险等级 | 说明 |
|---|---|---|
| query_policies | LOW | 查询用户保单列表 |
| query_policy_detail | LOW | 查询保单详情 |
| query_payment_records | LOW | 查询缴费记录 |
| query_claims | LOW | 查询理赔记录 |
| query_claim_detail | LOW | 查询理赔详情 |
| underwrite | **HIGH** | 核保审核 |
| make_payment | **HIGH** | 支付/退款 |
| issue_policy | **HIGH** | 出单 |
| cancel_policy | **HIGH** | 退保 |

### 工具规划

**LLM 规划**（主策略）：
```python
prompt = f"""根据用户问题，决定需要调用哪些保险业务工具。
可用工具：
{tool_descriptions}
请以JSON数组格式输出：[{{"name": "工具名", "args": {{参数}}}}]
"""
```

**规则降级**（LLM 失败时）：
基于关键词匹配的工具规划，如 "我的保单" → `query_policies`，"退保" → `cancel_policy`。

### HITL 机制

高风险工具执行前，调用 LangGraph 的 `interrupt()` 暂停图执行：

```python
if risk == RiskLevel.HIGH:
    human_decision = interrupt({
        "type": "hitl_review",
        "review_id": review_id,
        "tool": call.name,
        "args": call.args,
        "reason": "高风险操作，请人工确认",
        "risk_level": "HIGH",
    })
    
    action = human_decision.get("action", "reject")
    if action == "reject":
        # 记录拒绝结果，跳过执行
        continue
    elif action == "modify":
        # 使用修改后的参数继续执行
        call.args = human_decision.get("modified_args", call.args)
    # approve → 继续执行
```

### HITL 恢复

前端 approve 后，后端通过 `Command(resume=...)` 恢复图执行：

```python
result = await agent.ainvoke(
    Command(resume={"action": "approve", "modified_args": {}}),
    config={"configurable": {"thread_id": thread_id}}
)
```

---

## 13. 思维链（Chain-of-Thought）

系统采用**隐式思维链**设计，通过多节点串联实现分步推理：

### 推理链路

```
用户问题
  │
  ├─① 对话压缩 → "用户之前问了理赔，现在问材料"
  │
  ├─② 查询改写 → "车险理赔需要哪些材料？" (指代消解 + 子问题拆分)
  │     ├─ sub_query_1: "车险理赔所需材料"
  │     └─ sub_query_2: "车险理赔流程"
  │
  ├─③ 意图判断 → "rag" (知识性问题)
  │
  ├─④ 多路召回 → 向量 + BM25 各自检索
  │
  ├─⑤ RRF 融合 → 合并去重排序
  │
  ├─⑥ 重排序 → 精排 top-5
  │
  ├─⑦ 上下文拼装 → 带来源标注的上下文
  │
  ├─⑧ 草稿回答 → "根据知识库，车险理赔需要..."
  │
  └─⑨ 最终回答 → LLM 综合上下文 + 工具结果生成用户回答
```

### 显式思维链输出

RAG 检查页面（Inspect.vue）将每一步的中间结果可视化展示，形成完整的思维链追踪：

| 步骤 | 输出 | 可视化 |
|---|---|---|
| 查询改写 | rewritten_query + sub_queries | 不展示 |
| 向量召回 | vector_docs (id, score, content) | 结果卡片列表 |
| BM25 召回 | bm25_docs (id, score, content) | 结果卡片列表 |
| RRF 融合 | rrf_docs (id, rrf_score, content) | 结果卡片列表 |
| 重排序 | reranked_docs (id, rerank_score, content) | 结果卡片列表 |
| 上下文 | context (带来源标注的文本) | 深色代码块 |
| 草稿回答 | draft_answer | 文本展示 |

---

## 14. LLM 路由策略

文件：[router.py](file:///Users/yang/wise/policy_agent/backend/llm/router.py)

### 任务类型

```python
class TaskType(str, Enum):
    HEAVY = "heavy"   # 意图识别、最终回答、工具规划、RAG 草稿
    LIGHT = "light"   # 对话压缩、查询改写
```

### 路由优先级

```
1. DeepSeek (deepseek-chat)
   ↓ 不可用 (API Key 为空 / 网络错误)
2. Ollama (qwen3.5:0.8b)
   ↓ 不可用 (Ollama 服务未启动)
3. MockLLM (确定性 mock 响应)
```

### Mock 模式

通过环境变量 `POLICY_AGENT_MOCK_LLM=true` 启用全链路离线测试模式：
- LLM → MockLLM（基于关键词的规则响应）
- Embedding → MockEmbeddings（确定性伪随机向量）
- 无需 DeepSeek API 和 Ollama 服务

---

## 15. 会话持久化

文件：[checkpointer.py](file:///Users/yang/wise/policy_agent/backend/core/checkpointer.py)

### 持久化方案

| 组件 | 技术 | 存储路径 |
|---|---|---|
| 会话状态 | AsyncSqliteSaver | `data/checkpoints.sqlite` |
| 向量数据 | ChromaDB PersistentClient | `data/chroma/` |

### Checkpointer 初始化

在 FastAPI lifespan 中异步初始化：

```python
async def init_checkpointer():
    # 优先使用 AsyncSqliteSaver
    _saver_cm = AsyncSqliteSaver.from_conn_string(str(_sqlite_path))
    _saver = await _saver_cm.__aenter__()
    await _saver.setup()
    
    # 降级方案：
    # 1. Sync SqliteSaver (不支持 async 方法，仅作 fallback)
    # 2. MemorySaver (不持久化，重启丢失)
```

### 会话恢复流程

```
前端 localStorage 读取 thread_id
  │
  ▼
GET /api/chat/history/{thread_id}
  │
  ▼
后端 agent.aget_state(config)
  │
  ▼
从 SQLite 读取 checkpoint → 返回 messages 列表
  │
  ▼
前端渲染历史消息
```

---

## 16. Embedding 与向量库

### Embedding 模型

文件：[embeddings.py](file:///Users/yang/wise/policy_agent/backend/llm/embeddings.py)

| 模式 | 模型 | 维度 | 来源 |
|---|---|---|---|
| 正常 | nomic-embed-text | 768 | Ollama |
| Mock | MockEmbeddings | 768 | 确定性伪随机 |

### ChromaDB 配置

文件：[vector.py](file:///Users/yang/wise/policy_agent/backend/retrievers/vector.py)

```python
chromadb.PersistentClient(
    path=str(_chroma_dir),
    settings=ChromaSettings(anonymized_telemetry=False)
)

collection = client.get_or_create_collection(
    name="policy_knowledge",
    metadata={"hnsw:space": "cosine"}   # 使用 cosine 相似度
)
```

### 文档切片

使用 LangChain 的 `RecursiveCharacterTextSplitter`：

```python
splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,      # 每片 800 字符
    chunk_overlap=100,   # 重叠 100 字符
)
```

切片后每个 chunk 的 metadata 包含：
- `source`: 原始文档 ID
- `title`: 文档标题
- `chunk_index`: 切片序号
- `kb_id`: 知识库 ID

---

## 17. 关键参数配置

文件：[settings.py](file:///Users/yang/wise/policy_agent/backend/config/settings.py)

### RAG 参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `rag_top_k_retrieval` | 20 | 每路召回的文档数 |
| `rag_top_k_rrf` | 20 | RRF 融合后保留的文档数 |
| `rag_rrf_k` | 60 | RRF 平滑参数 |
| `rag_chunk_size` | 800 | 文档切片大小 |
| `rag_chunk_overlap` | 100 | 切片重叠大小 |
| `rag_max_context_tokens` | 3000 | 最终上下文最大 token 数 |
| `rerank_max_top_k` | 5 | 重排序后保留的文档数 |

### Agent 参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `agent_max_tool_rounds` | 5 | 工具调用最大轮数 |
| `agent_max_sub_queries` | 5 | 子问题拆分最大数量 |
| `hitl_timeout_minutes` | 30 | HITL 审核超时时间 |

### LLM 参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `deepseek_model` | deepseek-chat | DeepSeek 模型名 |
| `deepseek_temperature` | 0.3 | 温度（低温度保证稳定性） |
| `deepseek_max_tokens` | 4096 | 最大输出 token |
| `ollama_model` | qwen3.5:0.8b | 本地降级模型 |
| `ollama_embedding_model` | nomic-embed-text:latest | Embedding 模型 |
| `rerank_model` | dengcao/bge-reranker-v2-m3 | Rerank 模型 |

---

## 附：数据流总结

```
用户输入
  │
  ▼
[compress] ─── 对话 > 3 轮时摘要压缩 (LLM LIGHT)
  │
  ▼
[rewrite] ──── 指代消解 + 子问题拆分 + 同义词扩展 (LLM LIGHT)
  │            输出: rewritten_query, sub_queries[]
  ▼
[route_intent] 关键词规则 + LLM 判断 (LLM HEAVY)
  │            输出: intent ∈ {chitchat, rag, tool, both}
  │
  ├── chitchat ──────────────────────────────────────────┐
  │                                                      │
  ├── rag ──→ [rag_subgraph]                             │
  │           │                                          │
  │           ├─ query_rewrite (子问题拆分)               │
  │           ├─ vector_retrieval (ChromaDB cosine)     │
  │           ├─ bm25_retrieval (rank-bm25)             │
  │           ├─ rrf_fusion (1/(k+rank) 加权)            │
  │           ├─ rerank (bge-reranker-v2-m3)             │
  │           ├─ assemble_context (token 预算控制)       │
  │           └─ generate_draft (LLM HEAVY)             │
  │                                                      │
  ├── tool → [tool_subgraph]                            │
  │           │                                          │
  │           ├─ plan_tools (LLM HEAVY / 关键词降级)     │
  │           └─ execute_tools                           │
  │                ├─ LOW risk → 直接执行                │
  │                └─ HIGH risk → interrupt() → HITL     │
  │                                                      │
  └── both → fan-out (rag + tool 并行)                   │
                                                          │
                    ┌─────────────────────────────────────┘
                    ▼
              [assemble] ── 合并 RAG context + Tool results
                    │
                    ▼
              [final_generate] ── LLM HEAVY 生成最终回答
                    │
                    ▼
              SSE 流式输出 → 前端
```
