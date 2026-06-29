# DeepSearch — 多源交叉验证深度搜索引擎

双引擎（Grok + Tavily）交叉验证 + 证据约束的通用深度搜索工具包。

## 快速开始

```bash
cd ~/code/GenericAgent/skills/DeepSearch

# 确保依赖
uv sync

# 快速搜索
uv run deepsearch --query "FastAPI 最新稳定版本" --mode quick --pretty

# 深度调研（完整 5 阶段）
uv run deepsearch --query "2026 年 Claude Code 在 agentic coding 方面有哪些新功能？" --pretty

# 抓取页面
uv run deepsearch fetch --url "https://example.com" --pretty

# 启动 MCP Server（stdio 模式，供 AI agent 挂载）
uv run deepsearch serve
```

## 架构

```
skills/DeepSearch/
├── SKILL.md                    — Agent-readable skill 定义
├── README.md                   — 你正在看的
├── DeepSearch_SOP.md           — 详细方法论手册（1586 行精华）
├── .env                        — 凭证配置
├── .env.example                — 凭证模板
├── pyproject.toml              — 项目元数据
├── deepsearch/                 — 核心包
│   ├── __init__.py
│   ├── __main__.py             — python -m deepsearch
│   ├── cli.py                  — CLI 入口
│   ├── server.py               — MCP Server
│   ├── tools.py                — MCP Tool 定义
│   ├── engine.py               — 5 阶段编排引擎
│   └── config.py               — 凭证 + 配置
├── scripts/                    — 底层工具脚本
│   ├── __init__.py
│   ├── _creds.py / _http.py    — 基础设施
│   ├── dual_search.py          — 双引擎并行
│   ├── grok_search.py          — Grok AI 搜索
│   ├── tavily_search.py        — Tavily 结构化搜索
│   ├── web_fetch.py            — 页面抓取
│   ├── web_map.py              — 站点映射
│   └── search_planning.py      — 搜索规划
└── tests/
    └── test_smoke.py           — 烟测
```

## 5 阶段流程

```
Scope → Search → Fetch → Verify → Synthesize
```

| 阶段 | 做什么 | 核心逻辑 |
|------|--------|----------|
| **Scope** | 拆解问题为 3-7 个子查询 | `search_planning.py` |
| **Search** | 双引擎并行搜索 | `dual_search.py` / `grok_search.py` / `tavily_search.py` |
| **Fetch** | 抓取关键 URL 正文 | `web_fetch.py`（Tavily→FireCrawl 降级） |
| **Verify** | 交叉验证 + 置信度标注 | 来源质量评级、独立来源计数 |
| **Synthesize** | 合成带引用报告 | 多重证据组织 |

## 三种接入方式

| 方式 | 适用场景 | 命令 |
|------|----------|------|
| **CLI** | 任何终端 / 任何 agent | `deepsearch --query "..."` |
| **MCP Server** | Claude Code 等 MCP agent | `deepsearch serve` |
| **Python Import** | 直接集成 | `from deepsearch.engine import deep_search` |

## 凭证配置

复制 `.env.example` 为 `.env`，填入真实凭证：

```bash
cp .env.example .env
# 编辑 .env，填入 GROK2API_API_KEY / TAVILY_API_KEY / FIRECRAWL_API_KEY
```

凭证加载优先级：**环境变量 > .env > 默认值**

## 开发

```bash
# 安装到当前环境
uv pip install -e .

# 烟测
cd ~/code/GenericAgent/skills/DeepSearch
uv run deepsearch --query "test" --mode quick --max-results 2
```
