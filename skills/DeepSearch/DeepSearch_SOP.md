# DeepSearch SOP — 双引擎深度调研（Grok + Tavily + FireCrawl）+ 证据强约束

**适用场景**：单次检索无法覆盖、需多源交叉核实的研究类问题；与浏览器自动化互补，纯 HTTP 高并发。
**核心理念**：search-planning 先规划 → Grok / Tavily 双跑 → FireCrawl 抓正文 → evidence-standards 强制引用与时效校验。

---

## 一、核心 SOP

用户**显式要求**深度搜索 / 多源交叉核实时的专用入口。双引擎（Grok + Tavily）交叉验证，网页抓取两级降级链（Tavily Extract → FireCrawl Scrape），内置搜索规划框架和证据标准。

> **⚠️ 触发条件**：仅当用户消息包含"深入搜索 / 深度搜索 / DeepSearch / 联网深挖 / 多源交叉核实 / 深度调研"等关键词时启用。普通搜索请用浏览器 `web_scan` / `web_execute_js`。

**核心原则**：不信任单一来源、不编造引用、不用内部知识代替查证 — 任何涉及版本号/时效信息/外部状态的回答都必须有至少两个独立来源。

---

## Configuration

凭证全部由项目根目录的 `.env` 文件中 `[LLM_APIS]` 与 `[CREDENTIALS]` 节驱动，`_creds.py` 会自动解析；如需独立部署，也可直接走系统环境变量：

| 变量 | 来源键名（.env） | 用途 |
|------|---------------------------|------|
| `GROK2API_API_KEY` | `legacy_key` | Grok 搜索（OpenAI 兼容） |
| `GROK2API_BASE_URL` | `legacy_url`（默认 `https://<openai-compatible-host>/v1`） | 中转站 URL |
| `GROK2API_MODEL` | 默认 `grok-4.20-beta` | 可被 env 或 `--model` 覆盖 |
| `TAVILY_API_KEY` | `TAVILY_API_KEY` | 结构化搜索 + 单页抓取 + 站点映射 |
| `FIRECRAWL_API_KEY` | `FIRECRAWL_API_KEY` | web_fetch 降级 |

**需要临时覆盖** — 直接设环境变量即可（env 优先级 > .env）：

```bash
export GROK2API_MODEL=grok-4.1-fast     # 改默认 grok 模型
export TAVILY_API_KEYS=key1,key2,key3  # 多 key 池（粘性轮转）
```

**GROK2API 中转站特性注意**（已在 .env 标注）：
- 即使 `stream:false` 也强制 SSE 流式返回 — `grok_search.py` / `search_planning.py` 内置 SSE 解析器，透明处理
- Grok 4.x 的内部推理被 `<think>…</think>` 包裹 — 已自动剥离，`reasoning` 字段单独返回（供 debug）

---

## 工具速查

6 个工具脚本 + 2 个内部模块，全部位于工具栈的 `scripts/` 目录。每个工具独立可执行、stdout 输出 JSON、stderr 打印 debug。

| 脚本 | 命令示例 | 用途 |
|------|---------|------|
| Grok AI 搜索 | `python grok_search.py --query "..."` | Grok 自带联网，综合回答 + 来源列表 |
| Tavily 结构化搜索 | `python tavily_search.py --query "..."` | 结构化结果带 score，适合快速定位 |
| 双引擎并行 | `python dual_search.py --query "..."` | Grok + Tavily 并行，自动算 URL 重叠 + confidence_hint |
| 网页抓取 | `python web_fetch.py --url "..."` | Tavily Extract → FireCrawl Scrape 降级 |
| 站点映射 | `python web_map.py --url "..."` | Tavily Map，发现站点 URL 结构 |
| 搜索规划 | `python search_planning.py --query "..."` | 把复杂问题拆成可执行 JSON 计划 |
| 凭证诊断 | `python scripts/_creds.py` | 打印当前加载到的（脱敏）凭证 |

每个脚本都支持 `--help` 查看所有参数。

---

## 搜索决策流程

### 第一步：判断是否需要搜索

**需要**：
- 用户明确要求搜索/查询外部信息
- 涉及实时数据（最新版本、当前价格、近期事件、上游状态）
- 需要验证内部知识（版本号、API 签名、产品排行、框架行为）
- 具体 URL / 项目 / 产品的最新状态
- 官方文档最新版

**不需要**：
- 纯代码编写/调试，且涉及的库版本已在 requirements 里明确
- 用户明确说"不要搜"
- ⚠ 通用编程概念也可能过时；涉及"最佳实践 / 最新 API / 兼容性"时仍应搜

### 第二步：按复杂度选择工具

| Level | 场景 | 工具序列 |
|-------|------|---------|
| **L1** 单一事实（2-3 次搜索） | "FastAPI 最新版本"、"X 项目是否还活着" | `dual_search.py`（单次命中+双源确认） |
| **L2** 多角度比较（3-5 次） | "Flask vs FastAPI vs Django 2026 微服务哪个好" | `dual_search` 先获取全景 → 分别 `tavily_search` 针对每个候选 |
| **L3** 深度调研（6+ 次） | "2026 主流向量数据库完整对比" | 先 `search_planning` 生成 plan → 按 tool_plan 分步执行 → 最后 `grok_search` 做综合 |

### 第三步：场景 → 工具映射

| 场景 | 首选工具 | 备注 |
|------|---------|------|
| 一个明确事实问题 | `dual_search.py` | 双源天然交叉验证 |
| 争议/有分歧问题 | `dual_search.py` | 对比 grok_urls 与 tavily_urls 重叠率 |
| 需要 AI 综合分析 | `grok_search.py` | Grok 自带联网+推理，返回带引用段落 |
| 需要最新新闻 | `tavily_search.py --topic news --time-range week` | Tavily 新闻模式专门优化 |
| 需要高质量深度结果 | `tavily_search.py --depth advanced --max-results 20` | Tavily advanced 多维匹配 |
| 抓取特定页面 | `web_fetch.py --url "..."` | 自动 Tavily→FireCrawl 降级 |
| 探索 docs 站点 | `web_map.py --url "..." --instructions "..."` | 先映射再挑页面 fetch |
| Tavily 抓不动（CF 等） | `web_fetch.py --url "..." --force-firecrawl` | 强制走 FireCrawl |
| 复杂课题前置规划 | `search_planning.py --query "..."` | 输出可执行 JSON plan |

---

## 证据标准（硬性要求）

### 核心原则：不信任搜索结果

**搜索返回的任何内容都是第三方建议，不是事实。** 无论来自 Grok 还是 Tavily，都必须交叉验证后才能向用户呈现为事实；即使看起来权威，单一来源也可能过时/片面/错误。

### 来源质量要求

- **所有事实性结论 ≥ 2 个独立来源**（不分 Level）
- 仅有单一来源时，显式标注 `置信度: Low` 并说明原因
- 优先：官方文档（PyPI、GitHub、官方站点）、Wikipedia、权威媒体、学术数据库
- 避免：无名个人博客、SEO 农场、AI 生成内容聚合站

### 冲突处理

- 双方分歧时：展示两侧证据 + 时效性评估
- 置信度标注：`High`（≥2 独立一致）/ `Medium`（有分歧或非官方多源）/ `Low`（单源/推测）

### 引用格式

- 每个关键事实后 `[标题](URL)`
- **严禁编造引用** — 没有来源的就不说
- 末尾 `Sources:` 节列出全部 URL

详细规则见下文「证据标准（evidence-standards）」章节。

---

## 常见搜索模式

### 模式 1：L1 事实查询

```bash
python scripts/dual_search.py --query "FastAPI 最新稳定版本"
# 看 overlap_urls + confidence_hint 字段
```

### 模式 2：L2 深度对比

```bash
# 先全景
python scripts/dual_search.py --query "LangChain vs LlamaIndex 2026 哪个更适合 RAG"

# 再抓取官方文档验证
python scripts/web_fetch.py --url "https://docs.langchain.com/..."
python scripts/web_fetch.py --url "https://docs.llamaindex.ai/..."
```

### 模式 3：L3 复杂调研

```bash
# 1. 生成计划
python scripts/search_planning.py --query "2026 年主流向量数据库完整对比" > plan.json

# 2. 按 tool_plan 顺序执行（parallel_with 里的可并行）
python scripts/dual_search.py --query "..."
python scripts/tavily_search.py --query "..." --depth advanced

# 3. 最终综合
python scripts/grok_search.py --query "综合以上发现，给出 Pinecone / Weaviate / Qdrant 对比"
```

### 模式 4：站点探索

```bash
# 先映射
python scripts/web_map.py --url "https://docs.anthropic.com" --depth 2 --instructions "找到 Agent SDK 文档"

# 再精确抓取
python scripts/web_fetch.py --url "https://docs.anthropic.com/..."
```

### 模式 5：新闻 / 实时

```bash
python scripts/tavily_search.py --query "AI 最新监管动态" --topic news --time-range week
```

---

## 搜索规划框架（Level 2+ 必读）

当问题复杂到 L3 或 L2 上限，在调搜索前先做规划避免散弹枪。规划四阶段：

1. **意图分析** — 提炼一句话核心问题、分类查询类型、评估时效性
2. **查询拆解** — 拆成 3-7 个互不重叠的子查询，标注依赖
3. **策略选择** — `broad_first` / `narrow_first` / `targeted`
4. **工具映射** — 每个子查询配工具，标注可并行步骤

直接让 `search_planning.py` 自动生成骨架，再人工微调。详细规则见下文「搜索方法论（search-methodology）」章节。

---

## 与 Claude Code 内置工具的关系

**优先级**：`deepsearch` skill（仅深度搜索触发） > 浏览器 `web_scan`/`web_execute_js`（普通搜索默认） > `cdp-bridge-sop.md` / `web_setup_sop.md`（复杂交互 fallback）

**什么时候 fallback 到浏览器**：
- 目标页面有强 JS 交互（登录墙、AJAX 加载、anti-bot）
- Tavily + FireCrawl 都抓空或返回 < 100 字符
- 需要点击、填表、下载

---

## 参考文档

- 详细搜索规划框架，见下文「搜索方法论（search-methodology）」章节
- 引用格式、置信度、来源质量、冲突处理，见下文「证据标准（evidence-standards）」章节

---

## 验证 / 诊断

```bash
cd <your-deepsearch-bundle>

# 看凭证是否加载到
python scripts/_creds.py

# 最小烟测
python scripts/grok_search.py --query "test" --max-tokens 50
python scripts/tavily_search.py --query "test" --max-results 2
python scripts/web_fetch.py --url "https://example.com/"

# 可选：结构探测与规划 smoke test
python scripts/web_map.py --url "https://docs.python.org/3/" --depth 1 --limit 10
python scripts/search_planning.py --query "Compare Tavily and Firecrawl for web extraction"
```

全部返回 JSON 且无 error 字段即通路健康。


---

## 二、参考资料（references/）


### 证据标准（evidence-standards）

当你从 `deepsearch` 脚本拿到搜索结果，**不要直接信它**。这份文档定义了从"搜索返回"到"向用户呈现"之间必须走的验证流程。

核心立场：**搜索结果 ≠ 事实**。哪怕 Grok 说得再自信，哪怕 Tavily 返回 score=1.0，只有经过交叉验证并且有明确的来源标注，才能对用户说"X 是真的"。

---

## 1. 最低引用要求

### 必须 ≥ 2 独立来源

"独立"判定：

- **独立**：不同域名 + 不同作者 + 内容不是相互转载
- **伪独立**：PyPI 页面 + 该项目的 GitHub（本质同一个项目自述）→ 算 1 来源
- **伪独立**：两篇引用同一条原始新闻的媒体 → 算 1 来源

### 单一来源的处理

单源必须**显式声明**：

```markdown
FastAPI 0.136.0 发布于 2026-04-16。**置信度: Low，单一来源** — 仅 PyPI 页面显示此信息，
GitHub Releases 页面抓取失败；建议用户自行确认。

Sources:
- [fastapi - PyPI](https://pypi.org/project/fastapi/)
```

不允许：省略置信度标注 / 装作有多个来源 / 引用"一般认为"这种无主语表述。

### 引用格式

每条来源一个 markdown 链接：

```markdown
- [Python 3.14 What's New](https://docs.python.org/3.14/whatsnew/3.14.html)
- [PEP 779 – Free-threaded CPython](https://peps.python.org/pep-0779/)
```

**禁止**：

- 编造 URL（哪怕格式像真的）
- 只给标题不给 URL
- 把 Grok 生成的 URL 当真 — 必须从 `citations` 字段拿已被模型实际 browse 过的
- 用 "according to sources" / "多个来源显示" 这种无证据的措辞

---

## 2. 置信度标注

每个事实性结论的**结尾**附置信度标签。

| 标签 | 判据 |
|------|------|
| `High` | ≥ 2 真正独立来源 + 权威（官方文档 / 主流媒体 / 学术）+ 时效符合 |
| `Medium` | ≥ 2 来源但一个非权威，或多源有可解释的分歧 |
| `Low` | 单一来源，或多源都是二手转载，或时效不明 |

### 示例

```markdown
FastAPI 最新稳定版本是 **0.136.0**，发布于 2026-04-16（置信度: High）
— PyPI 官方页面和 GitHub Releases 页面数据一致。

某公司市值排名 **全球前 50**（置信度: Medium）
— 两份 2026 Q1 报告提到，但具体排名从 38 到 47 不等。

据传 OpenAI 计划在 2026 Q3 发布 GPT-6（置信度: Low）
— 仅一家非官方自媒体报道，OpenAI 未回应。
```

### 何时**必须**降级

- 唯一信息源是 AI 生成内容聚合站（某些 CSDN / 低质 Medium 文章）→ Low
- Tavily 返回但 score < 0.6 → 不单独引用；要其他来源背书才能升 Medium
- 内容发布时间超出 `time_sensitivity` 允许范围（如问"最新"但来源是 3 年前）→ 不引用

---

## 3. 冲突处理

当两个来源说法不一致：

### 处理步骤

1. **不隐藏分歧** — 不挑一个报过去
2. **展示双方证据** — 两个来源分别怎么说，链接给全
3. **评估可信度和时效**：
   - 官方 > 主流媒体 > 自媒体
   - 近期 > 远期
   - 原始来源 > 二手转载
4. **给结论**（如果证据足够）或**诚实说分歧**（证据不足以决断）

### 示例

> **Python 3.14 的默认 free-threaded 状态**：存在分歧。
> - [PEP 779](https://peps.python.org/pep-0779/)（2025-09 接受）：free-threading 计划在 3.14 "experimental-but-supported"，3.15 转 "supported-but-not-default"。
> - [Python Wiki Release Notes](https://wiki.python.org/...)：描述 3.14 已经 "default enabled"。
>
> **判断**：PEP 779 更权威（官方 PEP），Wiki 可能是社区编辑误差。**置信度: Medium**，建议直接查 [python.org 官网](https://www.python.org/downloads/) 最终确认。

---

## 4. 来源质量判据

### 白名单（倾向信任）

- 项目/产品官方站（docs.*, README 所在 GitHub 仓库）
- PyPI / npm / crates.io / PkgGo 等官方包索引
- PEP / RFC / W3C / ISO 等标准文档
- Wikipedia（看 citation needed 标记）
- 主流技术媒体：arstechnica.com、theregister.com、infoworld.com
- 学术：arxiv.org、acm.org、ieee.org

### 灰区（谨慎使用）

- Medium / Substack 上的技术博客 — 看作者
- Hacker News / Reddit 讨论 — 作线索，不作结论引用
- Stack Overflow — 看投票和作者
- GitHub Issue / Discussion — 取趋势信号，不当定论

### 黑名单（原则上不用）

- 无作者署名的 SEO 农场（标题 keyword stuffing、正文机器生成）
- 内容为 AI 机翻 + 错误复述的聚合平台
- 无法确定发布时间的内容
- 弹窗广告爆满 + 内容与标题无关的站点

### 遇到无从判断的来源

- 内容里有没有对其他权威来源的清晰引用
- 是不是已被 Grok 或 Tavily 的 score 给出权重（≥0.7 才考虑）
- URL 路径规范与否

---

## 5. 输出规范

### 推荐结构

```markdown
**结论**：<一句话答案>（置信度: <High/Medium/Low>）

**细节**：
<展开分析，每个关键事实后带引用>

**分歧**（如果有）：
- 来源 A 说 ...
- 来源 B 说 ...
- 判断依据：...

**Sources**:
- [标题1](URL1)
- [标题2](URL2)
```

### 禁止

- 没有 Sources 段的事实性回答
- "根据我的搜索" / "一般来说" / "据报道" 这些不带具体来源的措辞
- 把 Grok 的回答段落原样粘贴（它经常把不相关的话编成 assertion，需要你裁剪+验证）
- 在 Sources 段列出你没读过的 URL（只列 citations 里真实存在的）

### 何时可以省略引用

**只有**这几种情况：

- 纯代码调整（比如重命名变量）
- 用户明确说"不用搜，就用你的通识回答"
- 问题属于通用编程原理（如"什么是递归"） — 但仍应注意这类回答可能因语言版本差异而过时

---

## 6. 快速自检清单

向用户交付回答前：

- [ ] 每个事实性结论都有至少 1 个 `[标题](URL)` 引用
- [ ] 单源结论都标了 `置信度: Low`
- [ ] 所有 URL 都是从 `citations` / `results` 字段里真实出现过的
- [ ] 分歧的地方没藏着掖着
- [ ] Sources 段存在且非空
- [ ] 没用"一般来说 / 据报道 / 多方消息"这种无主语措辞
- [ ] 时效敏感的内容有明确发布时间标注

一条不满足，退回去补或降级标注。


### 搜索方法论（search-methodology）

配合 `search_planning.py` 使用。当用户问题属于 L2（3-5 次搜索的比较题）或 L3（6+ 次的调研综述）时，先跑一次规划再按 plan 执行。这份文档解释每个阶段应该产出什么、为什么必要。

---

## 阶段 1：意图分析

**目标**：从用户的自然语言提问里提炼出可搜索的核心问题。

### 产出字段

| 字段 | 含义 | 示例 |
|------|------|------|
| `core_question` | 一句话重新表述，去掉含糊语气 | "2026 Q2 最适合 RAG 的向量数据库是哪些？评估依据？" |
| `query_type` | factual / comparative / exploratory / analytical | "comparative" |
| `time_sensitivity` | realtime / recent / historical / timeless | "recent" |
| `terms_to_verify` | 需要先确认含义的术语 | `["RAG workload", "vector database 2026 ranking"]` |

### 为什么必要

用户问题经常带隐含前提（"最新"到底指什么月份？"最快"到底是 latency 还是 throughput？）。不澄清就搜，等于在模糊查询空间里随机游走。

### 常见陷阱

- **含糊时间词** — "最新"可能指昨天也可能指这个季度。先决定 `time_sensitivity`，`tavily_search` 的 `--time-range` 才知道怎么传
- **有歧义术语** — 如"Agent SDK"可能指 Claude Agent SDK、OpenAI Agent SDK、LangGraph 的 SDK。进 `terms_to_verify`
- **未声明的评估标准** — 用户问"哪个好"但没说按什么评估。要么主动补一条验证查询，要么回答末尾列出多个维度

---

## 阶段 2：查询拆解

**目标**：把核心问题打碎成 3-7 个子查询，每个都能作为独立的搜索 query。

### 产出结构

```json
"sub_queries": [
  {"id": 1, "query": "什么是 RAG workload 标准定义", "depends_on": [], "rationale": "术语验证"},
  {"id": 2, "query": "2026 年主流向量数据库排行", "depends_on": [], "rationale": "扫描候选"},
  {"id": 3, "query": "Pinecone vs Weaviate vs Qdrant 性能对比 2026", "depends_on": [2], "rationale": "聚焦 top 3"},
  {"id": 4, "query": "向量数据库定价模型对比 2026", "depends_on": [2], "rationale": "独立维度"}
]
```

### 拆解原则

1. **非重叠** — 子查询之间不能大幅重复；如果注定命中同一批页面就合并
2. **依赖标注** — B 需要 A 的结果才能写具体 query，就标 `depends_on: [A.id]`
3. **术语验证先行** — `terms_to_verify` 每项都是独立子查询（depends_on: []）放最前
4. **数量上限 7** — 超过多半没打碎干净或课题太大需再分

### 什么时候拆得不够细

- 一个 sub_query 预期结果覆盖 3+ 个独立事实 → 拆
- 回答它需要先回答另一个未列出的问题 → 补前置 sub_query

### 什么时候拆过头

- 两个子查询注定命中同一组 URL → 合并
- 子查询完全无关 → 这不是一个课题而是两个，分两次规划

---

## 阶段 3：策略选择

**目标**：决定搜索的展开顺序。

| 策略 | 适用 | 展开方式 |
|------|------|---------|
| `broad_first` | 探索型、我不知道候选集 | 先宽泛扫出候选 → 挑 top N 逐个深入 |
| `narrow_first` | 分析型、候选已定但需细节 | 直接针对每个候选精准搜 → 仅信息不够时才横向扩展 |
| `targeted` | 事实型、目标信息位置已知 | 直接抓官方 URL 或已知文档 |

### 选择规则

- 用户提到具体产品/工具名 → `targeted` 或 `narrow_first`
- 用户问"哪些 / 有什么选项" → `broad_first`
- 用户问"X vs Y"且 X、Y 已定 → `narrow_first`

### 选错的代价

- `broad_first` 用在已知目标上 → 在 SEO 垃圾里绕远路
- `targeted` 用在探索上 → 漏掉真正的候选
- `narrow_first` 用在一无所知时 → 把错的候选当真

---

## 阶段 4：工具映射

**目标**：把每个 sub_query 映射到具体脚本 + 决定并行/串行。

### 产出结构

```json
"tool_plan": [
  {"step": 1, "tool": "dual_search", "query_id": 1, "parallel_with": [2], "notes": "术语+排行并行"},
  {"step": 2, "tool": "dual_search", "query_id": 2, "parallel_with": [1], "notes": "与 step 1 同时起"},
  {"step": 3, "tool": "tavily_search", "query_id": 3, "parallel_with": [4], "notes": "depth=advanced"},
  {"step": 4, "tool": "tavily_search", "query_id": 4, "parallel_with": [3], "notes": "news topic"}
]
```

### 工具选择速查

| 子查询特征 | 选 |
|-----------|-----|
| 跨源验证的事实 | `dual_search` |
| 只要评分排序的结构化结果 | `tavily_search` |
| 需要 AI 综合分析 | `grok_search` |
| 抓已知 URL 正文 | `web_fetch` |
| 发现站点结构 | `web_map` |
| 新闻时效敏感 | `tavily_search --topic news` |

### 并行/串行判断

- 两个 sub_query 的 `depends_on` 都没有对方 → 可并行
- 用 `ThreadPoolExecutor` 或多开 bash 进程同时跑
- 串行只用于真正的数据依赖（比如必须先知道 top 3 才能搜它们的定价）

### 估算成本

在 tool_plan 末尾写 `estimated_searches`（总调用数）和 `expected_sources_per_query`。单次课题超过 20 次搜索通常是问题太大，退回阶段 2 重新拆。

---

## 从 plan 到执行的反馈

按 tool_plan 跑完一轮后，检查每个 sub_query 结果：

- **足够且一致** — 直接写进最终答案对应段落
- **足够但有分歧** — 记下分歧，在最终答案里展示双方 + 置信度标 Medium
- **不足（<2 独立来源）** — 启动补充搜索，优先换工具（Tavily 拿不到的换 Grok，Grok 模糊的换 Tavily advanced）
- **完全空/失败** — 要么术语错了（回阶段 1），要么目标不存在（诚实告诉用户）

---

## 模板：把方法论压成一次对话

当复杂度突然上来你不想自己规划，直接：

```bash
python scripts/search_planning.py --query "<用户的原问题>" > plan.json
```

输出就是本文档四阶段的 JSON 化结果。拿到后读一遍 `intent.terms_to_verify` 确认没有理解偏差，然后按 `tool_plan` 分步执行即可。


---

## 三、参考脚本（scripts/）

所有脚本以代码块附录，按需复制到自己的项目即可使用。


### scripts/_creds.py

```python
"""Credentials loader for this DeepSearch skill.

Loads credentials from (in priority order):
  1. Environment variables (GROK2API_API_KEY, TAVILY_API_KEY, FIRECRAWL_API_KEY, etc.)
  2. the project's .env file ([LLM_APIS] + [CREDENTIALS] sections)

Keeps .env authoritative — no separate .env file needed.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

# scripts/_creds.py → 项目根目录的 .env
DOTENV_PATH = Path(__file__).resolve().parents[2] / ".env"

DEFAULTS = {
    "GROK2API_BASE_URL": "https://<openai-compatible-host>/v1",
    "GROK2API_MODEL": "grok-4.20-beta",
    "TAVILY_BASE_URL": "https://api.tavily.com",
    "FIRECRAWL_BASE_URL": "https://api.firecrawl.dev/v2",
}


def _parse_dotenv(text: str) -> dict[str, str]:
    """Extract key:value pairs from .env.

    Format: `KEY: value` or `key: value` (lowercase project convention).
    We map the project's lowercase shorthand names to standard env-var names.
    """
    out: dict[str, str] = {}
    # Generic KEY: value collector (strips inline comments starting with `  #`).
    for m in re.finditer(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.+)$", text, re.M):
        key, val = m.group(1), m.group(2)
        # Strip trailing inline comments (two+ spaces then #).
        val = re.sub(r"\s{2,}#.*$", "", val).strip()
        if val:
            out[key] = val

    # Normalize shorthand -> standard env names (only if not already set).
    alias = {
        "legacy_url": "GROK2API_BASE_URL",
        "legacy_key": "GROK2API_API_KEY",
        "legacy_url": "GROK2API_LEGACY_BASE_URL",
        "legacy_key": "GROK2API_LEGACY_API_KEY",
    }
    for src, dst in alias.items():
        if src in out and dst not in out:
            out[dst] = out[src]
    return out


@lru_cache(maxsize=1)
def get_creds() -> dict[str, Any]:
    """Return credentials + endpoints.

    Resolution order: env var > .env > DEFAULTS.
    """
    creds: dict[str, Any] = dict(DEFAULTS)

    if DOTENV_PATH.exists():
        creds.update(_parse_dotenv(DOTENV_PATH.read_text(encoding="utf-8")))

    for k in (
        "GROK2API_API_KEY",
        "GROK2API_BASE_URL",
        "GROK2API_MODEL",
        "TAVILY_API_KEY",
        "TAVILY_BASE_URL",
        "FIRECRAWL_API_KEY",
        "FIRECRAWL_BASE_URL",
    ):
        v = os.environ.get(k)
        if v:
            creds[k] = v

    # Multi-key env support (comma-separated).
    tavily_list = os.environ.get("TAVILY_API_KEYS") or creds.get("TAVILY_API_KEY", "")
    creds["TAVILY_API_KEYS"] = [k.strip() for k in tavily_list.split(",") if k.strip()]

    fc_list = os.environ.get("FIRECRAWL_API_KEYS") or creds.get("FIRECRAWL_API_KEY", "")
    creds["FIRECRAWL_API_KEYS"] = [k.strip() for k in fc_list.split(",") if k.strip()]

    return creds


def require(key: str) -> str:
    v = get_creds().get(key)
    if not v:
        raise RuntimeError(
            f"Missing credential: {key}. Set env var {key} or add to "
            f"{DOTENV_PATH} under [LLM_APIS] / [CREDENTIALS]."
        )
    if isinstance(v, list):
        if not v:
            raise RuntimeError(f"Empty key list: {key}")
        return v[0]
    return str(v)


if __name__ == "__main__":
    import json
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows GBK fix
    except Exception:
        pass
    c = get_creds()
    for k, v in list(c.items()):
        if "KEY" in k and v:
            if isinstance(v, list):
                c[k] = [f"{x[:8]}...{x[-4:]}" if len(x) > 12 else "***" for x in v]
            else:
                c[k] = f"{v[:8]}...{v[-4:]}" if len(v) > 12 else "***"
    print(json.dumps(c, indent=2, ensure_ascii=False))
```


### scripts/_http.py

```python
"""Shared HTTP utilities: pooled sessions, key-rotation, OpenAI/Tavily helpers.

Design rationale
----------------
* **One Session per backend.** Module-level lazy sessions (GROK2API, Tavily,
  FireCrawl) reuse TCP/TLS connections — material speedup when ``dual_search``
  fans out in-process.
* **Sticky key rotation.** Stay on the current key until 401/403/429, then hop
  forward. 5xx triggers exponential backoff retry on the same key. Honors
  ``Retry-After`` if upstream sends it.
* **One SSE/JSON parser.** GROK2API returns SSE even for non-streamed requests;
  callers must not re-implement chunk assembly.
* **One openai_chat / tavily_post.** Three scripts call GROK2API and three call
  Tavily — one helper each kills the duplication.

Public API
----------
``log``, ``dump_json``, ``KeyRotationFailed``,
``session``, ``call_with_key_rotation``,
``parse_openai_response``, ``strip_think``,
``openai_chat``, ``tavily_post``, ``firecrawl_post``.
"""

from __future__ import annotations

import json
import random
import re
import sys
import time
from typing import Any, Callable, Iterable

import requests
from requests.adapters import HTTPAdapter

from _creds import get_creds

# --------------------------------- stdio ---------------------------------

_STDOUT_CONFIGURED = False


def log(msg: str) -> None:
    """Debug -> stderr; stdout stays a clean JSON channel."""
    print(f"[deepsearch] {msg}", file=sys.stderr, flush=True)


def dump_json(obj: Any) -> None:
    """Print JSON to stdout, forcing UTF-8 once on Windows (cp936 chokes)."""
    global _STDOUT_CONFIGURED
    if not _STDOUT_CONFIGURED:
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # py3.7+
        except Exception:
            pass
        _STDOUT_CONFIGURED = True
    print(json.dumps(obj, ensure_ascii=False, indent=2))


# ------------------------------ pooled sessions ------------------------------

class KeyRotationFailed(RuntimeError):
    """All API keys exhausted."""


def _make_session(timeout: int, pool: int = 8) -> requests.Session:
    s = requests.Session()
    adapter = HTTPAdapter(pool_connections=pool, pool_maxsize=pool)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    _orig = s.request

    def _req(method, url, **kwargs):
        kwargs.setdefault("timeout", timeout)
        return _orig(method, url, **kwargs)

    s.request = _req  # type: ignore[method-assign]
    return s


def session(timeout: int = 30) -> requests.Session:
    """Back-compat factory; new code prefers the module-level pooled sessions."""
    return _make_session(timeout)


_GROK2_SESSION: requests.Session | None = None
_TAVILY_SESSION: requests.Session | None = None
_FIRECRAWL_SESSION: requests.Session | None = None


def _grok2() -> requests.Session:
    global _GROK2_SESSION
    if _GROK2_SESSION is None:
        _GROK2_SESSION = _make_session(timeout=90)
    return _GROK2_SESSION


def _tavily() -> requests.Session:
    global _TAVILY_SESSION
    if _TAVILY_SESSION is None:
        _TAVILY_SESSION = _make_session(timeout=60)
    return _TAVILY_SESSION


def _firecrawl() -> requests.Session:
    global _FIRECRAWL_SESSION
    if _FIRECRAWL_SESSION is None:
        _FIRECRAWL_SESSION = _make_session(timeout=90)
    return _FIRECRAWL_SESSION


# ---------------------------- key rotation core ----------------------------

def call_with_key_rotation(
    keys: Iterable[str],
    do_request: Callable[[str], requests.Response],
    *,
    max_attempts_per_key: int = 2,
    backoff_base: float = 1.0,
) -> requests.Response:
    """Try each key; rotate on 401/403/429; retry on 5xx with exp backoff."""
    keys = [k for k in keys if k]
    if not keys:
        raise KeyRotationFailed("No API keys configured")

    last_err: str | None = None
    for idx, key in enumerate(keys):
        for attempt in range(max_attempts_per_key):
            try:
                resp = do_request(key)
            except requests.RequestException as e:
                last_err = f"network error on key #{idx + 1}: {e}"
                log(last_err)
                time.sleep(backoff_base * (2 ** attempt) + random.random() * 0.3)
                continue

            sc = resp.status_code
            if 200 <= sc < 300:
                return resp
            if sc in (401, 403, 429):
                last_err = f"key #{idx + 1} -> HTTP {sc}: {resp.text[:200]}"
                log(last_err + " (rotating)")
                ra = resp.headers.get("Retry-After")
                if sc == 429 and ra:
                    try:
                        time.sleep(min(float(ra), 5.0))
                    except ValueError:
                        pass
                break
            if 500 <= sc < 600:
                last_err = f"HTTP {sc} on key #{idx + 1} attempt {attempt + 1}"
                log(last_err)
                time.sleep(backoff_base * (2 ** attempt))
                continue
            resp.raise_for_status()

    raise KeyRotationFailed(f"All {len(keys)} key(s) exhausted. Last error: {last_err}")


# ------------------------ OpenAI-compatible helpers ------------------------

def parse_openai_response(text: str) -> dict:
    """Accept standard JSON or SSE stream; return canonical chat-completion shape.

    ``{"choices": [{"message": {"content", "reasoning_content"},
                    "finish_reason"}], "model": str|None, "usage": dict}``
    """
    text = text.strip()
    if text.startswith("{"):
        return json.loads(text)

    content: list[str] = []
    reasoning: list[str] = []
    model: str | None = None
    usage: dict = {}
    finish_reason: str | None = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError:
            continue
        model = chunk.get("model") or model
        if chunk.get("usage"):
            usage = chunk["usage"]
        for ch in chunk.get("choices", []):
            delta = ch.get("delta") or {}
            if delta.get("content"):
                content.append(delta["content"])
            if delta.get("reasoning_content"):
                reasoning.append(delta["reasoning_content"])
            if ch.get("finish_reason"):
                finish_reason = ch["finish_reason"]

    return {
        "choices": [{
            "message": {
                "content": "".join(content),
                "reasoning_content": "".join(reasoning) or None,
            },
            "finish_reason": finish_reason,
        }],
        "model": model,
        "usage": usage,
    }


_THINK_RE = re.compile(r"<think>(.*?)</think>", re.S)


def strip_think(content: str) -> tuple[str, str | None]:
    """Strip Grok-4.x ``<think>...</think>`` blocks. Returns (clean, joined_thoughts)."""
    blocks = _THINK_RE.findall(content)
    clean = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.S).strip()
    joined = "\n\n".join(b.strip() for b in blocks).strip()
    return clean, (joined or None)


def openai_chat(
    messages: list[dict],
    *,
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    timeout: int = 90,
) -> dict:
    """Single-call GROK2API chat helper. Returns dict with content/reasoning/model/usage/elapsed_s."""
    creds = get_creds()
    keys = creds.get("GROK2API_API_KEYS") or ([creds["GROK2API_API_KEY"]] if creds.get("GROK2API_API_KEY") else [])
    if not keys:
        raise RuntimeError("GROK2API_API_KEY not configured")
    base = creds["GROK2API_BASE_URL"].rstrip("/")
    url = f"{base}/chat/completions"
    body = {
        "model": model or creds.get("GROK2API_MODEL", "grok-4.20-beta"),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    s = _grok2()

    def do(key: str) -> requests.Response:
        return s.post(
            url,
            json=body,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            timeout=timeout,
        )

    log(f"POST {url} model={body['model']}")
    t0 = time.time()
    resp = call_with_key_rotation(keys, do)
    elapsed = round(time.time() - t0, 2)

    parsed = parse_openai_response(resp.text)
    msg = parsed["choices"][0]["message"]
    return {
        "content": msg.get("content", ""),
        "reasoning": msg.get("reasoning_content"),
        "model": parsed.get("model") or body["model"],
        "usage": parsed.get("usage", {}),
        "elapsed_s": elapsed,
    }


# ------------------------------ Tavily helper ------------------------------

def tavily_post(path: str, body: dict, *, timeout: int = 45) -> dict:
    """POST to a Tavily endpoint with key rotation; return parsed JSON."""
    creds = get_creds()
    keys = creds["TAVILY_API_KEYS"]
    base = creds["TAVILY_BASE_URL"].rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    s = _tavily()

    def do(key: str) -> requests.Response:
        return s.post(url, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=timeout)

    log(f"POST {url}")
    return call_with_key_rotation(keys, do).json()


def firecrawl_post(path: str, body: dict, *, timeout: int = 90) -> dict:
    """POST to a FireCrawl endpoint with key rotation; return parsed JSON."""
    creds = get_creds()
    keys = creds.get("FIRECRAWL_API_KEYS") or []
    if not keys:
        raise RuntimeError("FIRECRAWL_API_KEY not configured")
    base = creds["FIRECRAWL_BASE_URL"].rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    s = _firecrawl()

    def do(key: str) -> requests.Response:
        return s.post(url, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=timeout)

    log(f"POST {url}")
    return call_with_key_rotation(keys, do).json()
```


### scripts/dual_search.py

```python
#!/usr/bin/env python3
"""Dual-engine search: runs Grok + Tavily in parallel threads, merges results.

Rationale: cross-validate a single query with two independent engines. When
both agree on facts and overlap on sources, confidence is high; when they
diverge, the caller should drill deeper before stating anything as fact.

Implementation note: previously spawned two python subprocesses (~600ms cold
overhead each on Windows). Now both calls share this process and the pooled
HTTP sessions in `_http.py`, so latency = max(grok, tavily) instead of
max(grok, tavily) + 2 * spawn cost.

Usage:
    python dual_search.py --query "grok-4.1 vs claude-sonnet-4-6 coding benchmark 2026"

Output: JSON {query, grok{...}, tavily{...}, overlap_urls[], unique_to_*, confidence_hint, elapsed_s}.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import re
import sys
import time

from _http import dump_json, log, openai_chat, strip_think, tavily_post

_URL_RE = re.compile(r"https?://[^\s)\]]+")


def _grok(query: str, model: str | None) -> dict:
    sys_prompt = (
        "You are a web research assistant. Answer factually with explicit URL "
        "citations. Cite each non-trivial claim with a markdown link."
    )
    try:
        r = openai_chat(
            [{"role": "system", "content": sys_prompt}, {"role": "user", "content": f"Question: {query}"}],
            model=model,
        )
    except Exception as e:
        return {"error": str(e)}
    clean, think = strip_think(r["content"])
    seen: set[str] = set()
    citations: list[dict] = []
    for url in _URL_RE.findall(clean):
        url = url.rstrip(".,;:!?\"'")
        if url not in seen:
            seen.add(url)
            citations.append({"url": url, "title": ""})
    return {
        "content": clean,
        "reasoning": r.get("reasoning") or think,
        "model": r["model"],
        "usage": r.get("usage", {}),
        "citations": citations,
        "sources_count": len(citations),
        "elapsed_s": r["elapsed_s"],
    }


def _tavily(query: str, depth: str, max_results: int) -> dict:
    body = {
        "query": query,
        "search_depth": depth,
        "topic": "general",
        "max_results": max_results,
        "include_answer": True,
    }
    t0 = time.time()
    try:
        data = tavily_post("search", body)
    except Exception as e:
        return {"error": str(e)}
    elapsed = round(time.time() - t0, 2)
    results = [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "content": r.get("content", ""),
            "score": r.get("score"),
            "published_date": r.get("published_date"),
        }
        for r in data.get("results", [])
    ]
    return {
        "answer": data.get("answer"),
        "results": results,
        "results_count": len(results),
        "elapsed_s": elapsed,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Parallel Grok + Tavily cross-validation search")
    p.add_argument("--query", required=True)
    p.add_argument("--depth", choices=["basic", "advanced"], default="basic")
    p.add_argument("--max-results", type=int, default=8)
    p.add_argument("--model", default=None, help="Override Grok model")
    args = p.parse_args()

    log("dispatching grok + tavily in parallel (in-process)")
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        fg = ex.submit(_grok, args.query, args.model)
        ft = ex.submit(_tavily, args.query, args.depth, args.max_results)
        grok = fg.result()
        tavily = ft.result()
    elapsed = round(time.time() - t0, 2)

    grok_urls = {c["url"] for c in grok.get("citations", []) if c.get("url")}
    tavily_urls = {r["url"] for r in tavily.get("results", []) if r.get("url")}
    overlap = sorted(grok_urls & tavily_urls)

    dump_json({
        "query": args.query,
        "grok": grok,
        "tavily": tavily,
        "overlap_urls": overlap,
        "unique_to_grok": sorted(grok_urls - tavily_urls),
        "unique_to_tavily": sorted(tavily_urls - grok_urls),
        "confidence_hint": (
            "high" if overlap else ("medium" if (grok_urls and tavily_urls) else "low")
        ),
        "elapsed_s": elapsed,
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
```


### scripts/grok_search.py

```python
#!/usr/bin/env python3
"""Grok AI search via GROK2API (OpenAI-compatible chat completion).

Usage:
    python grok_search.py --query "FastAPI 0.200 release date"
    python grok_search.py --query "..." --model grok-4.1-fast --platform "GitHub"

Output: JSON {content, reasoning, model, usage, citations[], sources_count, elapsed_s}.
"""
from __future__ import annotations

import argparse
import re
import sys

from _http import dump_json, openai_chat, strip_think

_URL_RE = re.compile(r"https?://[^\s)\]]+")


def extract_citations(text: str) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for url in _URL_RE.findall(text):
        url = url.rstrip(".,;:!?\"'")
        if url in seen:
            continue
        seen.add(url)
        out.append({"url": url, "title": ""})
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Grok web search via GROK2API")
    p.add_argument("--query", required=True)
    p.add_argument("--model", default=None, help="Override default model (e.g. grok-4.1-fast)")
    p.add_argument("--platform", default="", help="Optional source-platform hint passed to model")
    p.add_argument("--temperature", type=float, default=0.3)
    p.add_argument("--max-tokens", type=int, default=4096)
    args = p.parse_args()

    sys_prompt = (
        "You are a web research assistant. Answer factually with explicit URL citations. "
        "Cite each non-trivial claim with a markdown link. If unsure, say so."
    )
    user = f"Question: {args.query}"
    if args.platform:
        user += f"\nPrefer sources from: {args.platform}"

    try:
        result = openai_chat(
            [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user}],
            model=args.model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )
    except Exception as e:
        dump_json({"error": str(e), "query": args.query})
        return 1

    clean, think = strip_think(result["content"])
    citations = extract_citations(clean)
    dump_json({
        "query": args.query,
        "content": clean,
        "reasoning": result.get("reasoning") or think,
        "model": result["model"],
        "usage": result.get("usage", {}),
        "citations": citations,
        "sources_count": len(citations),
        "elapsed_s": result["elapsed_s"],
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
```


### scripts/search_planning.py

```python
#!/usr/bin/env python3
"""Structured search planner: converts a complex question into a search plan JSON.

Invokes Grok to decompose a Level-3 query into intent / sub-queries / strategy /
tool mapping. Run this before launching many searches - it prevents duplicate
work and surfaces verification dependencies.

Usage:
    python search_planning.py --query "2026 \u5e74\u4e3b\u6d41\u5411\u91cf\u6570\u636e\u5e93\u5b8c\u6574\u5bf9\u6bd4"

Output: JSON plan with intent, sub_queries[], strategy, tool_plan, _meta.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

from _http import dump_json, openai_chat, strip_think

PROMPT = """You are a search planner. Given a user's research question, produce
a structured plan a search agent can execute directly. Output ONLY valid JSON
matching this schema - no prose before or after:

{
  "intent": {
    "core_question": "one-sentence reformulation",
    "query_type": "factual|comparative|exploratory|analytical",
    "time_sensitivity": "realtime|recent|historical|timeless",
    "terms_to_verify": ["term1", "term2"]
  },
  "sub_queries": [
    {"id": 1, "query": "...", "depends_on": [], "rationale": "..."},
    {"id": 2, "query": "...", "depends_on": [1], "rationale": "..."}
  ],
  "strategy": "broad_first|narrow_first|targeted",
  "tool_plan": [
    {"step": 1, "tool": "dual_search|grok_search|tavily_search|web_fetch|web_map",
     "query_id": 1, "parallel_with": [], "notes": "..."}
  ],
  "estimated_searches": 5,
  "expected_sources_per_query": 3
}

Rules:
- 3-7 sub_queries, non-overlapping.
- Sub-queries that verify domain terms go first (depends_on: []).
- Prefer dual_search for cross-validation; tavily_search for structured news;
  grok_search for synthesis; web_fetch for known URLs; web_map for exploration.
- Mark parallelizable steps with shared `parallel_with` list.
"""

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```\s*$", re.M)


def main() -> int:
    p = argparse.ArgumentParser(description="Generate a structured search plan")
    p.add_argument("--query", required=True)
    p.add_argument("--model", default=None)
    args = p.parse_args()

    try:
        result = openai_chat(
            [
                {"role": "system", "content": PROMPT},
                {"role": "user", "content": f"Question: {args.query}"},
            ],
            model=args.model,
            temperature=0.2,
            max_tokens=2000,
            timeout=120,
        )
    except Exception as e:
        dump_json({"error": str(e), "query": args.query})
        return 1

    content, _ = strip_think(result["content"])
    content = _FENCE_RE.sub("", content).strip()

    try:
        plan = json.loads(content)
    except json.JSONDecodeError as e:
        dump_json({"error": "planner returned non-JSON", "detail": str(e), "raw": content[:1500]})
        return 1

    plan["_meta"] = {
        "query": args.query,
        "model": result["model"],
        "elapsed_s": result["elapsed_s"],
        "usage": result.get("usage", {}),
    }
    dump_json(plan)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```


### scripts/tavily_search.py

```python
#!/usr/bin/env python3
"""Tavily structured web search.

Usage:
    python tavily_search.py --query "Python 3.14 release notes"
    python tavily_search.py --query "..." --depth advanced --topic news --time-range week

Output: JSON {query, answer, results[]{title,url,content,score,published_date}, results_count, elapsed_s}.
"""
from __future__ import annotations

import argparse
import sys
import time

from _http import dump_json, tavily_post


def main() -> int:
    p = argparse.ArgumentParser(description="Tavily web search")
    p.add_argument("--query", required=True)
    p.add_argument("--depth", choices=["basic", "advanced"], default="basic")
    p.add_argument("--topic", choices=["general", "news"], default="general")
    p.add_argument("--max-results", type=int, default=8)
    p.add_argument("--time-range", choices=["day", "week", "month", "year"], default=None)
    p.add_argument("--include-domains", nargs="*", default=None)
    p.add_argument("--exclude-domains", nargs="*", default=None)
    args = p.parse_args()

    body = {
        "query": args.query,
        "search_depth": args.depth,
        "topic": args.topic,
        "max_results": args.max_results,
        "include_answer": True,
    }
    if args.time_range:
        body["time_range"] = args.time_range
    if args.include_domains:
        body["include_domains"] = args.include_domains
    if args.exclude_domains:
        body["exclude_domains"] = args.exclude_domains

    t0 = time.time()
    try:
        data = tavily_post("search", body)
    except Exception as e:
        dump_json({"error": str(e), "query": args.query})
        return 1
    elapsed = round(time.time() - t0, 2)

    results = [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "content": r.get("content", ""),
            "score": r.get("score"),
            "published_date": r.get("published_date"),
        }
        for r in data.get("results", [])
    ]
    dump_json({
        "query": args.query,
        "answer": data.get("answer"),
        "results": results,
        "results_count": len(results),
        "elapsed_s": elapsed,
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
```


### scripts/web_fetch.py

```python
#!/usr/bin/env python3
"""Fetch a single URL's content as markdown.

Primary path: Tavily /extract (clean, fast, handles most sites).
Fallback: FireCrawl /scrape (better for Cloudflare-protected or JS-heavy pages).

Usage:
    python web_fetch.py --url "https://docs.python.org/3/whatsnew/3.13.html"
    python web_fetch.py --url "..." --force-firecrawl

Output: JSON {url, provider, markdown, length, elapsed_s}. On error: error/last_error.
"""
from __future__ import annotations

import argparse
import sys
import time

from _http import dump_json, firecrawl_post, log, tavily_post


def try_tavily(url: str) -> dict:
    data = tavily_post(
        "extract",
        {"urls": [url], "include_images": False, "extract_depth": "advanced"},
        timeout=60,
    )
    results = data.get("results") or []
    if not results:
        raise RuntimeError(f"Tavily returned no results for {url}")
    raw = (results[0].get("raw_content") or "").strip()
    if not raw:
        raise RuntimeError("Tavily returned empty content")
    return {"markdown": raw, "provider": "tavily"}


def try_firecrawl(url: str) -> dict:
    data = firecrawl_post(
        "scrape",
        {"url": url, "formats": ["markdown"], "onlyMainContent": True},
    )
    if not data.get("success", True):
        raise RuntimeError(f"FireCrawl error: {data.get('error')}")
    payload = data.get("data", data)
    md = (payload.get("markdown") or "").strip()
    if not md:
        raise RuntimeError("FireCrawl returned empty markdown")
    return {"markdown": md, "provider": "firecrawl"}


def main() -> int:
    p = argparse.ArgumentParser(description="Single-URL page fetcher")
    p.add_argument("--url", required=True)
    p.add_argument("--force-firecrawl", action="store_true", help="Skip Tavily, go straight to FireCrawl")
    p.add_argument("--max-length", type=int, default=0, help="Truncate markdown to N chars (0 = full)")
    args = p.parse_args()

    providers = []
    if not args.force_firecrawl:
        providers.append(("tavily", try_tavily))
    providers.append(("firecrawl", try_firecrawl))

    t0 = time.time()
    last_err: str | None = None
    result: dict | None = None
    for name, fn in providers:
        try:
            log(f"trying provider: {name}")
            result = fn(args.url)
            break
        except Exception as e:
            last_err = f"{name}: {e}"
            log(f"provider {name} failed - {e}")

    elapsed = round(time.time() - t0, 2)
    if result is None:
        dump_json({"url": args.url, "error": "all providers failed", "last_error": last_err, "elapsed_s": elapsed})
        return 1

    md = result["markdown"]
    full_len = len(md)
    if args.max_length and full_len > args.max_length:
        md = md[: args.max_length] + f"\n\n... [truncated at {args.max_length} chars]"

    dump_json({
        "url": args.url,
        "provider": result["provider"],
        "markdown": md,
        "length": full_len,
        "elapsed_s": elapsed,
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
```


### scripts/web_map.py

```python
#!/usr/bin/env python3
"""Map a website's URL structure via Tavily /map.

Use when you need to discover what's in a docs site / knowledge base before
choosing specific pages to fetch.

Usage:
    python web_map.py --url "https://docs.tavily.com"
    python web_map.py --url "..." --depth 2 --instructions "find API reference"

Output: JSON {url, urls[], urls_count, elapsed_s}.
"""
from __future__ import annotations

import argparse
import sys
import time

from _http import dump_json, tavily_post


def main() -> int:
    p = argparse.ArgumentParser(description="Site structure mapping via Tavily")
    p.add_argument("--url", required=True)
    p.add_argument("--depth", type=int, default=1, choices=[1, 2, 3, 4, 5])
    p.add_argument("--breadth", type=int, default=20, help="Max links per page (1-500)")
    p.add_argument("--limit", type=int, default=50, help="Total URL cap (1-500)")
    p.add_argument("--instructions", default="", help="Natural language filter")
    args = p.parse_args()

    body = {
        "url": args.url,
        "max_depth": args.depth,
        "max_breadth": args.breadth,
        "limit": args.limit,
    }
    if args.instructions:
        body["instructions"] = args.instructions

    t0 = time.time()
    try:
        data = tavily_post("map", body, timeout=150)
    except Exception as e:
        dump_json({"error": str(e), "url": args.url})
        return 1
    elapsed = round(time.time() - t0, 2)

    urls = data.get("results", [])
    dump_json({
        "url": args.url,
        "urls": urls,
        "urls_count": len(urls),
        "elapsed_s": elapsed,
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
```
