# DeepSearch — 多源交叉验证深度搜索引擎

## 一句话描述
双引擎（Grok + Tavily）交叉验证 + 证据约束的通用深度搜索 Skill。任何 AI agent 读完本文件即可使用。

## 触发关键词
当用户消息包含以下关键词时触发：
- "深度搜索" / "深度调研" / "多源核实" / "DeepSearch" / "deep research"
- 需要多来源交叉验证的复杂研究问题
- 涉及时效信息 / 版本号 / 外部状态需联网查证

## 接入方式

### 方式 1：CLI（通用）
```
cd <deepsearch-dir> && uv run deepsearch --query "你的问题"

# 快速模式（仅双引擎搜索，不做全流程）
uv run deepsearch --query "简单问题" --mode quick

# 抓取页面
uv run deepsearch fetch --url "https://example.com"

# 启动 MCP Server
uv run deepsearch serve
```

### 方式 2：MCP Server（Claude Code 等 MCP agent）
```json
// MCP server 配置
{
  "mcpServers": {
    "deepsearch": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--directory", "<deepsearch-dir>", "deepsearch", "serve"]
    }
  }
}
```

暴露的 MCP Tools：
| Tool | 功能 | 参数 |
|------|------|------|
| `deep_search` | 完整 5 阶段深度调研 | query: string |
| `quick_search` | 快速双引擎搜索 | query: string |
| `fetch_page` | 获取网页正文 | url: string |

### 方式 3：Python API（手动调用）
```python
from deepsearch.engine import deep_search

result = deep_search(question="你的问题", mode="standard")
# mode="quick" 仅双引擎快速搜索
```

## 工作流程

当 agent 决定使用 DeepSearch 时，建议按以下步骤：

### Step 1：判断是否需要搜索
**需要**：用户明确要求 / 涉及实时数据 / 需验证内部知识 / 版本号 / 产品最新状态
**不需要**：纯代码编写 / 用户说"不要搜"

### Step 2：按复杂度选择模式
| 级别 | 场景 | 模式 |
|------|------|------|
| L1 单一事实（1 次搜索） | "FastAPI 最新版本" | `quick_search` |
| L2 多角度比较（3-5 次） | "Flask vs FastAPI 2026" | `deep_search` |
| L3 深度调研（6+ 次） | "向量数据库完整对比" | `deep_search` |

### Step 3：评估结果
收到结果后 agent 必须执行以下验证 — 不信任单一来源：

## 证据标准（agent 必须遵守）

### 置信度标注
| 标签 | 判据 |
|------|------|
| **High** | ≥ 2 真正独立来源 + 官方/主流媒体 + 时效符合 |
| **Medium** | ≥ 2 来源但一个非权威，或多源有可解释分歧 |
| **Low** | 单一来源 / 非权威 / 时效不明 |

### 引用规则
- 每个关键事实后带 `[标题](URL)` 引用
- **严禁编造引用** — 没有来源的不说
- 末尾必须有 `Sources:` 节，列出全部 URL

### 冲突处理
- 不隐藏分歧，展示双方证据
- 官方 > 主流 > 自媒体；近期 > 远期；原始 > 二手
- 证据不足以决断时诚实说"存在分歧"

### 来源质量
| 级别 | 包含 |
|------|------|
| **高** | 官方文档、GitHub、PyPI、arxiv、PEP/RFC 标准文档 |
| **中** | Wikipedia、Stack Overflow、Reddit、Hacker News |
| **低** | 无名个人博客、SEO 农场、AI 生成聚合站 |

仅有单一来源时，显式标注 `置信度: Low`。

## 输出格式结构

CLI 和 MCP Server 都返回 JSON，结构如下：

### quick_search 输出
```json
{
  "query": "...",
  "mode": "quick",
  "plan": { "sub_queries": [...], "strategy": "..." },
  "search_results": [
    {
      "query_id": 1,
      "grok": { "content": "...", "citations": [{"url": "...", "title": ""}] },
      "tavily": { "answer": "...", "results": [{"title": "...", "url": "...", "content": "...", "score": 0.9}] },
      "overlap_urls": [...],
      "confidence_hint": "high|medium|low"
    }
  ],
  "elapsed_s": 12.3
}
```

### deep_search 输出
```json
{
  "question": "...",
  "summary": "一句话摘要",
  "findings": [{"statement": "...", "confidence": "High|Medium|Low", "sources": ["url1", "url2"]}],
  "evidence_grading": "High|Medium|Low",
  "sources": [{"url": "...", "quality": "high|medium|low"}],
  "caveats": ["来源不足，建议手动核实"],
  "_meta": { "elapsed_s": 45.6 }
}
```

## 快速自检清单（agent 交付前检查）
- [ ] 每个事实结论都有 ≥ 1 个 `[标题](URL)` 引用
- [ ] 单源结论都标了 `置信度: Low`
- [ ] 所有 URL 都是真实存在、已验证的
- [ ] 来源有分歧的地方没藏着掖着
- [ ] 没使用"一般来说 / 据报道 / 多个来源显示"这种无根据的措辞

---

*DeepSearch v1.0 — 双引擎 + 证据强约束通用搜索 Skill*
